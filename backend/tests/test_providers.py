import asyncio
import time

import httpx
import pytest

from thali.config import Settings
from thali.models import ProviderResult, ProviderSearch
from thali.providers.base import call_provider, fetch_all
from thali.providers.bitebox import BiteboxAdapter
from thali.providers.breaker import CircuitBreaker
from thali.providers.khaana import COLUMNS, KhaanaAdapter
from thali.providers.tiffinly import TiffinlyAdapter

BITEBOX_OK = {
    "api_version": "2.1",
    "results": [
        {
            "id": "bb_1",
            "restaurant": {"name": "Dum Pukht House", "area": "Andheri West"},
            "dish": "Veg Dum Biryani",
            "price": 289.0,
            "rating": 4.6,
            "ratings_count": 2140,
            "eta_minutes": 24,
            "is_veg": True,
            "cuisine": ["Biryani"],
            "offer": None,
        },
        {"restaurant": {"name": "Cafe"}, "dish": ""},
    ],
}
TIFFINLY_OK = {
    "meta": {"schema": "tiffinly.v3"},
    "data": {
        "outlets": [
            {
                "outletId": "T-1",
                "outletName": "Lucknowi Degh",
                "locality": "Bandra (W)",
                "score": "9.4/10",
                "votes": "620",
                "deliveryTime": "25-35 mins",
                "menu": [{"sku": "T-1-1", "title": "Subz Dum Biryani", "pricePaise": 32000}],
            }
        ]
    },
}
KHAANA_OK = ",".join(COLUMNS) + "\nA-1,Biryani Junction,Powai,Veg Biryani,Y,175,3.5,380,Biryani\n"
SEARCH = ProviderSearch(query="biryani")


@pytest.fixture
def settings() -> Settings:
    return Settings(
        _env_file=None,
        provider_timeout_ms=200,
        fetch_deadline_ms=1000,
        retry_backoff_min_ms=1,
        retry_backoff_max_ms=3,
    )


def new_breaker() -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, cooldown_s=30.0)


class Script:
    def __init__(self, *responses: httpx.Response) -> None:
        self.responses = list(responses)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        index = min(len(self.requests), len(self.responses)) - 1
        return self.responses[index]


