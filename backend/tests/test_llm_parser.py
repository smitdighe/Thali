import json

import httpx
import pytest

from thali.config import Settings
from thali.parsing import LlmParser, parse_request

QUERY = "get me a vegetarian dosa under ₹200 quickly"
OTHER_QUERY = "any pizza near Powai within 20 minutes"
EXTRACTION = {
    "intent": "discovery",
    "dish": {"value": "dosa", "evidence": "dosa"},
    "cuisine": None,
    "diet": {"value": "veg", "evidence": "vegetarian"},
    "ingredients": [],
    "budget": {"evidence": "under ₹200"},
    "delivery_time": None,
    "min_rating": None,
    "prefers_high_rating": None,
    "prefers_low_price": None,
    "prefers_fast_delivery": {"evidence": "quickly"},
    "location": None,
    "other_preferences": [],
}


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Recorder:
    def __init__(self, responder) -> None:
        self.responder = responder
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responder(request)


def completion(payload: object) -> httpx.Response:
    body = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    return httpx.Response(200, json=body)


def ok(_request: httpx.Request) -> httpx.Response:
    return completion(EXTRACTION)


def rate_limited(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, headers={"Retry-After": "12"}, json={"error": "slow down"})


def times_out(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("too slow", request=request)


def server_error(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(500, json={"error": "boom"})


def not_json(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": "not json at all"}}]})


def body_not_json(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=b"<html>gateway</html>")


def wrong_shape(_request: httpx.Request) -> httpx.Response:
    return completion({"dish": "dosa"})


def missing_choices(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"choices": []})


def make_settings(**overrides) -> Settings:
    values = {"llm_rpm": 6, "llm_cache_size": 4, "llm_timeout_ms": 500, **overrides}
    return Settings(_env_file=None, GROQ_API_KEY="test-key", **values)


async def parse(recorder: Recorder, queries: list[str], clock=None, **overrides):
    clock = clock or FakeClock()
    results = []
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        llm = LlmParser(client, make_settings(**overrides), clock)
        for query in queries:
            results.append(await parse_request(query, llm))
    return results


async def test_success_returns_grounded_llm_parse():
    recorder = Recorder(ok)
    [(parsed, reason)] = await parse(recorder, [QUERY])
    assert reason is None
    assert parsed.parser == "llm"
    assert parsed.dish == "dosa"
    assert parsed.diet == "veg"
    assert parsed.max_price_inr == 200
    assert parsed.speed_preference == "fast"
    assert len(recorder.requests) == 1


async def test_request_shape_matches_spec():
    recorder = Recorder(ok)
    await parse(recorder, [QUERY])
    request = recorder.requests[0]
    assert str(request.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert request.headers["Authorization"] == "Bearer test-key"
    payload = json.loads(request.content)
    assert payload["model"] == "openai/gpt-oss-20b"
    assert payload["temperature"] == 0
    assert payload["max_completion_tokens"] == 700
    assert payload["reasoning_effort"] == "low"
    assert payload["include_reasoning"] is False
    assert payload["response_format"] == {"type": "json_object"}
    roles = [message["role"] for message in payload["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert payload["messages"][-1]["content"] == QUERY
    assert json.loads(payload["messages"][2]["content"])["intent"] == "discovery"


async def test_rate_limit_falls_back_then_cools_down_without_http():
    recorder = Recorder(rate_limited)
    clock = FakeClock()
    first, second = await parse(recorder, [QUERY, OTHER_QUERY], clock)
    assert first[0].parser == "rules"
    assert first[1] == "HTTP 429"
    assert second[0].parser == "rules"
    assert second[1] == "cooling down after rate limit"
    assert len(recorder.requests) == 1


async def test_requests_resume_after_retry_after_elapses():
    recorder = Recorder(rate_limited)
    clock = FakeClock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        llm = LlmParser(client, make_settings(llm_rpm=60), clock)
        assert (await parse_request(QUERY, llm))[1] == "HTTP 429"
        assert (await parse_request(OTHER_QUERY, llm))[1] == "cooling down after rate limit"
        clock.advance(13)
        assert (await parse_request(OTHER_QUERY, llm))[1] == "HTTP 429"
    assert len(recorder.requests) == 2


async def test_timeout_falls_back_to_rules():
    recorder = Recorder(times_out)
    [(parsed, reason)] = await parse(recorder, [QUERY])
    assert reason == "timeout"
    assert parsed.parser == "rules"
    assert parsed.dish == "dosa"
    assert parsed.max_price_inr == 200


async def test_http_error_status_is_reported():
    [(parsed, reason)] = await parse(Recorder(server_error), [QUERY])
    assert reason == "HTTP 500"
    assert parsed.parser == "rules"


@pytest.mark.parametrize("responder", [not_json, body_not_json])
async def test_invalid_json_falls_back(responder):
    [(parsed, reason)] = await parse(Recorder(responder), [QUERY])
    assert reason == "invalid JSON"
    assert parsed.parser == "rules"


@pytest.mark.parametrize("responder", [wrong_shape, missing_choices])
async def test_unexpected_shape_falls_back(responder):
    [(parsed, reason)] = await parse(Recorder(responder), [QUERY])
    assert reason == "unexpected shape"
    assert parsed.parser == "rules"


async def test_empty_bucket_falls_back_without_http():
    recorder = Recorder(ok)
    first, second = await parse(recorder, [QUERY, OTHER_QUERY], llm_rpm=1)
    assert first[1] is None
    assert second[1] == "local rate limit"
    assert second[0].parser == "rules"
    assert len(recorder.requests) == 1


async def test_bucket_refills_over_time():
    recorder = Recorder(ok)
    clock = FakeClock()
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        llm = LlmParser(client, make_settings(llm_rpm=6), clock)
        for index in range(6):
            assert (await parse_request(f"dosa number {index}", llm))[1] is None
        assert (await parse_request("dosa number 7", llm))[1] == "local rate limit"
        clock.advance(10)
        assert (await parse_request("dosa number 8", llm))[1] is None
    assert len(recorder.requests) == 7


async def test_cache_hit_makes_no_http_request():
    recorder = Recorder(ok)
    first, second, third = await parse(
        recorder, [QUERY, QUERY, "  GET me a   vegetarian dosa UNDER ₹200 quickly "], llm_rpm=1
    )
    assert len(recorder.requests) == 1
    assert second[1] is None
    assert second[0] == first[0]
    assert third[0].parser == "llm"
    assert third[1] is None


async def test_cache_evicts_oldest_entry():
    recorder = Recorder(ok)
    queries = [f"dosa number {index}" for index in range(3)]
    async with httpx.AsyncClient(transport=httpx.MockTransport(recorder)) as client:
        llm = LlmParser(client, make_settings(llm_cache_size=2, llm_rpm=60), FakeClock())
        for query in queries:
            await parse_request(query, llm)
        assert len(recorder.requests) == 3
        await parse_request(queries[2], llm)
        assert len(recorder.requests) == 3
        await parse_request(queries[0], llm)
        assert len(recorder.requests) == 4


async def test_failures_are_not_cached():
    recorder = Recorder(server_error)
    await parse(recorder, [QUERY, QUERY], llm_rpm=60)
    assert len(recorder.requests) == 2


async def test_no_llm_returns_rules_without_reason():
    parsed, reason = await parse_request(QUERY, None)
    assert reason is None
    assert parsed.parser == "rules"
