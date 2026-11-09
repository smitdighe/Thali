import json

import pytest
from conftest import MAIN_QUERY, set_faults
from fastapi.testclient import TestClient

STREAM = "/api/v1/recommend/stream"
RECOMMEND = "/api/v1/recommend"


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events: list[tuple[str, dict]] = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        lines = block.split("\n")
        name = next(line.removeprefix("event: ") for line in lines if line.startswith("event: "))
        data = next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        events.append((name, json.loads(data)))
    return events


def stream(client: TestClient, query: str = MAIN_QUERY) -> list[tuple[str, dict]]:
    response = client.post(STREAM, json={"query": query})
    assert response.status_code == 200
    return parse_sse(response.text)


def provider_events(events: list[tuple[str, dict]]) -> dict[str, dict]:
    return {payload["name"]: payload for name, payload in events if name == "provider"}


def strip_volatile(payload: dict) -> dict:
    cleaned = {key: value for key, value in payload.items() if key not in ("request_id", "trace")}
    cleaned["providers"] = [
        {key: value for key, value in report.items() if key not in ("latency_ms", "attempt_log")}
        for report in payload["providers"]
    ]
    return cleaned


def test_event_order_and_headers(client):
    response = client.post(STREAM, json={"query": MAIN_QUERY})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["x-request-id"]
    names = [name for name, _ in parse_sse(response.text)]
    assert names == ["parsed", "provider", "provider", "provider", "done"]


def test_done_matches_recommend(client):
    events = stream(client)
    done = events[-1][1]
    plain = client.post(RECOMMEND, json={"query": MAIN_QUERY}).json()
    assert strip_volatile(done) == strip_volatile(plain)
    assert [report["name"] for report in done["providers"]] == ["bitebox", "tiffinly", "khaana"]
    assert done["recommendation"]["option"]["restaurant"] == "Lucknowi Degh"
    assert done["recommendation"]["option"]["score"] == 0.5961


def test_parsed_event_has_no_clarification_for_real_query(client):
    name, payload = stream(client)[0]
    assert name == "parsed"
    assert payload["clarification"] is None
    assert payload["parsed"]["intent"] != "clarification"


def test_timeout_provider_finishes_last(client):
    set_faults(client, tiffinly="timeout")
    events = stream(client)
    providers = [payload for name, payload in events if name == "provider"]
    assert providers[-1]["name"] == "tiffinly"
    assert providers[-1]["status"] == "timeout"
    assert [attempt["outcome"] for attempt in providers[-1]["attempt_log"]] == ["timeout"]


def test_error_provider_logs_both_attempts(client):
    set_faults(client, bitebox="error")
    log = provider_events(stream(client))["bitebox"]["attempt_log"]
    assert len(log) == 2
    assert [attempt["outcome"] for attempt in log] == ["http_error", "http_error"]
    assert [attempt["http_status"] for attempt in log] == [503, 503]
    assert log[1]["start_ms"] > log[0]["start_ms"]


def test_ok_provider_has_single_ok_attempt(client):
    for report in provider_events(stream(client)).values():
        assert len(report["attempt_log"]) == 1
        assert report["attempt_log"][0]["outcome"] == "ok"
        assert report["attempt_log"][0]["http_status"] == 200


def test_circuit_open_provider_logs_skipped(client):
    set_faults(client, bitebox="error")
    for _ in range(3):
        stream(client)
    report = provider_events(stream(client))["bitebox"]
    assert report["status"] == "circuit_open"
    assert len(report["attempt_log"]) == 1
    attempt = report["attempt_log"][0]
    assert attempt["outcome"] == "skipped"
    assert attempt["duration_ms"] == 0.0
    assert attempt["http_status"] is None


def test_clarification_skips_providers(client):
    events = stream(client, "hello")
    assert [name for name, _ in events] == ["parsed", "done"]
    assert events[0][1]["clarification"] is not None
    assert events[1][1]["clarification"] == events[0][1]["clarification"]
    assert events[1][1]["providers"] == []


def test_engine_failure_emits_error_frame(client, monkeypatch: pytest.MonkeyPatch):
    async def broken(query, llm):
        raise RuntimeError("boom")

    monkeypatch.setattr("thali.pipeline.engine.parse_request", broken)
    response = client.post(STREAM, json={"query": MAIN_QUERY})
    events = parse_sse(response.text)
    name, payload = events[-1]
    assert name == "error"
    assert payload == {"error": "internal_error", "request_id": response.headers["x-request-id"]}
