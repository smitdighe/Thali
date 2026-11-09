from dataclasses import dataclass
lazy import time
lazy from collections.abc import AsyncIterator

lazy import httpx
lazy from pydantic import BaseModel

lazy from thali.config import Settings
lazy from thali.models import (
    DataQuality,
    DedupeStats,
    DroppedRecord,
    Listing,
    ParsedRequest,
    ProviderReport,
    ProviderResult,
    ProviderSearch,
    RankOutcome,
    RecommendResponse,
    StreamParsed,
    Trace,
)
lazy from thali.observability import log_event
lazy from thali.parsing import LlmParser, parse_request
lazy from thali.pipeline.dedupe import group_listings
lazy from thali.pipeline.explain import explain, with_why_not
lazy from thali.pipeline.rank import rank
lazy from thali.pipeline.whatif import what_ifs
lazy from thali.providers.base import ProviderAdapter, fetch_all
lazy from thali.providers.breaker import CircuitBreaker
lazy from thali.text import AREAS

CLARIFY_PROMPT = "What would you like to eat? For example: “veg biryani under ₹300 in 30 minutes”."


@dataclass
class EngineDeps:
    settings: Settings
    provider_client: httpx.AsyncClient
    adapters: list[ProviderAdapter]
    breakers: dict[str, CircuitBreaker]
    llm: LlmParser | None


def elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


def rounded_ms(value: float) -> float:
    return round(value, 1)


def sentence(note: str) -> str:
    return note if note.endswith((".", "!", "?")) else f"{note}."


def clarification_text(parsed: ParsedRequest) -> str:
    return " ".join([*map(sentence, parsed.notes), CLARIFY_PROMPT])


@dataclass
class PipelineContext:
    parsed: ParsedRequest | None = None
    session: str | None = None


def search_for(parsed: ParsedRequest, session: str | None = None) -> ProviderSearch:
    area = parsed.location if parsed.location in AREAS else None
    return ProviderSearch(query=parsed.dish or parsed.cuisine or "", area=area, session=session)


def provider_warning(report: ProviderReport, deps: EngineDeps) -> str | None:
    label = report.label
    if report.status == "timeout":
        seconds = deps.settings.provider_timeout_ms / 1000
        return f"{label} didn't respond within {seconds:g} s, so its listings weren't compared."
    if report.status == "error":
        cause = report.http_status if report.http_status is not None else "a connection error"
        return (
            f"{label} returned an error ({cause}) after {report.attempts} attempts, "
            "so its listings weren't compared."
        )
    if report.status == "malformed":
        return (
            f"{label} sent a response that couldn't be read ({report.message}), "
            "so its listings weren't compared."
        )
    if report.status == "circuit_open":
        wait = deps.breakers[report.name].retry_in_s()
        return f"{label} is paused after repeated failures; retrying in {wait:.0f} s."
    return None


def build_warnings(
    parsed: ParsedRequest,
    reports: list[ProviderReport],
    listings: list[Listing],
    outcome: RankOutcome | None,
    fallback: str | None,
    deps: EngineDeps,
) -> list[str]:
    warnings = [text for report in reports if (text := provider_warning(report, deps))]
    if deps.llm is not None and fallback is not None:
        warnings.append(
            f"The language model was unavailable ({fallback}), "
            "so the request was read with the rule-based parser."
        )
    if outcome is None:
        return warnings
    if parsed.intent == "action":
        warnings.append("Placing orders isn't supported here; this is the option that fits best.")
    if (
        parsed.location is not None
        and listings
        and all(listing.area != parsed.location for listing in listings)
    ):
        warnings.append(
            f"No source lists restaurants in {parsed.location}. "
            f"Covered areas: {', '.join(sorted(AREAS))}."
        )
    if listings and not outcome.ranked:
        warnings.append(
            "Nothing matched every requirement. The closest options are listed with what they miss."
        )
    if reports and all(report.status != "ok" for report in reports):
        warnings.append("No source responded. Try again in a few seconds.")
    return warnings


def data_quality_for(
    reports: list[ProviderReport],
    dropped: list[DroppedRecord],
    listings: list[Listing],
    stats: DedupeStats,
) -> DataQuality:
    return DataQuality(
        records_received=sum(report.records_received for report in reports),
        records_dropped=len(dropped),
        duplicates_removed=stats.duplicates_removed,
        merged_options=stats.merged_options,
        listings_with_missing_fields=sum(1 for listing in listings if listing.missing_fields),
    )


def log_provider(report: ProviderReport) -> None:
    log_event(
        "provider.done",
        provider=report.name,
        status=report.status,
        attempts=report.attempts,
        latency_ms=report.latency_ms,
        records_used=report.records_used,
        records_dropped=report.records_dropped,
    )


