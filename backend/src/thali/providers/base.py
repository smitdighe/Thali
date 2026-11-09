import logging
from typing import Protocol
lazy import asyncio
lazy import random
lazy import time
lazy from collections.abc import AsyncIterator

from pydantic import BaseModel, Field
lazy import httpx

from thali.models import DroppedRecord, Listing
lazy from thali.config import Settings
lazy from thali.models import (
    Attempt,
    AttemptOutcome,
    ProviderReport,
    ProviderResult,
    ProviderSearch,
    ProviderStatus,
)
lazy from thali.pipeline.normalize import effective_price, missing_fields
lazy from thali.providers.breaker import CircuitBreaker

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 2


class MalformedPayload(Exception):
    pass


class NormalizedBatch(BaseModel):
    listings: list[Listing] = Field(default_factory=list)
    dropped: list[DroppedRecord] = Field(default_factory=list)
    records_received: int = 0
    schema_seen: str | None = None


class ProviderAdapter(Protocol):
    name: str
    label: str

    async def fetch(self, client: httpx.AsyncClient, search: ProviderSearch) -> httpx.Response: ...

    def normalize(self, response: httpx.Response) -> NormalizedBatch: ...


def build_listing(**values: object) -> Listing:
    listing = Listing(**values)
    listing.effective_price_paise = effective_price(listing.price_paise, listing.offer)
    listing.missing_fields = missing_fields(listing)
    return listing


def read_json(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError as exc:
        raise MalformedPayload("response is not valid JSON") from exc


class _Failure(Exception):
    def __init__(
        self,
        status: ProviderStatus,
        message: str,
        outcome: AttemptOutcome,
        http_status: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.outcome = outcome
        self.message = message
        self.http_status = http_status
        self.retryable = retryable


def _classify(adapter: ProviderAdapter, response: httpx.Response) -> NormalizedBatch:
    code = response.status_code
    if code >= 500:
        raise _Failure("error", f"HTTP {code}", "http_error", code, retryable=True)
    if not 200 <= code < 300:
        raise _Failure("error", f"HTTP {code}", "http_error", code)
    try:
        return adapter.normalize(response)
    except MalformedPayload as exc:
        raise _Failure("malformed", str(exc), "malformed", code) from exc
    except Exception as exc:
        logger.exception("%s normalize crashed", adapter.name)
        raise _Failure(
            "malformed", f"unreadable payload: {type(exc).__name__}", "malformed", code
        ) from exc


async def _attempt(
    adapter: ProviderAdapter,
    client: httpx.AsyncClient,
    search: ProviderSearch,
    timeout_s: float,
) -> tuple[NormalizedBatch, int]:
    try:
        async with asyncio.timeout(timeout_s):
            response = await adapter.fetch(client, search)
    except TimeoutError as exc:
        raise _Failure(
            "timeout", f"no response within {timeout_s * 1000:.0f} ms", "timeout"
        ) from exc
    except httpx.TransportError as exc:
        raise _Failure(
            "error",
            f"connection failed: {type(exc).__name__}",
            "connection_error",
            retryable=True,
        ) from exc
    except Exception as exc:
        logger.exception("%s fetch crashed", adapter.name)
        raise _Failure(
            "error", f"request failed: {type(exc).__name__}", "connection_error"
        ) from exc
    return _classify(adapter, response), response.status_code


def _elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _since_ms(origin: float, moment: float) -> float:
    return round((moment - origin) * 1000, 1)


def _log_attempt(
    report: ProviderReport,
    origin: float,
    started: float,
    outcome: AttemptOutcome,
    http_status: int | None,
) -> None:
    report.attempt_log.append(
        Attempt(
            start_ms=_since_ms(origin, started),
            duration_ms=round((time.monotonic() - started) * 1000, 1),
            outcome=outcome,
            http_status=http_status,
        )
    )


async def call_provider(
    adapter: ProviderAdapter,
    client: httpx.AsyncClient,
    search: ProviderSearch,
    breaker: CircuitBreaker,
    settings: Settings,
    deadline: float,
    origin: float,
) -> ProviderResult:
    started = time.monotonic()
    report = ProviderReport(name=adapter.name, label=adapter.label, status="ok")
    if not breaker.allow():
        report.attempt_log.append(
            Attempt(
                start_ms=_since_ms(origin, started),
                duration_ms=0.0,
                outcome="skipped",
                http_status=None,
            )
        )
        report.status = "circuit_open"
        report.message = (
            f"skipped after {breaker.failures} consecutive failures; "
            f"retrying in {breaker.retry_in_s():.0f} s"
        )
        return ProviderResult(report=report)

    batch: NormalizedBatch | None = None
    http_status: int | None = None
    failure: _Failure | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            failure = _Failure("timeout", "fetch deadline reached", "timeout")
            break
        report.attempts = attempt
        attempt_started = time.monotonic()
        try:
            batch, http_status = await _attempt(
                adapter, client, search, min(settings.provider_timeout_ms / 1000, remaining)
            )
            _log_attempt(report, origin, attempt_started, "ok", http_status)
            failure = None
            break
        except _Failure as exc:
            failure = exc
            _log_attempt(report, origin, attempt_started, exc.outcome, exc.http_status)
        if not failure.retryable or attempt == MAX_ATTEMPTS:
            break
        pause = random.uniform(settings.retry_backoff_min_ms, settings.retry_backoff_max_ms) / 1000
        if deadline - time.monotonic() <= pause:
            break
        await asyncio.sleep(pause)

    result = ProviderResult(report=report)
    if batch is not None:
        breaker.record_success()
        report.http_status = http_status
        report.records_received = batch.records_received
        report.records_used = len(batch.listings)
        report.records_dropped = len(batch.dropped)
        report.schema_seen = batch.schema_seen
        result.listings = batch.listings
        result.dropped = batch.dropped
    else:
        breaker.record_failure()
        if failure is not None:
            report.status = failure.status
            report.http_status = failure.http_status
            report.message = failure.message
    report.latency_ms = _elapsed_ms(started)
    return result


async def fetch_all(
    adapters: list[ProviderAdapter],
    client: httpx.AsyncClient,
    search: ProviderSearch,
    breakers: dict[str, CircuitBreaker],
    settings: Settings,
) -> AsyncIterator[ProviderResult]:
    origin = time.monotonic()
    deadline = origin + settings.fetch_deadline_ms / 1000
    tasks = [
        asyncio.create_task(
            call_provider(
                adapter, client, search, breakers[adapter.name], settings, deadline, origin
            )
        )
        for adapter in adapters
    ]
    try:
        for finished in asyncio.as_completed(tasks):
            yield await finished
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
