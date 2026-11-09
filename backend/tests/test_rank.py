import pytest
lazy from main_data import main_groups, main_parsed, make_group, make_listing

lazy from thali.models import (
    OptionGroup,
    OptionResult,
    ParsedRequest,
    RankOutcome,
    ScoredListing,
)
lazy from thali.pipeline.rank import rank, weights

TOLERANCE = 0.0005

MAIN_SCORES = {
    "bitebox:bb_105": (0.8619, 0.2167, 0.2667, 0.5961),
    "bitebox:bb_101": (0.7866, 0.1330, 0.2000, 0.5208),
    "tiffinly:T-88-4": (0.7842, 0.2367, 0.0000, 0.4988),
    "tiffinly:T-40-2": (0.5479, 0.3000, 0.1667, 0.4131),
    "bitebox:bb_106": (0.5000, 0.1333, 0.1667, 0.3500),
    "bitebox:bb_103": (0.2588, 0.4000, 0.0667, 0.2479),
}

MAIN_VIOLATIONS = {
    "tiffinly:T-12-1": ["25–35 min can exceed your 30-minute limit"],
    "bitebox:bb_107": ["delivery time not listed by Bitebox"],
    "bitebox:bb_108": ["31 min is over your 30-minute limit"],
    "bitebox:bb_109": ["price not listed by Bitebox"],
    "tiffinly:T-55-1": ["delivery time not listed by Tiffinly"],
    "khaana:A-1": ["delivery time not listed by Khaana Open Data"],
    "khaana:A-7": ["delivery time not listed by Khaana Open Data"],
    "khaana:A-5": [
        "price not listed by Khaana Open Data",
        "delivery time not listed by Khaana Open Data",
    ],
    "bitebox:bb_102": ["not vegetarian", "₹349 is over your ₹300 budget"],
    "tiffinly:T-88-7": ["not vegetarian", "₹339 is over your ₹300 budget"],
}


def all_scored(outcome: RankOutcome) -> dict[str, ScoredListing]:
    options = [*outcome.ranked, *outcome.excluded]
    return {scored.listing.listing_id: scored for option in options for scored in option.listings}


def restaurants(options: list[OptionResult]) -> list[str]:
    return [option.restaurant for option in options]


def factor_values(scored: ScoredListing) -> tuple[float, float, float, float]:
    values = {factor.factor: factor.value for factor in scored.factors}
    return (values["rating"], values["price"], values["eta"], scored.score)


def test_main_query_scores_match_worked_example() -> None:
    scored = all_scored(rank(main_groups(), main_parsed()))
    for listing_id, expected in MAIN_SCORES.items():
        actual = factor_values(scored[listing_id])
        assert actual == pytest.approx(expected, abs=TOLERANCE), listing_id


def test_main_query_order() -> None:
    outcome = rank(main_groups(), main_parsed())
    assert restaurants(outcome.ranked) == [
        "Lucknowi Degh",
        "Dum Pukht House",
        "Tandoor Tales",
        "Spice Route Kitchen",
        "Biryani Junction",
    ]
    assert [option.rank for option in outcome.ranked] == [1, 2, 3, 4, 5]
    assert outcome.ranked[1].best.listing.listing_id == "bitebox:bb_101"
    assert outcome.ranked[0].score == pytest.approx(0.5961, abs=TOLERANCE)
    assert len(outcome.excluded) == 11
    assert outcome.closest == []


def test_cheapest_feasible_option_comes_last() -> None:
    outcome = rank(main_groups(), main_parsed())
    prices = [option.best.listing.effective_price_paise or 0 for option in outcome.ranked]
    assert outcome.ranked[-1].best.listing.effective_price_paise == min(prices) == 18000


def test_main_query_violation_strings() -> None:
    scored = all_scored(rank(main_groups(), main_parsed()))
    for listing_id, expected in MAIN_VIOLATIONS.items():
        assert scored[listing_id].violations == expected, listing_id
        assert not scored[listing_id].feasible


def test_option_stays_feasible_through_another_provider() -> None:
    outcome = rank(main_groups(), main_parsed())
    lucknowi = outcome.ranked[0]
    assert [scored.listing.listing_id for scored in lucknowi.listings] == [
        "bitebox:bb_105",
        "tiffinly:T-12-1",
    ]
    assert lucknowi.best.listing.listing_id == "bitebox:bb_105"


def test_chain_branches_stay_separate_options() -> None:
    outcome = rank(main_groups(), main_parsed())
    branches = [
        option.area for option in outcome.excluded if option.restaurant == "Hyderabad House"
    ]
    assert sorted(branches) == ["Andheri West", "Dadar"]


def test_unknown_diet_is_excluded_for_veg_request() -> None:
    scored = all_scored(rank(main_groups(), main_parsed()))
    assert "vegetarian status not listed by Khaana Open Data" in scored["khaana:A-4"].violations


def test_weights_double_and_renormalize() -> None:
    plain = ParsedRequest(intent="discovery")
    assert weights(plain) == pytest.approx({"rating": 0.4, "price": 0.3, "eta": 0.3})
    rated = ParsedRequest(intent="discovery", rating_preference="high")
    assert weights(rated) == pytest.approx(
        {"rating": 0.5714, "price": 0.2143, "eta": 0.2143}, abs=TOLERANCE
    )
    cheap = ParsedRequest(intent="discovery", price_preference="low")
    assert weights(cheap) == pytest.approx(
        {"rating": 0.3077, "price": 0.4615, "eta": 0.2308}, abs=TOLERANCE
    )
    every = ParsedRequest(
        intent="discovery",
        rating_preference="high",
        price_preference="low",
        speed_preference="fast",
    )
    assert weights(every) == pytest.approx({"rating": 0.4, "price": 0.3, "eta": 0.3})


