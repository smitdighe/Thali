import re

import httpx
import pytest
from conftest import MAIN_QUERY
from fastapi.testclient import TestClient

from thali.config import Settings
from thali.main import create_app

RECOMMEND = "/api/v1/recommend"
HEALTH = "/api/v1/health"
SERVER_TIMING = re.compile(
    r"^parse;dur=\d+(\.\d+)?, fetch;dur=\d+(\.\d+)?, rank;dur=\d+(\.\d+)?, total;dur=\d+(\.\d+)?$"
)


def rate_limited(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(429, headers={"Retry-After": "12"}, json={"error": "slow down"})


def test_empty_query_is_rejected(client: TestClient) -> None:
    assert client.post(RECOMMEND, json={"query": ""}).status_code == 422


def test_blank_query_is_rejected(client: TestClient) -> None:
    assert client.post(RECOMMEND, json={"query": "   "}).status_code == 422


def test_missing_query_is_rejected(client: TestClient) -> None:
    assert client.post(RECOMMEND, json={}).status_code == 422


def test_overlong_query_is_rejected(client: TestClient) -> None:
    assert client.post(RECOMMEND, json={"query": "a" * 501}).status_code == 422


def test_query_at_limit_is_accepted(client: TestClient) -> None:
    assert client.post(RECOMMEND, json={"query": "a" * 500}).status_code == 200


def test_health_shape(client: TestClient) -> None:
    response = client.get(HEALTH)
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "llm_enabled": False,
        "llm_model": None,
        "breakers": {"bitebox": "closed", "tiffinly": "closed", "khaana": "closed"},
    }


def test_health_reports_llm_when_key_is_set(settings: Settings) -> None:
    keyed = settings.model_copy(update={"groq_api_key": "test-key"})
    transport = httpx.MockTransport(rate_limited)
    with TestClient(create_app(keyed, llm_transport=transport)) as c:
        body = c.get(HEALTH).json()
    assert body["llm_enabled"] is True
    assert body["llm_model"] == settings.llm_model


def test_llm_failure_falls_back_with_warning(settings: Settings) -> None:
    keyed = settings.model_copy(update={"groq_api_key": "test-key"})
    transport = httpx.MockTransport(rate_limited)
    with TestClient(create_app(keyed, llm_transport=transport)) as c:
        body = c.post(RECOMMEND, json={"query": MAIN_QUERY}).json()
    assert body["parsed"]["parser"] == "rules"
    assert body["degraded"] is True
    assert (
        "The language model was unavailable (HTTP 429), "
        "so the request was read with the rule-based parser."
    ) in body["warnings"]
    assert body["recommendation"] is not None


def test_request_id_is_generated(client: TestClient) -> None:
    response = client.post(RECOMMEND, json={"query": MAIN_QUERY})
    request_id = response.headers["X-Request-ID"]
    assert re.fullmatch(r"[0-9a-f]{12}", request_id)
    assert response.json()["request_id"] == request_id


def test_request_id_is_echoed(client: TestClient) -> None:
    response = client.post(
        RECOMMEND, json={"query": MAIN_QUERY}, headers={"X-Request-ID": "abc-123"}
    )
    assert response.headers["X-Request-ID"] == "abc-123"
    assert response.json()["request_id"] == "abc-123"


def test_request_id_is_set_on_other_routes(client: TestClient) -> None:
    response = client.get(HEALTH, headers={"X-Request-ID": "health-1"})
    assert response.headers["X-Request-ID"] == "health-1"


def test_server_timing_is_present(client: TestClient) -> None:
    response = client.post(RECOMMEND, json={"query": MAIN_QUERY})
    assert SERVER_TIMING.match(response.headers["Server-Timing"])


def test_fault_api_is_reachable_under_mock(client: TestClient) -> None:
    assert client.get("/mock/_faults").json() == {
        "bitebox": "ok",
        "tiffinly": "ok",
        "khaana": "ok",
    }


def test_unhandled_error_returns_internal_error(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr("thali.api.recommend", boom)
    with TestClient(create_app(settings), raise_server_exceptions=False) as c:
        response = c.post(RECOMMEND, json={"query": MAIN_QUERY}, headers={"X-Request-ID": "err-1"})
    assert response.status_code == 500
    assert response.json() == {"error": "internal_error", "request_id": "err-1"}
    assert response.headers["X-Request-ID"] == "err-1"