def client_for(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://mock")


def deadline_in(seconds: float = 1.0) -> float:
    return time.monotonic() + seconds


def ok_response() -> httpx.Response:
    return httpx.Response(200, json=BITEBOX_OK)


def error_response() -> httpx.Response:
    return httpx.Response(503, json={"error": "upstream unavailable"})


async def run(handler, settings, breaker=None, adapter=None, deadline=None):
    async with client_for(handler) as client:
        return await call_provider(
            adapter or BiteboxAdapter(),
            client,
            SEARCH,
            breaker or new_breaker(),
            settings,
            deadline or deadline_in(),
            time.monotonic(),
        )


async def test_ok(settings):
    script = Script(ok_response())
    result = await run(script, settings)
    report = result.report
    assert report.status == "ok"
    assert report.attempts == 1
    assert report.http_status == 200
    assert report.name == "bitebox" and report.label == "Bitebox"
    assert report.schema_seen == "bitebox 2.1"
    assert (report.records_received, report.records_used, report.records_dropped) == (2, 1, 1)
    assert report.message is None
    assert len(result.listings) == 1 and len(result.dropped) == 1
    assert len(script.requests) == 1


async def test_retry_after_503_then_ok(settings):
    script = Script(error_response(), ok_response())
    breaker = new_breaker()
    result = await run(script, settings, breaker)
    assert result.report.status == "ok"
    assert result.report.attempts == 2
    assert len(script.requests) == 2
    assert breaker.failures == 0


async def test_503_twice_is_error(settings):
    script = Script(error_response(), error_response())
    breaker = new_breaker()
    result = await run(script, settings, breaker)
    assert result.report.status == "error"
    assert result.report.attempts == 2
    assert result.report.http_status == 503
    assert result.listings == []
    assert breaker.failures == 1


async def test_4xx_is_not_retried(settings):
    script = Script(httpx.Response(404, text="nope"))
    result = await run(script, settings)
    assert result.report.status == "error"
    assert result.report.attempts == 1
    assert result.report.http_status == 404
    assert len(script.requests) == 1


async def test_connection_error_is_retried(settings):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            raise httpx.ConnectError("refused", request=request)
        return ok_response()

    result = await run(handler, settings)
    assert result.report.status == "ok"
    assert result.report.attempts == 2


async def test_connection_error_twice_has_no_http_status(settings):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    result = await run(handler, settings)
    assert result.report.status == "error"
    assert result.report.attempts == 2
    assert result.report.http_status is None


async def test_slow_handler_times_out_without_retry(settings):
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        await asyncio.sleep(2)
        return ok_response()

    started = time.monotonic()
    result = await run(handler, settings)
    assert result.report.status == "timeout"
    assert result.report.attempts == 1
    assert len(calls) == 1
    assert time.monotonic() - started < 1.0
    assert result.report.latency_ms >= 150


async def test_garbage_body_is_malformed(settings):
    script = Script(httpx.Response(200, text="<html>oops</html>"))
    breaker = new_breaker()
    result = await run(script, settings, breaker)
    assert result.report.status == "malformed"
    assert result.report.attempts == 1
    assert result.report.http_status == 200
    assert result.report.message
    assert breaker.failures == 1


async def test_unsupported_schema_is_malformed(settings):
    script = Script(httpx.Response(200, json={"api_version": "3.0", "results": []}))
    result = await run(script, settings)
    assert result.report.status == "malformed"
    assert result.report.message == "unsupported api_version 3.0"


async def test_breaker_opens_after_three_failures_and_skips_request(settings):
    script = Script(error_response())
    breaker = new_breaker()
    for _ in range(3):
        result = await run(script, settings, breaker, deadline=deadline_in(5))
        assert result.report.status == "error"
    sent = len(script.requests)
    assert breaker.state == "open"

    skipped = await run(script, settings, breaker)
    assert skipped.report.status == "circuit_open"
    assert skipped.report.attempts == 0
    assert skipped.report.message == ("skipped after 3 consecutive failures; retrying in 30 s")
    assert skipped.listings == []
    assert len(script.requests) == sent


async def test_expired_deadline_skips_request(settings):
    script = Script(ok_response())
    result = await run(script, settings, deadline=time.monotonic() - 1)
    assert result.report.status == "timeout"
    assert result.report.attempts == 0
    assert script.requests == []


async def test_no_retry_when_deadline_cannot_cover_backoff(settings):
    settings.retry_backoff_min_ms = 500
    settings.retry_backoff_max_ms = 500
    script = Script(error_response(), ok_response())
    result = await run(script, settings, deadline=deadline_in(0.2))
    assert result.report.status == "error"
    assert result.report.attempts == 1
    assert len(script.requests) == 1


async def collect(adapters, client, breakers, settings):
    results = [result async for result in fetch_all(adapters, client, SEARCH, breakers, settings)]
    order = [adapter.name for adapter in adapters]

    def position(result: ProviderResult) -> int:
        return order.index(result.report.name)

    return sorted(results, key=position)


async def test_fetch_all_runs_providers_concurrently(settings):
    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "bitebox" in path:
            return ok_response()
        if "tiffinly" in path:
            await asyncio.sleep(2)
            return httpx.Response(200, json=TIFFINLY_OK)
        return httpx.Response(200, text=KHAANA_OK)

    adapters = [BiteboxAdapter(), TiffinlyAdapter(), KhaanaAdapter()]
    breakers = {adapter.name: new_breaker() for adapter in adapters}
    started = time.monotonic()
    async with client_for(handler) as client:
        results = await collect(adapters, client, breakers, settings)
    assert time.monotonic() - started < 1.0
    assert [r.report.name for r in results] == ["bitebox", "tiffinly", "khaana"]
    assert [r.report.status for r in results] == ["ok", "timeout", "ok"]
    assert results[2].listings[0].listing_id == "khaana:A-1"
    assert breakers["tiffinly"].failures == 1
    assert breakers["bitebox"].failures == 0


async def test_fetch_all_tiffinly_ok(settings):
    script = Script(httpx.Response(200, json=TIFFINLY_OK))
    adapters = [TiffinlyAdapter()]
    async with client_for(script) as client:
        results = await collect(adapters, client, {"tiffinly": new_breaker()}, settings)
    assert results[0].report.status == "ok"
    assert results[0].listings[0].area == "Bandra West"
    assert script.requests[0].method == "POST"