def test_hard_constraints_do_not_change_weights() -> None:
    constrained = ParsedRequest(
        intent="discovery", max_price_inr=300, max_eta_min=30, min_rating=4.0
    )
    assert weights(constrained) == pytest.approx({"rating": 0.4, "price": 0.3, "eta": 0.3})


def test_min_max_path_without_constraints() -> None:
    groups = [
        make_group(
            f"r{index}|powai|biryani",
            [
                make_listing(
                    f"bitebox:x{index}",
                    f"R{index}",
                    "Powai",
                    "Biryani",
                    "veg",
                    price,
                    4.0,
                    100,
                    eta,
                )
            ],
        )
        for index, (price, eta) in enumerate(
            [(10000, (10, 10)), (20000, (20, 20)), (30000, (30, 30)), (None, None)]
        )
    ]
    outcome = rank(groups, ParsedRequest(intent="discovery", dish="biryani"))
    values = {
        scored.listing.listing_id: factor_values(scored)
        for option in outcome.ranked
        for scored in option.listings
    }
    assert values["bitebox:x0"][1:3] == (1.0, 1.0)
    assert values["bitebox:x1"][1:3] == (0.5, 0.5)
    assert values["bitebox:x2"][1:3] == (0.0, 0.0)
    assert values["bitebox:x3"][1:3] == (0.5, 0.5)


def test_single_price_uses_neutral_value() -> None:
    group = make_group(
        "r|powai|biryani",
        [make_listing("bitebox:x", "R", "Powai", "Biryani", "veg", 10000, 4.0, 100, (20, 20))],
    )
    outcome = rank([group], ParsedRequest(intent="discovery"))
    assert factor_values(outcome.ranked[0].best)[1:3] == (0.5, 0.5)


def test_closest_when_nothing_fits() -> None:
    parsed = main_parsed().model_copy(update={"max_price_inr": 100})
    outcome = rank(main_groups(), parsed)
    assert outcome.ranked == []
    assert len(outcome.closest) == 3
    assert outcome.closest == outcome.excluded[:3]
    assert all(len(option.best.violations) >= 1 for option in outcome.closest)
    counts = [len(option.best.violations) for option in outcome.excluded]
    assert counts == sorted(counts)


def test_tie_break_is_deterministic() -> None:
    def twin(name: str) -> OptionGroup:
        return make_group(
            f"{name.lower()}|powai|biryani",
            [
                make_listing(
                    f"bitebox:{name}", name, "Powai", "Biryani", "veg", 20000, 4.2, 300, (25, 25)
                )
            ],
        )

    groups = [twin("Zeta"), twin("Alpha"), twin("Mid")]
    parsed = ParsedRequest(intent="discovery", dish="biryani")
    forward = restaurants(rank(groups, parsed).ranked)
    backward = restaurants(rank(list(reversed(groups)), parsed).ranked)
    assert forward == backward == ["Alpha", "Mid", "Zeta"]


def test_provider_name_breaks_an_exact_tie() -> None:
    first = make_listing("tiffinly:t", "Same", "Powai", "Biryani", "veg", 20000, 4.2, 300, (25, 25))
    second = make_listing("bitebox:b", "Same", "Powai", "Biryani", "veg", 20000, 4.2, 300, (25, 25))
    parsed = ParsedRequest(intent="discovery", max_price_inr=300, max_eta_min=30)
    outcome = rank([make_group("same|powai|biryani", [first, second])], parsed)
    scores = {scored.listing.listing_id: scored.score for scored in outcome.ranked[0].listings}
    assert scores["bitebox:b"] == scores["tiffinly:t"]
    assert outcome.ranked[0].best.listing.listing_id == "bitebox:b"


def test_preference_bonus_is_capped() -> None:
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
        tags=("veg", "jain", "healthy", "combo"),
    )
    parsed = ParsedRequest(
        intent="discovery", other_preferences=["jain", "healthy", "combo", "not spicy"]
    )
    outcome = rank([make_group("thali ghar|dadar|jain thali", [listing])], parsed)
    best = outcome.ranked[0].best
    assert best.bonus == pytest.approx(0.06)
    assert best.matched_preferences == ["jain", "healthy", "combo"]


def test_bitebox_partial_moves_pick_to_tiffinly() -> None:
    outcome = rank(main_groups(bitebox_partial=True), main_parsed())
    top = outcome.ranked[0]
    assert top.restaurant == "Dum Pukht House"
    assert top.best.listing.listing_id == "tiffinly:T-88-4"
    assert top.score == pytest.approx(0.4988, abs=TOLERANCE)
    assert outcome.ranked[1].restaurant == "Tandoor Tales"
    assert outcome.ranked[1].score == pytest.approx(0.4131, abs=TOLERANCE)
    scored = all_scored(outcome)
    assert scored["bitebox:bb_105"].violations == ["delivery time not listed by Bitebox"]
