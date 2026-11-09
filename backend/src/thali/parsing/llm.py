import time
lazy import json
lazy from collections import OrderedDict
lazy from collections.abc import Callable

from pydantic import BaseModel, Field, field_validator
lazy import httpx
lazy from pydantic import ValidationError

lazy from thali.config import Settings
lazy from thali.models import ParsedRequest

DEFAULT_COOLDOWN_S = 30.0
MAX_COMPLETION_TOKENS = 700

SYSTEM_PROMPT = """You read one food-delivery request and return JSON describing only what the user explicitly asked for.
Rules:
- Never guess. If something is not stated, use null (or [] for lists).
- Every non-null field needs "evidence": words copied exactly from the request.
- budget, delivery_time and min_rating evidence must include the number and its cue or unit, e.g. "under ₹300", "within 30 minutes", "4+ stars".
- diet.value is one of veg, vegan, egg, non_veg. Use egg only for eggetarian requests. Do not infer diet from dish names.
- intent is one of: discovery (looking for options), decision (asking which is best or better), information (asking a factual question such as a price), action (asking to order or book), clarification (no usable food request).
Return exactly this shape:
{"intent": "...", "dish": {"value": "...", "evidence": "..."} | null, "cuisine": {"value": "...", "evidence": "..."} | null,
 "diet": {"value": "...", "evidence": "..."} | null, "ingredients": [{"value": "...", "evidence": "..."}],
 "budget": {"evidence": "..."} | null, "delivery_time": {"evidence": "..."} | null, "min_rating": {"evidence": "..."} | null,
 "prefers_high_rating": {"evidence": "..."} | null, "prefers_low_price": {"evidence": "..."} | null,
 "prefers_fast_delivery": {"evidence": "..."} | null, "location": {"value": "...", "evidence": "..."} | null,
 "other_preferences": [{"value": "...", "evidence": "..."}]}"""  # noqa: E501

EXAMPLE_USER = "cheap paneer rolls near Powai in 20 mins, nothing spicy"
EXAMPLE_ASSISTANT = (
    '{"intent":"discovery","dish":{"value":"rolls","evidence":"rolls"},"cuisine":null,"diet":null,'
    '"ingredients":[{"value":"paneer","evidence":"paneer"}],"budget":null,'
    '"delivery_time":{"evidence":"in 20 mins"},"min_rating":null,"prefers_high_rating":null,'
    '"prefers_low_price":{"evidence":"cheap"},"prefers_fast_delivery":null,'
    '"location":{"value":"Powai","evidence":"Powai"},'
    '"other_preferences":[{"value":"nothing spicy","evidence":"nothing spicy"}]}'
)


class LlmUnavailable(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Evidence(BaseModel):
    evidence: str


class ValueEvidence(BaseModel):
    value: str
    evidence: str


class LlmExtraction(BaseModel):
    intent: str
    dish: ValueEvidence | None = None
    cuisine: ValueEvidence | None = None
    diet: ValueEvidence | None = None
    ingredients: list[ValueEvidence] = Field(default_factory=list)
    budget: Evidence | None = None
    delivery_time: Evidence | None = None
    min_rating: Evidence | None = None
    prefers_high_rating: Evidence | None = None
    prefers_low_price: Evidence | None = None
    prefers_fast_delivery: Evidence | None = None
    location: ValueEvidence | None = None
    other_preferences: list[ValueEvidence] = Field(default_factory=list)

    @field_validator("ingredients", "other_preferences", mode="before")
    @classmethod
    def none_as_empty(cls, value: object) -> object:
        return [] if value is None else value


def cache_key(query: str) -> str:
    return " ".join(query.lower().split())


def retry_after_seconds(response: httpx.Response) -> float:
    try:
        return max(float(response.headers.get("Retry-After", DEFAULT_COOLDOWN_S)), 0.0)
    except ValueError:
        return DEFAULT_COOLDOWN_S


class LlmParser:
    def __init__(
        self,
        client: httpx.AsyncClient,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client
        self._settings = settings
        self._clock = clock
        self._tokens = float(settings.llm_rpm)
        self._refilled_at = clock()
        self._cooldown_until = 0.0
        self._cache: OrderedDict[str, ParsedRequest] = OrderedDict()

    def cached(self, query: str) -> ParsedRequest | None:
        key = cache_key(query)
        if key not in self._cache:
            return None
        self._cache.move_to_end(key)
        return self._cache[key].model_copy(deep=True)

    def remember(self, query: str, parsed: ParsedRequest) -> None:
        key = cache_key(query)
        self._cache[key] = parsed.model_copy(deep=True)
        self._cache.move_to_end(key)
        while len(self._cache) > self._settings.llm_cache_size:
            self._cache.popitem(last=False)

    def _take_token(self) -> None:
        now = self._clock()
        if now < self._cooldown_until:
            raise LlmUnavailable("cooling down after rate limit")
        capacity = float(self._settings.llm_rpm)
        refill = (now - self._refilled_at) * capacity / 60
        self._tokens = min(capacity, self._tokens + refill)
        self._refilled_at = now
        if self._tokens < 1:
            raise LlmUnavailable("local rate limit")
        self._tokens -= 1

    def _payload(self, query: str) -> dict[str, object]:
        return {
            "model": self._settings.llm_model,
            "temperature": 0,
            "max_completion_tokens": MAX_COMPLETION_TOKENS,
            "reasoning_effort": "low",
            "include_reasoning": False,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": EXAMPLE_USER},
                {"role": "assistant", "content": EXAMPLE_ASSISTANT},
                {"role": "user", "content": query},
            ],
        }

    async def _post(self, query: str) -> httpx.Response:
        url = f"{self._settings.llm_base_url.rstrip('/')}/chat/completions"
        headers = {"Authorization": f"Bearer {self._settings.groq_api_key}"}
        try:
            return await self._client.post(
                url,
                json=self._payload(query),
                headers=headers,
                timeout=self._settings.llm_timeout_ms / 1000,
            )
        except httpx.HTTPError as error:
            raise LlmUnavailable("timeout") from error

    async def extract(self, query: str) -> LlmExtraction:
        self._take_token()
        response = await self._post(query)
        if response.status_code == 429:
            self._cooldown_until = self._clock() + retry_after_seconds(response)
        if response.status_code != 200:
            raise LlmUnavailable(f"HTTP {response.status_code}")
        return parse_completion(response)


def parse_completion(response: httpx.Response) -> LlmExtraction:
    try:
        content = response.json()["choices"][0]["message"]["content"]
    except ValueError as error:
        raise LlmUnavailable("invalid JSON") from error
    except (KeyError, IndexError, TypeError) as error:
        raise LlmUnavailable("unexpected shape") from error
    try:
        payload = json.loads(content)
    except (TypeError, ValueError) as error:
        raise LlmUnavailable("invalid JSON") from error
    try:
        return LlmExtraction.model_validate(payload)
    except ValidationError as error:
        raise LlmUnavailable("unexpected shape") from error
