lazy import csv
lazy import io
lazy import json
lazy import time
lazy from collections.abc import Iterator
lazy from pathlib import Path

import pytest
lazy from fastapi.testclient import TestClient

lazy from thali.config import Settings
lazy from thali.mock.app import create_mock_app

BITEBOX = "/bitebox/v2/search"
TIFFINLY = "/tiffinly/api/v3/outlets/search"
KHAANA = "/khaana/v1/listings.csv"
ALL_OK = {"bitebox": "ok", "tiffinly": "ok", "khaana": "ok"}
MODES = ["ok", "slow", "timeout", "error", "malformed", "partial"]


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "providers_in_process": True,
        "mock_slow_ms": 50,
        "mock_timeout_sleep_ms": 200,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_mock_app(make_settings())) as c:
        yield c


def data_path(name: str) -> Path:
    return Path(__file__).resolve().parents[1] / "src" / "thali" / "mock" / "data" / name


def call(client: TestClient, provider: str):
    if provider == "bitebox":
        return client.get(BITEBOX)
    if provider == "tiffinly":
        return client.post(TIFFINLY, json={"query": ""})
    return client.get(KHAANA)


def set_mode(client: TestClient, provider: str, mode: str) -> None:
    assert client.put("/_faults", json={provider: mode}).status_code == 200


def test_bitebox_shape(client: TestClient) -> None:
    body = client.get(BITEBOX).json()
    assert body["api_version"] == "2.1"
    assert len(body["results"]) == 46
    first = body["results"][0]
    assert first["id"] == "bb_101"
    assert first["restaurant"] == {"id": "rb_1", "name": "Dum Pukht House", "area": "Andheri West"}
    assert first["offer"] == "10% OFF up to ₹40"


def test_bitebox_q_matches_dish_case_insensitively(client: TestClient) -> None:
    ids = [r["id"] for r in client.get(BITEBOX, params={"q": "DUM BIRYANI"}).json()["results"]]
    assert ids == ["bb_101", "bb_102", "bb_105"]


def test_bitebox_q_matches_cuisine(client: TestClient) -> None:
    ids = [r["id"] for r in client.get(BITEBOX, params={"q": "tibetan"}).json()["results"]]
    assert ids == ["bb_201"]


def test_bitebox_q_biryani_returns_all_biryani_rows(client: TestClient) -> None:
    results = client.get(BITEBOX, params={"q": "biryani"}).json()["results"]
    assert [r["id"] for r in results] == [f"bb_10{n}" for n in range(1, 10)]


def test_bitebox_area_is_exact(client: TestClient) -> None:
    ids = [r["id"] for r in client.get(BITEBOX, params={"area": "Powai"}).json()["results"]]
    assert ids == ["bb_103", "bb_104", "bb_201", "bb_202"]
    assert client.get(BITEBOX, params={"area": "powai"}).json()["results"] == []
    assert client.get(BITEBOX, params={"area": "Andheri"}).json()["results"] == []


def test_bitebox_q_and_area_combine(client: TestClient) -> None:
    params = {"q": "biryani", "area": "Andheri West"}
    ids = [r["id"] for r in client.get(BITEBOX, params=params).json()["results"]]
    assert ids == ["bb_101", "bb_102", "bb_106", "bb_107"]


def test_bitebox_no_match_is_empty(client: TestClient) -> None:
    body = client.get(BITEBOX, params={"q": "sushi"}).json()
    assert body == {"api_version": "2.1", "results": []}


def test_tiffinly_empty_query_returns_everything(client: TestClient) -> None:
    body = client.post(TIFFINLY, json={"query": ""}).json()
    assert body["meta"]["schema"] == "tiffinly.v3"
    outlets = body["data"]["outlets"]
    assert [o["outletId"] for o in outlets] == [
        "T-88",
        "T-12",
        "T-40",
        "T-55",
        "T-70",
        "T-31",
        "T-64",
        "T-19",
    ]
    assert len(outlets[3]["menu"]) == 3


