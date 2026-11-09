from thali.parsing.grounding import ground
from thali.parsing.llm import Evidence, LlmExtraction, ValueEvidence
from thali.parsing.rules import parse_rules

MAIN_QUERY = (
    "Find me a vegetarian biryani under ₹300 that can arrive within 30 minutes. "
    "I prefer highly rated restaurants."
)


def run(query: str, **fields):
    extraction = LlmExtraction(intent=fields.pop("intent", "discovery"), **fields)
    return ground(query, extraction, parse_rules(query))


def test_grounded_evidence_is_accepted():
    parsed = run(
        MAIN_QUERY,
        dish=ValueEvidence(value="biryani", evidence="biryani"),
        diet=ValueEvidence(value="veg", evidence="vegetarian"),
        budget=Evidence(evidence="under ₹300"),
        delivery_time=Evidence(evidence="within 30 minutes"),
        prefers_high_rating=Evidence(evidence="highly rated"),
    )
    assert parsed.parser == "llm"
    assert parsed.dish == "biryani"
    assert parsed.diet == "veg"
    assert parsed.max_price_inr == 300
    assert parsed.max_eta_min == 30
    assert parsed.rating_preference == "high"
    assert parsed.notes == []
    assert {s.source for s in parsed.spans} == {"llm"}
    for span in parsed.spans:
        assert MAIN_QUERY[span.start : span.end] == span.text


def test_evidence_matches_case_and_whitespace_insensitively():
    query = "get me a Vegetarian   BIRYANI"
    parsed = run(
        query,
        diet=ValueEvidence(value="veg", evidence="vegetarian"),
        dish=ValueEvidence(value="biryani", evidence="vegetarian biryani"),
    )
    assert parsed.diet == "veg"
    spans = {s.field: s for s in parsed.spans}
    assert query[spans["dish"].start : spans["dish"].end] == "Vegetarian   BIRYANI"
    assert spans["dish"].text == "Vegetarian   BIRYANI"


def test_evidence_not_in_query_is_dropped_with_note():
    parsed = run(
        "suggest some biryani",
        diet=ValueEvidence(value="veg", evidence="vegetarian"),
    )
    assert parsed.diet is None
    assert parsed.notes == ["dropped diet: “vegetarian” is not in the request"]
    assert "diet" in parsed.missing


def test_number_is_rederived_from_evidence():
    parsed = run(
        "biryani under ₹300",
        budget=Evidence(evidence="under ₹300"),
    )
    assert parsed.max_price_inr == 300


def test_model_number_is_ignored_even_when_evidence_differs():
    extraction = LlmExtraction.model_validate(
        {"intent": "discovery", "budget": {"evidence": "under ₹300", "value": 350}}
    )
    query = "biryani under ₹300"
    parsed = ground(query, extraction, parse_rules(query))
    assert parsed.max_price_inr == 300


def test_evidence_without_usable_number_is_dropped():
    query = "biryani under 80"
    parsed = run(query, budget=Evidence(evidence="under 80"))
    assert parsed.max_price_inr is None
    assert "dropped budget: no usable number in “under 80”" in parsed.notes


def test_delivery_and_rating_numbers_come_from_code():
    query = "biryani in 25-35 minutes, 4+ stars"
    parsed = run(
        query,
        delivery_time=Evidence(evidence="in 25-35 minutes"),
        min_rating=Evidence(evidence="4+ stars"),
    )
    assert parsed.max_eta_min == 35
    assert parsed.min_rating == 4.0


def test_unknown_location_is_kept_as_text():
    parsed = run(
        "veg pizza near Juhu Beach",
        location=ValueEvidence(value=" Juhu Beach ", evidence="Juhu Beach"),
    )
    assert parsed.location == "Juhu Beach"


def test_known_location_is_canonicalised():
    parsed = run(
        "veg pizza in bandra",
        location=ValueEvidence(value="bandra", evidence="bandra"),
    )
    assert parsed.location == "Bandra West"


