lazy from main_data import main_groups, main_parsed, make_group, make_listing

lazy from thali.models import OptionResult, ParsedRequest, RankOutcome
lazy from thali.pipeline.explain import with_why_not
lazy from thali.pipeline.rank import rank


def main_outcome() -> RankOutcome:
    return with_why_not(rank(main_groups(), main_parsed()))


def by_restaurant(options: list[OptionResult], restaurant: str) -> OptionResult:
    return next(option for option in options if option.restaurant == restaurant)


def test_top_pick_has_no_why_not() -> None:
    assert main_outcome().ranked[0].why_not is None


def test_every_other_option_has_why_not() -> None:
    outcome = main_outcome()
    assert all(option.why_not for option in outcome.ranked[1:])
    assert all(option.why_not for option in outcome.excluded)


def test_main_query_runner_up() -> None:
    option = by_restaurant(main_outcome().ranked, "Dum Pukht House")
    assert option.why_not == (
        "Scores 0.5208 vs 0.5961: mainly rating (4.6 from 2,140 ratings vs 4.8 from 950)."
    )


def test_main_query_cheaper_option_names_its_win() -> None:
    option = by_restaurant(main_outcome().ranked, "Biryani Junction")
    assert option.why_not == (
        "Scores 0.2479 vs 0.5961: mainly rating (3.4 from 410 ratings vs 4.8 from 950). "
        "It is ₹55 cheaper, but price carries 21% of the score here."
    )


def test_unknown_rating_is_named() -> None:
    option = by_restaurant(main_outcome().ranked, "Spice Route Kitchen")
    assert option.why_not == (
        "Scores 0.3500 vs 0.5961: mainly rating (no rating listed vs 4.8 from 950)."
    )


def test_filtered_out_lists_every_violation() -> None:
    excluded = main_outcome().excluded
    chicken = next(option for option in excluded if option.best.listing.diet == "non_veg")
    assert chicken.why_not == "Filtered out: not vegetarian; ₹349 is over your ₹300 budget."


def test_faster_option_names_its_delivery_win() -> None:
    top = make_listing(
        "bitebox:a", "Alpha", "Powai", "Paneer Roll", "veg", 20000, 4.8, 1000, (40, 40)
    )
    other = make_listing(
        "bitebox:b", "Beta", "Powai", "Paneer Roll", "veg", 20000, 3.0, 2000, (30, 30)
    )
    parsed = ParsedRequest(intent="discovery", dish="paneer roll")
    outcome = with_why_not(rank([make_group("a", [top]), make_group("b", [other])], parsed))
    assert [option.restaurant for option in outcome.ranked] == ["Alpha", "Beta"]
    assert outcome.ranked[1].why_not == (
        "Scores 0.4595 vs 0.4955: mainly rating (3.0 from 2,000 ratings vs 4.8 from 1,000). "
        "It arrives 10 min sooner, but delivery time carries 30% of the score here."
    )


def test_nothing_ranked_marks_every_option_filtered() -> None:
    parsed = main_parsed().model_copy(update={"max_price_inr": 100})
    outcome = with_why_not(rank(main_groups(), parsed))
    assert not outcome.ranked
    assert all(option.why_not.startswith("Filtered out: ") for option in outcome.excluded)
    assert all(option.why_not for option in outcome.closest)
