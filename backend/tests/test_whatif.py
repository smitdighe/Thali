lazy from main_data import main_groups, main_parsed

lazy from thali.models import ParsedRequest
lazy from thali.pipeline.rank import (
    budget_violations,
    delivery_violations,
    rank,
    rating_violations,
)
lazy from thali.pipeline.whatif import candidates, fast_top, what_ifs


def statements(parsed: ParsedRequest) -> list[str]:
    groups = main_groups()
    ranked = rank(groups, parsed).ranked
    pick = ranked[0].best.listing if ranked else None
    return [item.statement for item in what_ifs(groups, parsed, pick)]


def test_main_query_what_ifs() -> None:
    assert statements(main_parsed()) == [
        "The pick holds for any budget from ₹235 to ₹600. Under ₹235, it changes to "
        "Veg Dum Biryani at Dum Pukht House (Tiffinly, ₹229).",
        "The pick holds for any time limit from 22 to 60 minutes. Under 22 minutes, nothing fits.",
        "Without the “highly rated” preference, the pick stays the same.",
    ]


def test_main_query_what_if_fields() -> None:
    groups, parsed = main_groups(), main_parsed()
    pick = rank(groups, parsed).ranked[0].best.listing
    budget, delivery, preference = what_ifs(groups, parsed, pick)
    assert (budget.kind, budget.threshold) == ("budget", 235)
    assert budget.new_pick == "Veg Dum Biryani at Dum Pukht House (Tiffinly, ₹229)"
    assert (delivery.kind, delivery.threshold, delivery.new_pick) == ("delivery", 22, None)
    assert (preference.kind, preference.threshold, preference.new_pick) == (
        "preference",
        None,
        None,
    )


def test_min_rating_sweeps_upward_only() -> None:
    parsed = main_parsed().model_copy(update={"min_rating": 4.0})
    assert "The pick holds for any minimum rating up to 4.8. Above 4.8, nothing fits." in (
        statements(parsed)
    )


def test_removed_preference_can_change_the_pick() -> None:
    parsed = main_parsed().model_copy(
        update={"rating_preference": None, "price_preference": "low", "max_price_inr": None}
    )
    groups = main_groups()
    pick = rank(groups, parsed).ranked[0]
    without = rank(groups, parsed.model_copy(update={"price_preference": None})).ranked[0]
    text = statements(parsed)[-1]
    if without.best.listing.listing_id == pick.best.listing.listing_id:
        assert text == "Without the “cheaper” preference, the pick stays the same."
    else:
        assert text.startswith(
            f"Without the “cheaper” preference, the pick would be {without.item} at "
            f"{without.restaurant} ({without.best.listing.provider_label}, "
        )


def test_no_pick_gives_no_what_ifs() -> None:
    assert what_ifs(main_groups(), main_parsed(), None) == []


def test_nothing_stated_gives_no_what_ifs() -> None:
    assert statements(ParsedRequest(intent="discovery", dish="biryani")) == []


def test_fast_path_matches_full_ranking() -> None:
    groups = main_groups()
    sweeps = [
        ("max_price_inr", budget_violations, list(range(1, 700, 3))),
        ("max_eta_min", delivery_violations, list(range(1, 70))),
        ("min_rating", rating_violations, [step / 10 for step in range(51)]),
    ]
    bases = [
        main_parsed(),
        main_parsed().model_copy(update={"rating_preference": None, "price_preference": "low"}),
        main_parsed().model_copy(update={"speed_preference": "fast", "diet": None}),
    ]
    for field, check, values in sweeps:
        for base in bases:
            pool = candidates(groups, base, field)
            for value in values:
                parsed = base.model_copy(update={field: value})
                ranked = rank(groups, parsed).ranked
                expected = ranked[0].best.listing.listing_id if ranked else None
                fast = fast_top(pool, parsed, check)
                assert (fast.listing.listing_id if fast else None) == expected, (field, value)