def test_invalid_diet_value_is_dropped():
    parsed = run(
        "keto bowl",
        diet=ValueEvidence(value="keto", evidence="keto"),
    )
    assert parsed.diet is None
    assert parsed.notes == ["dropped diet: “keto” is not a known diet"]


def test_dish_and_cuisine_use_canonical_names():
    parsed = run(
        "some chowmein from a chinese place",
        dish=ValueEvidence(value="Chowmein", evidence="chowmein"),
        cuisine=ValueEvidence(value="Indo Chinese", evidence="chinese"),
    )
    assert parsed.dish == "noodles"
    assert parsed.cuisine == "chinese"


def test_unlisted_dish_is_lowercased():
    parsed = run(
        "plant-based bowl for under 250",
        dish=ValueEvidence(value="Bowl", evidence="bowl"),
    )
    assert parsed.dish == "bowl"


def test_ingredients_and_preferences_are_lowercased_and_grounded():
    parsed = run(
        "Paneer wrap, Extra Cheese, nothing spicy",
        ingredients=[
            ValueEvidence(value="Paneer", evidence="Paneer"),
            ValueEvidence(value="Tofu", evidence="tofu"),
        ],
        other_preferences=[ValueEvidence(value="Nothing Spicy", evidence="nothing spicy")],
    )
    assert parsed.ingredients == ["paneer"]
    assert parsed.other_preferences == ["nothing spicy"]
    assert "dropped ingredients: “tofu” is not in the request" in parsed.notes


def test_preference_flags_need_grounded_evidence():
    parsed = run(
        "cheap pizza",
        prefers_low_price=Evidence(evidence="cheap"),
        prefers_fast_delivery=Evidence(evidence="quickly"),
    )
    assert parsed.price_preference == "low"
    assert parsed.speed_preference is None
    assert parsed.notes == ["dropped speed_preference: “quickly” is not in the request"]


def test_empty_fields_are_backfilled_from_rules():
    query = "cheap veg momos in Powai under ₹200"
    parsed = run(query, dish=ValueEvidence(value="momos", evidence="momos"))
    assert parsed.parser == "llm"
    assert parsed.dish == "momos"
    assert parsed.diet == "veg"
    assert parsed.location == "Powai"
    assert parsed.max_price_inr == 200
    assert parsed.price_preference == "low"
    sources = {s.field: s.source for s in parsed.spans}
    assert sources["dish"] == "llm"
    assert sources["diet"] == "rules"
    assert sources["location"] == "rules"
    assert sources["budget"] == "rules"
    assert [s.start for s in parsed.spans] == sorted(s.start for s in parsed.spans)


def test_llm_value_wins_over_rules_value():
    query = "chicken biryani near Dadar"
    parsed = run(
        query,
        dish=ValueEvidence(value="chicken biryani", evidence="chicken biryani"),
    )
    assert parsed.dish == "biryani"
    assert parsed.ingredients == ["chicken"]


def test_ungrounded_everything_falls_back_to_rules_values():
    query = "veg biryani under 300"
    parsed = run(
        query,
        diet=ValueEvidence(value="vegan", evidence="plant based"),
        budget=Evidence(evidence="below ₹500"),
    )
    assert parsed.diet == "veg"
    assert parsed.max_price_inr == 300
    assert len(parsed.notes) == 2


def test_nothing_extracted_becomes_clarification():
    parsed = run("hi", intent="discovery")
    assert parsed.intent == "clarification"
    assert parsed.parser == "llm"


def test_model_intent_is_used_when_content_exists():
    parsed = run(
        "which biryani is better",
        intent="decision",
        dish=ValueEvidence(value="biryani", evidence="biryani"),
    )
    assert parsed.intent == "decision"


def test_unknown_model_intent_uses_rules_intent():
    query = "order a pizza"
    parsed = run(query, intent="purchase", dish=ValueEvidence(value="pizza", evidence="pizza"))
    assert parsed.intent == "action"


def test_rules_notes_are_kept_once():
    query = "pizza under 80"
    parsed = run(query, dish=ValueEvidence(value="pizza", evidence="pizza"))
    assert parsed.notes == ["“under 80” has no unit, so it was ignored"]
