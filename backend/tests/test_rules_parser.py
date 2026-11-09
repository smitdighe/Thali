import pytest

from thali.parsing.rules import (
    extract_budget,
    extract_delivery,
    extract_min_rating,
    parse_rules,
)

MAIN_QUERY = (
    "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. "
    "I prefer highly rated restaurants."
)

QUERIES = [
    MAIN_QUERY,
    "suggest some biryani",
    "Jain food, not spicy, in Andheri West",
    "non-veg biryani with chicken, 4+ stars, below rs 400",
    "biryani for under 300, delivered in 25-35 minutes",
    "order a masala dosa from Dadar",
    "what's the price of a veg burger in Lower Parel?",
    "within 45",
]


def test_main_query_fields():
    parsed = parse_rules(MAIN_QUERY)
    assert parsed.intent == "discovery"
    assert parsed.dish == "biryani"
    assert parsed.diet == "veg"
    assert parsed.max_price_inr == 300
    assert parsed.max_eta_min == 30
    assert parsed.rating_preference == "high"
    assert parsed.cuisine is None
    assert parsed.ingredients == []
    assert parsed.min_rating is None
    assert parsed.price_preference is None
    assert parsed.speed_preference is None
    assert parsed.location is None
    assert parsed.other_preferences == []
    assert parsed.missing == ["location"]
    assert parsed.notes == []
    assert parsed.parser == "rules"


def test_main_query_spans():
    spans = parse_rules(MAIN_QUERY).spans
    assert [(s.field, s.text, s.start, s.end, s.source) for s in spans] == [
        ("diet", "vegetarian", 10, 20, "rules"),
        ("dish", "biryani", 21, 28, "rules"),
        ("budget", "under ₹300", 29, 39, "rules"),
        ("delivery_time", "within 30 minutes", 56, 73, "rules"),
        ("rating_preference", "highly rated", 84, 96, "rules"),
    ]


@pytest.mark.parametrize("query", QUERIES)
def test_spans_index_original_text(query):
    for span in parse_rules(query).spans:
        assert query[span.start : span.end] == span.text


def test_jain_sets_veg_and_preference_with_overlapping_spans():
    parsed = parse_rules("Jain food, not spicy, in Andheri West")
    assert parsed.diet == "veg"
    assert parsed.other_preferences == ["jain", "not spicy"]
    assert parsed.location == "Andheri West"
    jain_fields = {s.field for s in parsed.spans if s.text == "Jain"}
    assert jain_fields == {"diet", "other_preferences"}


@pytest.mark.parametrize(
    "query",
    ["non-veg biryani", "Non Veg thali", "nonveg kebab", "non-vegetarian food", "NON-VEG"],
)
def test_non_veg_never_yields_veg(query):
    assert parse_rules(query).diet == "non_veg"


@pytest.mark.parametrize(
    ("query", "diet"),
    [
        ("vegan food", "vegan"),
        ("eggetarian options", "egg"),
        ("pure veg thali", "veg"),
        ("veggie pizza", "veg"),
    ],
)
def test_other_diet_forms(query, diet):
    assert parse_rules(query).diet == diet


def test_egg_ingredient_is_not_a_diet():
    parsed = parse_rules("egg biryani")
    assert parsed.diet is None
    assert parsed.ingredients == ["egg"]


def test_fields_cannot_reuse_claimed_characters():
    parsed = parse_rules("paneer tikka")
    assert parsed.dish == "paneer tikka"
    assert parsed.ingredients == []


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("under ₹300", 300),
        ("below rs 400", 400),
        ("less than Rs. 250", 250),
        ("max ₹150", 150),
        ("₹200 max", 200),
        ("budget 500", 500),
        ("budget of ₹450", 450),
        ("up to 350", 350),
        ("upto 350", 350),
        ("for under 300", 300),
        ("200 tops", 200),
        ("300 rupees", 300),
        ("300 bucks", 300),
        ("300 rs", 300),
        ("within 300", 300),
    ],
)
def test_budget_values_without_notes(text, value):
    result = extract_budget(text)
    assert result is not None
    assert result.value == value
    assert result.note is None