def clarification_response(
    query: str,
    parsed: ParsedRequest,
    fallback: str | None,
    deps: EngineDeps,
    request_id: str,
    trace: Trace,
) -> RecommendResponse:
    return RecommendResponse(
        request_id=request_id,
        query=query,
        parsed=parsed,
        clarification=clarification_text(parsed),
        warnings=build_warnings(parsed, [], [], None, fallback, deps),
        degraded=deps.llm is not None and fallback is not None,
        trace=trace,
    )


async def parse_for(
    query: str, deps: EngineDeps, context: PipelineContext | None
) -> tuple[ParsedRequest, str | None]:
    if context is not None and context.parsed is not None:
        return context.parsed, None
    return await parse_request(query, deps.llm)


async def collect_results(
    deps: EngineDeps, search: ProviderSearch, results: list[ProviderResult]
) -> AsyncIterator[ProviderReport]:
    async for result in fetch_all(
        deps.adapters, deps.provider_client, search, deps.breakers, deps.settings
    ):
        results.append(result)
        log_provider(result.report)
        yield result.report


def in_adapter_order(results: list[ProviderResult], deps: EngineDeps) -> list[ProviderResult]:
    order = [adapter.name for adapter in deps.adapters]

    def position(result: ProviderResult) -> int:
        return order.index(result.report.name)

    return sorted(results, key=position)


async def run_pipeline(
    query: str, deps: EngineDeps, request_id: str, context: PipelineContext | None = None
) -> AsyncIterator[tuple[str, BaseModel]]:
    started = time.perf_counter()
    parsed, fallback = await parse_for(query, deps, context)
    parse_ms = elapsed_ms(started)
    log_event("parse.done", parser=parsed.parser, fallback=fallback, ms=rounded_ms(parse_ms))

    if parsed.intent == "clarification":
        trace = Trace(parse_ms=rounded_ms(parse_ms), total_ms=rounded_ms(elapsed_ms(started)))
        final = clarification_response(query, parsed, fallback, deps, request_id, trace)
        yield "parsed", StreamParsed(parsed=parsed, clarification=final.clarification)
        yield "done", final
        return

    yield "parsed", StreamParsed(parsed=parsed)

    fetch_started = time.perf_counter()
    session = context.session if context is not None else None
    collected: list[ProviderResult] = []
    async for report in collect_results(deps, search_for(parsed, session), collected):
        yield "provider", report
    fetch_ms = elapsed_ms(fetch_started)
    results = in_adapter_order(collected, deps)
    reports = [result.report for result in results]

    rank_started = time.perf_counter()
    listings = [listing for result in results for listing in result.listings]
    dropped = [record for result in results for record in result.dropped]
    groups, stats = group_listings(listings)
    outcome = with_why_not(rank(groups, parsed))
    recommendation = explain(outcome, parsed, reports)
    rank_ms = elapsed_ms(rank_started)
    what_if_started = time.perf_counter()
    pick = recommendation.option.best.listing if recommendation is not None else None
    what_if = what_ifs(groups, parsed, pick)
    what_if_ms = elapsed_ms(what_if_started)
    log_event("rank.done", ranked=len(outcome.ranked), excluded=len(outcome.excluded))

    yield (
        "done",
        RecommendResponse(
            request_id=request_id,
            query=query,
            parsed=parsed,
            recommendation=recommendation,
            ranked=outcome.ranked,
            excluded=outcome.excluded,
            closest=outcome.closest,
            providers=reports,
            dropped=dropped,
            data_quality=data_quality_for(reports, dropped, listings, stats),
            warnings=build_warnings(parsed, reports, listings, outcome, fallback, deps),
            degraded=any(report.status != "ok" for report in reports)
            or (deps.llm is not None and fallback is not None),
            trace=Trace(
                parse_ms=rounded_ms(parse_ms),
                fetch_ms=rounded_ms(fetch_ms),
                rank_ms=rounded_ms(rank_ms),
                what_if_ms=rounded_ms(what_if_ms),
                total_ms=rounded_ms(elapsed_ms(started)),
            ),
            what_if=what_if,
        ),
    )


async def recommend(
    query: str, deps: EngineDeps, request_id: str, context: PipelineContext | None = None
) -> RecommendResponse:
    final: RecommendResponse | None = None
    async for _name, payload in run_pipeline(query, deps, request_id, context):
        if isinstance(payload, RecommendResponse):
            final = payload
    if final is None:
        raise RuntimeError("pipeline finished without a response")
    return final