def test_tiffinly_filters_items_and_drops_empty_outlets(client: TestClient) -> None:
    outlets = client.post(TIFFINLY, json={"query": "BIRYANI"}).json()["data"]["outlets"]
    assert [o["outletId"] for o in outlets] == ["T-88", "T-12", "T-40", "T-55"]
    assert [len(o["menu"]) for o in outlets] == [2, 1, 1, 1]
    assert outlets[2]["menu"][0]["title"] == "Veg Biryani Bowl"


def test_tiffinly_no_match_has_no_outlets(client: TestClient) -> None:
    body = client.post(TIFFINLY, json={"query": "sushi"}).json()
    assert body["data"]["outlets"] == []


def test_khaana_serves_whole_csv(client: TestClient) -> None:
    response = client.get(KHAANA)
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    expected = data_path("khaana.csv").read_bytes().decode("utf-8")
    assert response.content.decode("utf-8") == expected
    assert len(response.text.splitlines()) == 9


def test_khaana_ignores_query_params(client: TestClient) -> None:
    assert client.get(KHAANA, params={"q": "zzz"}).text == client.get(KHAANA).text


def test_data_files_use_lf_line_endings() -> None:
    for name in ("khaana.csv", "bitebox.json", "tiffinly.json"):
        assert b"\r" not in data_path(name).read_bytes()


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly", "khaana"])
def test_mode_header_defaults_to_ok(client: TestClient, provider: str) -> None:
    assert call(client, provider).headers["x-mock-mode"] == "ok"


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly", "khaana"])
@pytest.mark.parametrize("mode", MODES)
def test_mode_header_reflects_fault(client: TestClient, provider: str, mode: str) -> None:
    set_mode(client, provider, mode)
    assert call(client, provider).headers["x-mock-mode"] == mode


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly", "khaana"])
def test_error_mode_returns_503(client: TestClient, provider: str) -> None:
    set_mode(client, provider, "error")
    response = call(client, provider)
    assert response.status_code == 503
    assert response.json() == {"error": "upstream unavailable"}


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly"])
def test_malformed_json_is_truncated_and_unparseable(client: TestClient, provider: str) -> None:
    normal = call(client, provider).text
    set_mode(client, provider, "malformed")
    response = call(client, provider)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert len(response.text) == 120
    assert normal.startswith(response.text)
    with pytest.raises(json.JSONDecodeError):
        json.loads(response.text)


def test_malformed_khaana_is_html(client: TestClient) -> None:
    set_mode(client, "khaana", "malformed")
    response = client.get(KHAANA)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text == "<html><body>Service temporarily unavailable</body></html>"


def test_partial_bitebox_strips_fields(client: TestClient) -> None:
    set_mode(client, "bitebox", "partial")
    results = client.get(BITEBOX).json()["results"]
    assert len(results) == 46
    for result in results:
        assert not {"rating", "ratings_count", "eta_minutes"} & result.keys()
        assert "price" in result
        assert "dish" in result


def test_partial_tiffinly_strips_fields(client: TestClient) -> None:
    set_mode(client, "tiffinly", "partial")
    outlets = client.post(TIFFINLY, json={"query": ""}).json()["data"]["outlets"]
    assert len(outlets) == 8
    for outlet in outlets:
        assert not {"score", "votes", "deliveryTime"} & outlet.keys()
        assert "outletName" in outlet
        assert outlet["menu"]


