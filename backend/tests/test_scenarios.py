from conftest import MAIN_QUERY, set_faults
from fastapi.testclient import TestClient

from thali.models import DataQuality, OptionResult

RECOMMEND = "/api/v1/recommend"
MAIN_SUMMARY = (
    "Recommended because it matches your vegetarian requirement, stays within your ₹300 budget "
    "at ₹235 after the offer, has a 4.8 rating from 950 ratings, and has an estimated delivery "
    "time of 22 minutes."
)


def ask(client: TestClient, query: str = MAIN_QUERY) -> dict:
    response = client.post(RECOMMEND, json={"query": query})
    assert response.status_code == 200
    return response.json()


def provider(body: dict, name: str) -> dict:
    return next(report for report in body["providers"] if report["name"] == name)


def option_named(options: list[dict], restaurant: str, item: str | None = None) -> dict:
    return next(
        option
        for option in options
        if option["restaurant"] == restaurant and (item is None or option["item"] == item)
    )


def providers_of(option: dict) -> set[str]:
    return {scored["listing"]["provider"] for scored in option["listings"]}


def all_options(body: dict) -> list[dict]:
    return body["ranked"] + body["excluded"] + body["closest"]


def effective_price_of(option: OptionResult) -> int:
    price = option.best.listing.effective_price_paise
    assert price is not None
    return price


def test_normal_request_recommends_best_fit(client: TestClient) -> None:
    body = ask(client)
    parsed = body["parsed"]
    assert parsed["intent"] == "discovery"
    assert parsed["dish"] == "biryani"
    assert parsed["diet"] == "veg"
    assert parsed["max_price_inr"] == 300
    assert parsed["max_eta_min"] == 30
    assert parsed["rating_preference"] == "high"
    assert parsed["missing"] == ["location"]
    recommendation = body["recommendation"]
    assert recommendation["option"]["restaurant"] == "Lucknowi Degh"
    assert recommendation["option"]["item"] == "Subz Dum Biryani"
    assert recommendation["option"]["best"]["listing"]["provider"] == "bitebox"
    assert recommendation["summary"] == MAIN_SUMMARY
    assert body["degraded"] is False
    assert body["warnings"] == []
    assert [report["status"] for report in body["providers"]] == ["ok", "ok", "ok"]


def test_missing_information_stays_null(client: TestClient) -> None:
    body = ask(client, "suggest a biryani")
    parsed = body["parsed"]
    assert parsed["dish"] == "biryani"
    for field in ("diet", "max_price_inr", "max_eta_min", "min_rating", "location"):
        assert parsed[field] is None
    assert parsed["missing"] == ["diet", "budget", "delivery_time", "rating", "location"]
    assert body["recommendation"] is not None
    for option in all_options(body):
        for scored in option["listings"]:
            for violation in scored["violations"]:
                assert "budget" not in violation
                assert "minute limit" not in violation


def test_provider_timeout_degrades_gracefully(client: TestClient) -> None:
    set_faults(client, tiffinly="timeout")
    body = ask(client)
    assert provider(body, "tiffinly")["status"] == "timeout"
    assert body["degraded"] is True
    assert any("Tiffinly" in warning for warning in body["warnings"])
    option = body["recommendation"]["option"]
    assert option["restaurant"] == "Lucknowi Degh"
    assert option["best"]["listing"]["provider"] == "bitebox"
    assert body["trace"]["total_ms"] < 1500


def test_provider_error_is_retried_then_reported(client: TestClient) -> None:
    set_faults(client, bitebox="error")
    body = ask(client)
    report = provider(body, "bitebox")
    assert report["status"] == "error"
    assert report["attempts"] == 2
    assert report["http_status"] == 503
    assert body["degraded"] is True
    assert any("Bitebox returned an error (503) after 2 attempts" in w for w in body["warnings"])
    recommendation = body["recommendation"]
    assert recommendation is not None
    assert recommendation["option"]["best"]["listing"]["provider"] != "bitebox"


def test_incomplete_provider_data(client: TestClient) -> None:
    set_faults(client, bitebox="partial")
    body = ask(client)
    bitebox_listings = [
        scored["listing"]
        for option in all_options(body)
        for scored in option["listings"]
        if scored["listing"]["provider"] == "bitebox"
    ]
    assert bitebox_listings
    for listing in bitebox_listings:
        assert "rating" in listing["missing_fields"]
        assert "eta" in listing["missing_fields"]
    violations = [
        violation
        for option in all_options(body)
        for scored in option["listings"]
        for violation in scored["violations"]
    ]
    assert "delivery time not listed by Bitebox" in violations
    option = body["recommendation"]["option"]
    assert option["restaurant"] == "Dum Pukht House"
    assert option["best"]["listing"]["provider"] == "tiffinly"


def test_duplicates_are_merged(client: TestClient) -> None:
    body = ask(client)
    dum_pukht = option_named(body["ranked"], "Dum Pukht House", "Veg Dum Biryani")
    assert {"bitebox", "tiffinly"} <= providers_of(dum_pukht)
    junction = option_named(all_options(body), "Biryani Junction")
    assert {"bitebox", "khaana"} <= providers_of(junction)
    assert len(junction["listings"]) == 2
    assert DataQuality(**body["data_quality"]) == DataQuality(
        records_received=22,
        records_dropped=1,
        duplicates_removed=1,
        merged_options=4,
        listings_with_missing_fields=11,
    )
    assert len(body["ranked"]) == 5
    assert len(body["excluded"]) == 11
    hyderabad = [o for o in all_options(body) if o["restaurant"] == "Hyderabad House"]
    assert len(hyderabad) == 2
    assert {o["area"] for o in hyderabad} == {"Andheri West", "Dadar"}
    assert len({o["option_id"] for o in hyderabad}) == 2


def test_cheapest_is_not_automatically_best(client: TestClient) -> None:
    body = ask(client)
    ranked = [OptionResult(**option) for option in body["ranked"]]
    cheapest = min(ranked, key=effective_price_of)
    assert cheapest.restaurant == "Biryani Junction"
    assert effective_price_of(cheapest) == 18000
    assert ranked[0].restaurant != "Biryani Junction"
    alternative = body["recommendation"]["cheaper_alternative"]
    assert "Biryani Junction" in alternative
    assert "₹55" in alternative


def test_malformed_provider_response(client: TestClient) -> None:
    baseline = ask(client)
    set_faults(client, tiffinly="malformed")
    body = ask(client)
    assert provider(body, "tiffinly")["status"] == "malformed"
    assert body["degraded"] is True
    assert any("Tiffinly sent a response that couldn't be read" in w for w in body["warnings"])
    assert body["recommendation"]["summary"] == baseline["recommendation"]["summary"]
    assert (
        body["recommendation"]["option"]["option_id"]
        == baseline["recommendation"]["option"]["option_id"]
    )


def test_circuit_opens_after_repeated_failures(client: TestClient) -> None:
    set_faults(client, tiffinly="error")
    for _ in range(3):
        assert provider(ask(client), "tiffinly")["status"] == "error"
    body = ask(client)
    report = provider(body, "tiffinly")
    assert report["status"] == "circuit_open"
    assert report["attempts"] == 0
    assert any("Tiffinly is paused after repeated failures" in w for w in body["warnings"])
    assert body["recommendation"] is not None


def test_clarification_skips_providers(client: TestClient) -> None:
    body = ask(client, "hi")
    assert body["clarification"] is not None
    assert body["clarification"].endswith("“veg biryani under ₹300 in 30 minutes”.")
    assert body["providers"] == []
    assert body["recommendation"] is None
    assert body["ranked"] == []
