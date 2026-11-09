import re
lazy from collections.abc import Callable, Mapping, Sequence
lazy from operator import attrgetter

lazy from thali.models import Intent, ParsedRequest, Span
lazy from thali.parsing.lexicon import CUISINES, DISHES
lazy from thali.parsing.llm import Evidence, LlmExtraction, ValueEvidence
lazy from thali.parsing.rules import (
    Extract,
    Range,
    extract_budget,
    extract_delivery,
    extract_min_rating,
    finalize,
    phrase_pairs,
    phrase_regex,
)
lazy from thali.text import canonical_area

DIETS = frozenset({"veg", "vegan", "egg", "non_veg"})
INTENTS = frozenset({"discovery", "decision", "information", "clarification", "action"})
BACKFILL = (
    ("dish", "dish"),
    ("cuisine", "cuisine"),
    ("ingredients", "ingredients"),
    ("diet", "diet"),
    ("max_price_inr", "budget"),
    ("max_eta_min", "delivery_time"),
    ("min_rating", "min_rating"),
    ("rating_preference", "rating_preference"),
    ("price_preference", "price_preference"),
    ("speed_preference", "speed_preference"),
    ("location", "location"),
    ("other_preferences", "other_preferences"),
)


def locate(query: str, evidence: str) -> tuple[int, int] | None:
    words = evidence.split()
    if not words:
        return None
    pattern = r"\s+".join(re.escape(word) for word in words)
    match = re.search(pattern, query, re.IGNORECASE)
    return (match.start(), match.end()) if match else None


def canonical_key(texts: Sequence[str], vocabulary: Mapping[str, Sequence[str]]) -> str | None:
    for text in texts:
        for phrase, key in phrase_pairs(vocabulary):
            if phrase_regex(phrase).search(text):
                return key
    return None


def is_empty(value: object) -> bool:
    return value is None or value == []


class _Grounder:
    def __init__(self, query: str) -> None:
        self.query = query
        self.spans: list[Span] = []
        self.notes: list[str] = []

    def note(self, text: str | None) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    def found(self, field: str, evidence: str) -> tuple[int, int] | None:
        position = locate(self.query, evidence)
        if position is None:
            self.note(f"dropped {field}: “{evidence}” is not in the request")
        return position

    def accept(self, field: str, position: tuple[int, int]) -> None:
        start, end = position
        text = self.query[start:end]
        self.spans.append(Span(field=field, text=text, start=start, end=end, source="llm"))

    def number(
        self,
        field: str,
        item: Evidence | None,
        extractor: Callable[[str, Sequence[Range]], Extract | None],
    ) -> int | float | None:
        if item is None:
            return None
        position = self.found(field, item.evidence)
        if position is None:
            return None
        result = extractor(self.query[position[0] : position[1]], ())
        if result is None or result.value is None:
            self.note(f"dropped {field}: no usable number in “{item.evidence}”")
            return None
        self.note(result.note)
        self.accept(field, position)
        return result.value

    def flag(self, field: str, item: Evidence | None) -> bool:
        if item is None:
            return False
        position = self.found(field, item.evidence)
        if position is None:
            return False
        self.accept(field, position)
        return True

    def canonical(
        self,
        field: str,
        item: ValueEvidence | None,
        vocabulary: Mapping[str, Sequence[str]],
    ) -> str | None:
        if item is None or not item.value.strip():
            return None
        position = self.found(field, item.evidence)
        if position is None:
            return None
        self.accept(field, position)
        key = canonical_key([item.value.lower(), item.evidence.lower()], vocabulary)
        return key or item.value.strip().lower()

    def diet(self, item: ValueEvidence | None) -> str | None:
        if item is None:
            return None
        position = self.found("diet", item.evidence)
        if position is None:
            return None
        value = item.value.strip().lower()
        if value not in DIETS:
            self.note(f"dropped diet: “{item.value}” is not a known diet")
            return None
        self.accept("diet", position)
        return value

    def location(self, item: ValueEvidence | None) -> str | None:
        if item is None:
            return None
        position = self.found("location", item.evidence)
        area = canonical_area(item.value)
        if position is None or area is None:
            return None
        self.accept("location", position)
        return area

    def items(self, field: str, entries: Sequence[ValueEvidence]) -> list[str]:
        values: list[str] = []
        for entry in entries:
            position = self.found(field, entry.evidence)
            value = entry.value.strip().lower()
            if position is None or not value:
                continue
            self.accept(field, position)
            if value not in values:
                values.append(value)
        return values


def _backfill(values: dict[str, object], rules: ParsedRequest, spans: list[Span]) -> None:
    for attribute, span_field in BACKFILL:
        if is_empty(values[attribute]):
            values[attribute] = getattr(rules, attribute)
            spans.extend(span for span in rules.spans if span.field == span_field)


def ground(query: str, extraction: LlmExtraction, rules: ParsedRequest) -> ParsedRequest:
    grounder = _Grounder(query)
    max_price = grounder.number("budget", extraction.budget, extract_budget)
    max_eta = grounder.number("delivery_time", extraction.delivery_time, extract_delivery)
    min_rating = grounder.number("min_rating", extraction.min_rating, extract_min_rating)
    rating_high = grounder.flag("rating_preference", extraction.prefers_high_rating)
    price_low = grounder.flag("price_preference", extraction.prefers_low_price)
    speed_fast = grounder.flag("speed_preference", extraction.prefers_fast_delivery)
    values: dict[str, object] = {
        "dish": grounder.canonical("dish", extraction.dish, DISHES),
        "cuisine": grounder.canonical("cuisine", extraction.cuisine, CUISINES),
        "ingredients": grounder.items("ingredients", extraction.ingredients),
        "diet": grounder.diet(extraction.diet),
        "max_price_inr": None if max_price is None else int(max_price),
        "max_eta_min": None if max_eta is None else int(max_eta),
        "min_rating": None if min_rating is None else float(min_rating),
        "rating_preference": "high" if rating_high else None,
        "price_preference": "low" if price_low else None,
        "speed_preference": "fast" if speed_fast else None,
        "location": grounder.location(extraction.location),
        "other_preferences": grounder.items("other_preferences", extraction.other_preferences),
    }
    spans = list(grounder.spans)
    _backfill(values, rules, spans)
    intent: Intent = extraction.intent if extraction.intent in INTENTS else rules.intent
    notes = list(grounder.notes)
    notes.extend(note for note in rules.notes if note not in notes)
    parsed = ParsedRequest.model_validate(
        {
            **values,
            "intent": intent,
            "spans": sorted(spans, key=attrgetter("start")),
            "notes": notes,
            "parser": "llm",
        }
    )
    return finalize(parsed)