def test_partial_khaana_blanks_rating_columns(client: TestClient) -> None:
    set_mode(client, "khaana", "partial")
    text = client.get(KHAANA).text
    rows = list(csv.DictReader(io.StringIO(text), restkey="extra"))
    assert len(rows) == 8
    for row in rows:
        assert row["avg_rating"] == ""
        assert row["num_ratings"] == ""
    assert rows[0]["price"] == "₹ 175"
    assert rows[4]["item"] == "Veg Biryani, Large"
    assert rows[5]["extra"] == ["extra", "column"]
    assert text.endswith("\n")
    assert "\r" not in text


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly", "khaana"])
def test_slow_mode_sleeps_then_serves_normal_body(client: TestClient, provider: str) -> None:
    normal = call(client, provider).text
    set_mode(client, provider, "slow")
    started = time.perf_counter()
    response = call(client, provider)
    elapsed = time.perf_counter() - started
    assert 0.045 <= elapsed < 0.19
    assert response.status_code == 200
    assert response.text == normal


@pytest.mark.parametrize("provider", ["bitebox", "tiffinly", "khaana"])
def test_timeout_mode_sleeps_longer_then_serves_normal_body(
    client: TestClient, provider: str
) -> None:
    normal = call(client, provider).text
    set_mode(client, provider, "timeout")
    started = time.perf_counter()
    response = call(client, provider)
    assert time.perf_counter() - started >= 0.195
    assert response.status_code == 200
    assert response.text == normal


def test_fault_sleep_follows_settings() -> None:
    settings = make_settings(mock_slow_ms=120)
    with TestClient(create_mock_app(settings)) as c:
        set_mode(c, "bitebox", "slow")
        started = time.perf_counter()
        c.get(BITEBOX)
        assert time.perf_counter() - started >= 0.115


def test_faults_start_all_ok(client: TestClient) -> None:
    assert client.get("/_faults").json() == ALL_OK


def test_put_faults_merges(client: TestClient) -> None:
    assert client.put("/_faults", json={"bitebox": "error"}).json() == {
        **ALL_OK,
        "bitebox": "error",
    }
    response = client.put("/_faults", json={"tiffinly": "slow"})
    assert response.json() == {"bitebox": "error", "tiffinly": "slow", "khaana": "ok"}
    assert client.get("/_faults").json() == response.json()


@pytest.mark.parametrize(
    "body",
    [
        {"zomato": "error"},
        {"bitebox": "exploded"},
        {"bitebox": "error", "zomato": "ok"},
        {"bitebox": None},
        {"bitebox": 1},
        ["bitebox"],
        "bitebox",
    ],
)
def test_put_faults_rejects_invalid_body(client: TestClient, body: object) -> None:
    assert client.put("/_faults", json=body).status_code == 422
    assert client.get("/_faults").json() == ALL_OK


def test_put_faults_with_empty_object_changes_nothing(client: TestClient) -> None:
    set_mode(client, "khaana", "error")
    assert client.put("/_faults", json={}).json() == {**ALL_OK, "khaana": "error"}


def test_reset_restores_all_ok(client: TestClient) -> None:
    client.put("/_faults", json={"bitebox": "error", "tiffinly": "malformed", "khaana": "partial"})
    response = client.post("/_faults/reset")
    assert response.status_code == 200
    assert response.json() == ALL_OK
    assert client.get("/_faults").json() == ALL_OK
    assert client.get(BITEBOX).status_code == 200


def test_each_app_has_its_own_fault_table() -> None:
    first = create_mock_app(make_settings())
    second = create_mock_app(make_settings())
    with TestClient(first) as a, TestClient(second) as b:
        set_mode(a, "bitebox", "error")
        assert b.get("/_faults").json() == ALL_OK
        assert first.state.faults["bitebox"] == "error"
        assert second.state.faults == ALL_OK


def test_fault_api_disabled_returns_404() -> None:
    app = create_mock_app(make_settings(enable_fault_api=False))
    with TestClient(app) as c:
        assert c.get("/_faults").status_code == 404
        assert c.put("/_faults", json={"bitebox": "error"}).status_code == 404
        assert c.post("/_faults/reset").status_code == 404
        assert app.state.faults == ALL_OK
        assert c.get(BITEBOX).status_code == 200
