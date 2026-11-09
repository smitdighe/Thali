import json

from conftest import MAIN_QUERY
from fastapi.testclient import TestClient

from thali.models import ParsedRequest
from thali.sessions import SessionStore

RECOMMEND = "/api/v1/recommend"
STREAM = "/api/v1/recommend/stream"
REFINE = "/api/v1/refine"
NO_PICK_QUERY = "veg biryani under ₹100"


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def first_response(client: TestClient, query: str = MAIN_QUERY) -> dict:
    response = client.post(RECOMMEND, json={"query": query})
    assert response.status_code == 200
    return response.json()


def refine(client: TestClient, request_id: str, **change: str) -> dict:
    response = client.post(REFINE, json={"request_id": request_id, **change})
    assert response.status_code == 200
    return response.json()


def test_cheaper_tightens_budget_and_changes_pick(client: TestClient) -> None:
    original = first_response(client)
    body = refine(client, original["request_id"], action="cheaper")
    parsed = body["parsed"]
    assert parsed["max_price_inr"] == 234
    assert parsed["price_preference"] == "low"
    assert parsed["rating_preference"] == "high"
    assert "budget" in parsed["adjusted"]
    assert "price_preference" in parsed["adjusted"]
    assert parsed["refined_from"] == original["request_id"]
    assert body["query"] == "Cheaper"
    option = body["recommendation"]["option"]
    assert option["item"] == "Veg Dum Biryani"
    assert option["restaurant"] == "Dum Pukht House"
    assert option["best"]["listing"]["provider"] == "tiffinly"
    assert option["best"]["listing"]["effective_price_paise"] == 22900
    assert option["best"]["score"] == 0.3766


def test_faster_tightens_delivery(client: TestClient) -> None:
    original = first_response(client)
    body = refine(client, original["request_id"], action="faster")
    assert body["parsed"]["max_eta_min"] == 21
    assert body["parsed"]["speed_preference"] == "fast"
    assert body["recommendation"] is None
    assert body["closest"]


def test_better_rated_raises_rating_floor(client: TestClient) -> None:
    original = first_response(client)
    body = refine(client, original["request_id"], action="better_rated")
    assert body["parsed"]["min_rating"] == 4.9
    assert body["parsed"]["rating_preference"] == "high"


def test_drop_clears_field(client: TestClient) -> None:
    original = first_response(client)
    body = refine(client, original["request_id"], drop="budget")
    parsed = body["parsed"]
    assert parsed["max_price_inr"] is None
    assert "budget" in parsed["adjusted"]
    for name in ("dish", "diet", "delivery_time"):
        assert name in parsed["carried_over"]
    assert body["query"] == "Remove budget"


def test_drop_unknown_field_is_rejected(client: TestClient) -> None:
    original = first_response(client)
    response = client.post(REFINE, json={"request_id": original["request_id"], "drop": "nonsense"})
    assert response.status_code == 422
    assert response.json() == {"error": "unknown_field"}


def test_text_followup_overrides_only_what_it_sets(client: TestClient) -> None:
    original = first_response(client)
    text = "make it vegan"
    body = refine(client, original["request_id"], text=text)
    parsed = body["parsed"]
    assert parsed["diet"] == "vegan"
    assert parsed["dish"] == "biryani"
    assert parsed["max_price_inr"] == 300
    assert parsed["max_eta_min"] == 30
    assert parsed["adjusted"] == ["diet"]
    assert body["query"] == text
    assert parsed["spans"]
    for span in parsed["spans"]:
        assert span["text"] == text[span["start"] : span["end"]]


def test_text_without_change_asks_for_clarification(client: TestClient) -> None:
    original = first_response(client)
    body = refine(client, original["request_id"], text="hmm ok")
    assert body["clarification"] == "I couldn't find a change in “hmm ok”."
    assert body["recommendation"] is None
    assert body["providers"] == []
    assert body["parsed"]["refined_from"] == original["request_id"]
    assert body["parsed"]["max_price_inr"] == 300
    again = refine(client, body["request_id"], action="cheaper")
    assert again["parsed"]["max_price_inr"] == 234


def test_refinements_chain(client: TestClient) -> None:
    original = first_response(client)
    refined = refine(client, original["request_id"], action="cheaper")
    chained = refine(client, refined["request_id"], text="make it vegan")
    assert chained["parsed"]["refined_from"] == refined["request_id"]
    assert chained["parsed"]["max_price_inr"] == 234
    assert chained["parsed"]["diet"] == "vegan"


def test_unknown_request_is_404(client: TestClient) -> None:
    response = client.post(REFINE, json={"request_id": "missing", "action": "cheaper"})
    assert response.status_code == 404
    assert response.json() == {"error": "unknown_or_expired_request"}


def test_expired_request_is_404(client: TestClient) -> None:
    clock = FakeClock()
    client.app.state.deps.sessions = SessionStore(clock=clock)
    original = first_response(client)
    clock.now += 901
    response = client.post(REFINE, json={"request_id": original["request_id"], "action": "cheaper"})
    assert response.status_code == 404
    assert response.json() == {"error": "unknown_or_expired_request"}


def test_entry_within_ttl_survives(client: TestClient) -> None:
    clock = FakeClock()
    client.app.state.deps.sessions = SessionStore(clock=clock)
    original = first_response(client)
    clock.now += 899
    refine(client, original["request_id"], action="cheaper")


def test_store_evicts_least_recently_used() -> None:
    store = SessionStore(max_entries=2)
    parsed = ParsedRequest(intent="discovery", dish="biryani")
    store.put("a", parsed, None)
    store.put("b", parsed, None)
    assert store.get("a") is not None
    store.put("c", parsed, None)
    assert store.get("b") is None
    assert store.get("a") is not None
    assert store.get("c") is not None


def test_action_without_pick_is_409(client: TestClient) -> None:
    original = first_response(client, NO_PICK_QUERY)
    assert original["recommendation"] is None
    response = client.post(REFINE, json={"request_id": original["request_id"], "action": "cheaper"})
    assert response.status_code == 409
    assert response.json() == {"error": "no_pick_to_refine"}
    refine(client, original["request_id"], drop="budget")


def test_body_needs_exactly_one_change(client: TestClient) -> None:
    original = first_response(client)
    request_id = original["request_id"]
    assert client.post(REFINE, json={"request_id": request_id}).status_code == 422
    both = {"request_id": request_id, "action": "cheaper", "drop": "budget"}
    assert client.post(REFINE, json=both).status_code == 422


def test_streamed_results_can_be_refined(client: TestClient) -> None:
    response = client.post(STREAM, json={"query": MAIN_QUERY})
    done = [block for block in response.text.split("\n\n") if block.startswith("event: done")]
    payload = json.loads(done[0].split("data: ", 1)[1])
    body = refine(client, payload["request_id"], action="cheaper")
    assert body["parsed"]["refined_from"] == payload["request_id"]
