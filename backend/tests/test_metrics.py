import pytest
from conftest import MAIN_QUERY, set_faults
from fastapi.testclient import TestClient

from thali.metrics import Metrics, nearest_rank

METRICS = "/api/v1/metrics"
RECOMMEND = "/api/v1/recommend"
PROVIDERS = ["bitebox", "tiffinly", "khaana"]


def recommend(client: TestClient, query: str = MAIN_QUERY) -> None:
    assert client.post(RECOMMEND, json={"query": query}).status_code == 200


def fetch_metrics(client: TestClient) -> dict:
    response = client.get(METRICS)
    assert response.status_code == 200
    return response.json()


def test_nearest_rank_ten_values() -> None:
    values = [float(n) for n in range(1, 11)]
    assert nearest_rank(values, 50) == 5.0
    assert nearest_rank(values, 95) == 10.0


def test_nearest_rank_single_value() -> None:
    assert nearest_rank([42.0], 50) == 42.0
    assert nearest_rank([42.0], 95) == 42.0


def test_nearest_rank_empty() -> None:
    assert nearest_rank([], 50) == 0.0
    assert nearest_rank([], 95) == 0.0


def test_nearest_rank_ignores_input_order() -> None:
    assert nearest_rank([9.0, 1.0, 5.0, 3.0, 7.0], 50) == 5.0


def test_empty_snapshot(client: TestClient) -> None:
    body = fetch_metrics(client)
    assert body["requests"] == 0
    assert body["p50_ms"] == 0.0
    assert body["recent_total_ms"] == []
    assert sorted(body["providers"]) == sorted(PROVIDERS)
    assert all(
        entry["calls"] == 0 and entry["ok_rate"] == 0.0 for entry in body["providers"].values()
    )


def test_counts_after_requests(client: TestClient) -> None:
    recommend(client)
    recommend(client)
    recommend(client, "hello")
    body = fetch_metrics(client)
    assert body["requests"] == 3
    assert body["parser"] == {"rules": 3, "llm": 0, "fallbacks": 0}
    for name in PROVIDERS:
        assert body["providers"][name]["calls"] == 2
        assert body["providers"][name]["ok_rate"] == 1.0
    set_faults(client, tiffinly="timeout")
    recommend(client)
    body = fetch_metrics(client)
    assert body["requests"] == 4
    assert body["providers"]["tiffinly"]["timeouts"] == 1
    assert body["providers"]["tiffinly"]["calls"] == 3
    assert body["providers"]["tiffinly"]["ok_rate"] == pytest.approx(0.6667, abs=1e-4)
    assert body["providers"]["bitebox"]["calls"] == 3


def test_response_shape(client: TestClient) -> None:
    for _ in range(3):
        recommend(client)
    body = fetch_metrics(client)
    assert set(body) == {"requests", "p50_ms", "p95_ms", "recent_total_ms", "parser", "providers"}
    assert set(body["parser"]) == {"rules", "llm", "fallbacks"}
    assert len(body["providers"]) == 3
    expected = {
        "calls",
        "ok_rate",
        "p50_ms",
        "p95_ms",
        "timeouts",
        "errors",
        "circuit_open",
        "breaker",
    }
    assert all(set(entry) == expected for entry in body["providers"].values())
    assert len(body["recent_total_ms"]) == min(body["requests"], 30)
    assert body["p95_ms"] >= body["p50_ms"] > 0


def test_ring_buffer_cap() -> None:
    metrics = Metrics()
    for n in range(1, 601):
        metrics.record_request(float(n), "rules", False)
    snapshot = metrics.snapshot({})
    assert snapshot.requests == 600
    assert len(snapshot.recent_total_ms) == 30
    assert snapshot.recent_total_ms[0] == 571.0
    assert snapshot.recent_total_ms[-1] == 600.0
    assert snapshot.p50_ms == 350.0
    assert snapshot.p95_ms == 575.0
    assert snapshot.parser.rules == 500
