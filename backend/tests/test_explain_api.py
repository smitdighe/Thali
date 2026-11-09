from conftest import MAIN_QUERY
from fastapi.testclient import TestClient

RECOMMEND = "/api/v1/recommend"


def ask(client: TestClient, query: str = MAIN_QUERY) -> dict:
    response = client.post(RECOMMEND, json={"query": query})
    assert response.status_code == 200
    return response.json()


def test_main_query_carries_why_not(client: TestClient) -> None:
    body = ask(client)
    assert body["schema_version"] == "1.1"
    assert body["ranked"][0]["why_not"] is None
    runner = body["ranked"][1]
    assert runner["restaurant"] == "Dum Pukht House"
    assert runner["why_not"] == (
        "Scores 0.5208 vs 0.5961: mainly rating (4.6 from 2,140 ratings vs 4.8 from 950)."
    )
    assert all(option["why_not"].startswith("Filtered out: ") for option in body["excluded"])


def test_main_query_carries_what_ifs(client: TestClient) -> None:
    body = ask(client)
    assert [item["statement"] for item in body["what_if"]] == [
        "The pick holds for any budget from ₹235 to ₹600. Under ₹235, it changes to "
        "Veg Dum Biryani at Dum Pukht House (Tiffinly, ₹229).",
        "The pick holds for any time limit from 22 to 60 minutes. Under 22 minutes, nothing fits.",
        "Without the “highly rated” preference, the pick stays the same.",
    ]
    assert body["trace"]["what_if_ms"] >= 0


def test_no_pick_has_no_what_ifs(client: TestClient) -> None:
    body = ask(client, "veg biryani under ₹100")
    assert body["recommendation"] is None
    assert body["what_if"] == []
    assert all(option["why_not"] for option in body["closest"])