def test_budget_bare_symbol_adds_note():
    result = extract_budget("I have ₹300")
    assert result is not None
    assert result.value == 300
    assert result.note == "treated “₹300” as your budget"


def test_budget_without_unit_below_hundred_is_ignored():
    result = extract_budget("under 80")
    assert result is not None
    assert result.value is None
    assert result.note == "“under 80” has no unit, so it was ignored"


def test_budget_ignores_time_phrases():
    assert extract_budget("under 20 min") is None
    assert extract_budget("within 30 minutes") is None


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("within 30 minutes", 30),
        ("in 30 mins", 30),
        ("under 20 min", 20),
        ("30 min delivery", 30),
        ("in 25-35 minutes", 35),
        ("within an hour", 60),
        ("in an hour", 60),
        ("in 1 hour", 60),
        ("1 hr", 60),
        ("half an hour", 30),
    ],
)
def test_delivery_values(text, value):
    result = extract_delivery(text)
    assert result is not None
    assert result.value == value
    assert result.note is None


def test_delivery_unitless_within_is_ignored_with_note():
    result = extract_delivery("within 45")
    assert result is not None
    assert result.value is None
    assert result.note == "“within 45” has no unit (₹ or minutes?), so it was ignored"


@pytest.mark.parametrize(
    ("text", "value"),
    [
        ("4+ stars", 4.0),
        ("4.2+ rating", 4.2),
        ("rated at least 4.5", 4.5),
        ("at least 4 stars", 4.0),
        ("minimum 4 rating", 4.0),
        ("4 stars and above", 4.0),
        ("above 4.0 rating", 4.0),
        ("rated 4.5 or more", 4.5),
    ],
)
def test_min_rating_values(text, value):
    result = extract_min_rating(text)
    assert result is not None
    assert result.value == value


@pytest.mark.parametrize("text", ["rated 7 stars", "0 stars", "300 ratings", "4 people"])
def test_min_rating_rejects_out_of_range_or_no_cue(text):
    assert extract_min_rating(text) is None


def test_within_45_gives_one_note_and_clarification():
    parsed = parse_rules("within 45")
    assert parsed.notes == ["“within 45” has no unit (₹ or minutes?), so it was ignored"]
    assert parsed.intent == "clarification"
    assert parsed.max_eta_min is None
    assert parsed.max_price_inr is None
    assert parsed.spans == []


def test_under_80_in_query_adds_note_and_leaves_budget_null():
    parsed = parse_rules("biryani under 80")
    assert parsed.max_price_inr is None
    assert parsed.notes == ["“under 80” has no unit, so it was ignored"]


def test_budget_and_delivery_do_not_share_numbers():
    parsed = parse_rules("something under 200 in 20 mins")
    assert parsed.max_price_inr == 200
    assert parsed.max_eta_min == 20


def test_min_rating_in_query_with_budget():
    parsed = parse_rules("non-veg biryani with chicken, 4+ stars, below rs 400")
    assert parsed.min_rating == 4.0
    assert parsed.max_price_inr == 400
    assert parsed.ingredients == ["chicken"]
    assert parsed.diet == "non_veg"


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("order a masala dosa from Dadar", "action"),
        ("how much does a gujarati thali cost in Dadar?", "information"),
        ("what's the price of a veg burger in Lower Parel?", "information"),
        ("Which biryani place is better in Bandra, under 350?", "decision"),
        ("suggest some biryani", "discovery"),
        ("hi", "clarification"),
        ("order", "clarification"),
    ],
)
def test_intent(query, intent):
    assert parse_rules(query).intent == intent


def test_missing_order_for_bare_dish():
    parsed = parse_rules("suggest some biryani")
    assert parsed.missing == ["diet", "budget", "delivery_time", "rating", "location"]


def test_area_aliases_resolve_to_canonical_names():
    assert parse_rules("pizza in Bandra").location == "Bandra West"
    assert parse_rules("pizza in andheri (w)").location == "Andheri West"
    assert parse_rules("pizza near Dadar").location == "Dadar"


def test_whole_words_only():
    parsed = parse_rules("top rated south indian breakfast near Dadar")
    assert parsed.speed_preference is None
    assert parsed.cuisine == "south indian"
