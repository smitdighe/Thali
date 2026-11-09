lazy from main_data import (
    main_groups,
    main_parsed,
    make_group,
    make_listing,
    offer_percent,
)

lazy from thali.models import ParsedRequest, ProviderReport, Recommendation
lazy from thali.pipeline.explain import explain
lazy from thali.pipeline.rank import rank

MAIN_SUMMARY = (
    "Recommended because it matches your vegetarian requirement, stays within your ₹300 budget "
    "at ₹235 after the offer, has a 4.8 rating from 950 ratings, and has an estimated delivery "
    "time of 22 minutes."
)
MAIN_REASONS = [
    "Vegetarian (marked veg by Bitebox)",
    "Subz Dum Biryani matches “biryani”",
    "₹285, ₹235 after 20% off (max ₹50) — within your ₹300 budget",
    "22 min delivery — inside your 30-minute limit",
    "Rated 4.8 from 950 ratings — the highest rating among options that fit",
]


def ok_reports() -> list[ProviderReport]:
    return [
        ProviderReport(name="bitebox", label="Bitebox", status="ok"),
        ProviderReport(name="tiffinly", label="Tiffinly", status="ok"),
        ProviderReport(name="khaana", label="Khaana Open Data", status="ok"),
    ]


def main_recommendation(reports: list[ProviderReport] | None = None) -> Recommendation:
    parsed = main_parsed()
    result = explain(rank(main_groups(), parsed), parsed, reports or ok_reports())
    assert result is not None
    return result


def test_main_query_summary() -> None:
    assert main_recommendation().summary == MAIN_SUMMARY


def test_main_query_reasons() -> None:
    assert main_recommendation().reasons == MAIN_REASONS


def test_main_query_comparison() -> None:
    assert main_recommendation().comparison == (
        "Ranked above Veg Dum Biryani at Dum Pukht House (Bitebox) mainly on rating: 4.8 vs 4.6."
    )


def test_main_query_cheaper_alternative() -> None:
    assert main_recommendation().cheaper_alternative == (
        "Veg Biryani at Biryani Junction is ₹55 cheaper (₹180) but is rated 3.4 from 410 ratings."
    )


def test_main_query_also_on_and_caveats() -> None:
    result = main_recommendation()
    assert result.also_on == ["Also on Tiffinly, but 25–35 min can exceed your 30-minute limit."]
    assert result.caveats == []
    assert result.option.restaurant == "Lucknowi Degh"


def test_nothing_ranked_gives_no_recommendation() -> None:
    parsed = main_parsed().model_copy(update={"max_price_inr": 100})
    assert explain(rank(main_groups(), parsed), parsed, ok_reports()) is None


def test_unknown_rating_caveat() -> None:
    listing = make_listing(
        "bitebox:bb_106",
        "Spice Route Kitchen",
        "Andheri West",
        "Paneer Biryani",
        "veg",
        26000,
        None,
        None,
        (25, 25),
    )
    parsed = ParsedRequest(intent="discovery", dish="biryani")
    outcome = rank([make_group("spice|andheri west|biryani paneer", [listing])], parsed)
    result = explain(outcome, parsed, ok_reports())
    assert result is not None
    assert result.caveats == ["No rating is listed for this item, so it was scored as average."]
    assert result.summary == (
        "Recommended because it costs ₹260 and has an estimated delivery time of 25 minutes."
    )
    assert result.comparison is None
    assert result.cheaper_alternative is None


def test_provider_caveat() -> None:
    reports = ok_reports()
    reports[1] = ProviderReport(name="tiffinly", label="Tiffinly", status="timeout")
    reports[2] = ProviderReport(name="khaana", label="Khaana Open Data", status="circuit_open")
    assert main_recommendation(reports).caveats == [
        "Tiffinly wasn't compared (timed out).",
        "Khaana Open Data wasn't compared (was skipped after repeated failures).",
    ]


def test_unmatched_preference_caveat() -> None:
    parsed = main_parsed().model_copy(update={"other_preferences": ["not spicy"]})
    result = explain(rank(main_groups(), parsed), parsed, ok_reports())
    assert result is not None
    assert result.caveats == ["Couldn't check “not spicy”: none of the sources describe it."]


def test_matched_preference_reason() -> None:
    listing = make_listing(
        "tiffinly:T-70-1",
        "Thali Ghar",
        "Dadar",
        "Jain Thali",
        "veg",
        26000,
        4.4,
        980,
        (30, 40),
        tags=("veg", "jain"),
    )
    parsed = ParsedRequest(
        intent="discovery",
        dish="thali",
        diet="veg",
        location="Dadar",
        max_price_inr=300,
        other_preferences=["jain"],
    )
    result = explain(
        rank([make_group("thali ghar|dadar|jain thali", [listing])], parsed), parsed, []
    )
    assert result is not None
    assert result.reasons[-2:] == ["In Dadar, as requested", "Matches “jain”"]
    assert result.summary.startswith(
        "Recommended because it matches your vegetarian requirement, is in Dadar, stays within"
    )
    assert result.caveats == []


def test_range_eta_caveat() -> None:
    listing = make_listing(
        "tiffinly:T-40-2",
        "Tandoor Tales",
        "Powai",
        "Veg Biryani Bowl",
        "veg",
        21000,
        4.1,
        2300,
        (15, 25),
    )
    parsed = ParsedRequest(intent="discovery", max_eta_min=30)
    result = explain(rank([make_group("tandoor|powai|bowl", [listing])], parsed), parsed, [])
    assert result is not None
    assert result.reasons == [
        "15–25 min delivery — inside your 30-minute limit",
        "Rated 4.1 from 2,300 ratings — the highest rating among options that fit",
    ]
    assert result.caveats == [
        "Delivery is quoted as 15–25 min; the upper end was checked against your limit."
    ]


def test_offer_dependent_budget_text() -> None:
    listing = make_listing(
        "tiffinly:T-12-1",
        "Lucknowi Degh",
        "Bandra West",
        "Subz Dum Biryani",
        "veg",
        32000,
        4.7,
        620,
        (25, 25),
        offer_percent("15% off up to ₹60", 15.0, 6000),
        27200,
    )
    parsed = ParsedRequest(intent="discovery", max_price_inr=300)
    result = explain(rank([make_group("lucknowi|bandra west|subz", [listing])], parsed), parsed, [])
    assert result is not None
    assert "₹320, ₹272 after 15% off (max ₹60) — within your ₹300 budget" in result.reasons
