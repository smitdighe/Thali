from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

SCHEMA_VERSION = "1.0"

Intent = Literal["discovery", "decision", "information", "clarification", "action"]
Diet = Literal["veg", "vegan", "egg", "non_veg"]
ProviderStatus = Literal["ok", "timeout", "error", "malformed", "circuit_open"]
Factor = Literal["rating", "price", "eta"]
FaultMode = Literal["ok", "slow", "timeout", "error", "malformed", "partial"]
BreakerState = Literal["closed", "open", "half_open"]


class RecommendRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class Span(BaseModel):
    field: str
    text: str
    start: int
    end: int
    source: Literal["rules", "llm"]


class ParsedRequest(BaseModel):
    intent: Intent
    dish: str | None = None
    cuisine: str | None = None
    ingredients: list[str] = Field(default_factory=list)
    diet: Diet | None = None
    max_price_inr: int | None = None
    max_eta_min: int | None = None
    min_rating: float | None = None
    rating_preference: Literal["high"] | None = None
    price_preference: Literal["low"] | None = None
    speed_preference: Literal["fast"] | None = None
    location: str | None = None
    other_preferences: list[str] = Field(default_factory=list)
    spans: list[Span] = Field(default_factory=list)
    missing: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    parser: Literal["rules", "llm"] = "rules"


class Offer(BaseModel):
    label: str
    kind: Literal["percent", "flat", "unknown"]
    percent: float | None = None
    amount_paise: int | None = None
    max_discount_paise: int | None = None
    min_order_paise: int | None = None


class Listing(BaseModel):
    listing_id: str
    provider: str
    provider_label: str
    restaurant: str
    area: str | None = None
    item: str
    cuisines: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    diet: Diet | None = None
    price_paise: int | None = None
    offer: Offer | None = None
    effective_price_paise: int | None = None
    rating: float | None = None
    rating_count: int | None = None
    eta_min_low: int | None = None
    eta_min_high: int | None = None
    missing_fields: list[str] = Field(default_factory=list)


class DroppedRecord(BaseModel):
    provider: str
    record_ref: str | None = None
    reason: str


class ProviderReport(BaseModel):
    name: str
    label: str
    status: ProviderStatus
    http_status: int | None = None
    latency_ms: int = 0
    attempts: int = 0
    records_received: int = 0
    records_used: int = 0
    records_dropped: int = 0
    schema_seen: str | None = None
    message: str | None = None


class FactorScore(BaseModel):
    factor: Factor
    value: float
    weight: float
    points: float


class ScoredListing(BaseModel):
    listing: Listing
    feasible: bool
    violations: list[str] = Field(default_factory=list)
    score: float
    factors: list[FactorScore] = Field(default_factory=list)
    bonus: float = 0.0
    matched_preferences: list[str] = Field(default_factory=list)


class OptionResult(BaseModel):
    option_id: str
    restaurant: str
    area: str | None = None
    item: str
    feasible: bool
    rank: int | None = None
    score: float
    best: ScoredListing
    listings: list[ScoredListing]


class Recommendation(BaseModel):
    option: OptionResult
    summary: str
    reasons: list[str]
    comparison: str | None = None
    cheaper_alternative: str | None = None
    also_on: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class DataQuality(BaseModel):
    records_received: int = 0
    records_dropped: int = 0
    duplicates_removed: int = 0
    merged_options: int = 0
    listings_with_missing_fields: int = 0


class Trace(BaseModel):
    parse_ms: float = 0.0
    fetch_ms: float = 0.0
    rank_ms: float = 0.0
    total_ms: float = 0.0


class RecommendResponse(BaseModel):
    schema_version: str = SCHEMA_VERSION
    request_id: str
    query: str
    parsed: ParsedRequest
    clarification: str | None = None
    recommendation: Recommendation | None = None
    ranked: list[OptionResult] = Field(default_factory=list)
    excluded: list[OptionResult] = Field(default_factory=list)
    closest: list[OptionResult] = Field(default_factory=list)
    providers: list[ProviderReport] = Field(default_factory=list)
    dropped: list[DroppedRecord] = Field(default_factory=list)
    data_quality: DataQuality = Field(default_factory=DataQuality)
    warnings: list[str] = Field(default_factory=list)
    degraded: bool = False
    trace: Trace = Field(default_factory=Trace)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    llm_enabled: bool
    llm_model: str | None = None
    breakers: dict[str, BreakerState] = Field(default_factory=dict)


class ProviderSearch(BaseModel):
    query: str = ""
    area: str | None = None


class ProviderResult(BaseModel):
    report: ProviderReport
    listings: list[Listing] = Field(default_factory=list)
    dropped: list[DroppedRecord] = Field(default_factory=list)


class OptionGroup(BaseModel):
    option_id: str
    restaurant: str
    area: str | None = None
    item: str
    listings: list[Listing]


class DedupeStats(BaseModel):
    duplicates_removed: int = 0
    merged_options: int = 0


class RankOutcome(BaseModel):
    ranked: list[OptionResult] = Field(default_factory=list)
    excluded: list[OptionResult] = Field(default_factory=list)
    closest: list[OptionResult] = Field(default_factory=list)
