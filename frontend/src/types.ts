export type Intent = "discovery" | "decision" | "information" | "clarification" | "action";
export type Diet = "veg" | "vegan" | "egg" | "non_veg";
export type ProviderStatus = "ok" | "timeout" | "error" | "malformed" | "circuit_open";
export type Factor = "rating" | "price" | "eta";
export type FaultMode = "ok" | "slow" | "timeout" | "error" | "malformed" | "partial";
export type ProviderName = "bitebox" | "tiffinly" | "khaana";
export type FaultState = Record<ProviderName, FaultMode>;

export interface Span { field: string; text: string; start: number; end: number; source: "rules" | "llm" }

export interface ParsedRequest {
  intent: Intent; dish: string | null; cuisine: string | null; ingredients: string[]; diet: Diet | null;
  max_price_inr: number | null; max_eta_min: number | null; min_rating: number | null;
  rating_preference: "high" | null; price_preference: "low" | null; speed_preference: "fast" | null;
  location: string | null; other_preferences: string[]; spans: Span[]; missing: string[]; notes: string[];
  parser: "rules" | "llm";
}

export interface Offer {
  label: string; kind: "percent" | "flat" | "unknown"; percent: number | null; amount_paise: number | null;
  max_discount_paise: number | null; min_order_paise: number | null;
}

export interface Listing {
  listing_id: string; provider: string; provider_label: string; restaurant: string; area: string | null;
  item: string; cuisines: string[]; tags: string[]; diet: Diet | null; price_paise: number | null;
  offer: Offer | null; effective_price_paise: number | null; rating: number | null; rating_count: number | null;
  eta_min_low: number | null; eta_min_high: number | null; missing_fields: string[];
}

export interface DroppedRecord { provider: string; record_ref: string | null; reason: string }

export interface ProviderReport {
  name: string; label: string; status: ProviderStatus; http_status: number | null; latency_ms: number;
  attempts: number; records_received: number; records_used: number; records_dropped: number;
  schema_seen: string | null; message: string | null;
}

export interface FactorScore { factor: Factor; value: number; weight: number; points: number }

export interface ScoredListing {
  listing: Listing; feasible: boolean; violations: string[]; score: number; factors: FactorScore[];
  bonus: number; matched_preferences: string[];
}

export interface OptionResult {
  option_id: string; restaurant: string; area: string | null; item: string; feasible: boolean;
  rank: number | null; score: number; best: ScoredListing; listings: ScoredListing[];
}

export interface Recommendation {
  option: OptionResult; summary: string; reasons: string[]; comparison: string | null;
  cheaper_alternative: string | null; also_on: string[]; caveats: string[];
}

export interface DataQuality {
  records_received: number; records_dropped: number; duplicates_removed: number; merged_options: number;
  listings_with_missing_fields: number;
}

export interface Trace { parse_ms: number; fetch_ms: number; rank_ms: number; total_ms: number }

export interface RecommendResponse {
  schema_version: string; request_id: string; query: string; parsed: ParsedRequest;
  clarification: string | null; recommendation: Recommendation | null; ranked: OptionResult[];
  excluded: OptionResult[]; closest: OptionResult[]; providers: ProviderReport[]; dropped: DroppedRecord[];
  data_quality: DataQuality; warnings: string[]; degraded: boolean; trace: Trace;
}

export interface HealthResponse {
  status: "ok"; llm_enabled: boolean; llm_model: string | null;
  breakers: Record<string, "closed" | "open" | "half_open">;
}
