import re
from typing import NamedTuple
lazy from collections.abc import Callable, Mapping, Sequence
lazy from operator import attrgetter

from pydantic import BaseModel

lazy from thali.models import Intent, ParsedRequest, Span
lazy from thali.parsing.lexicon import (
    CUISINES,
    DIETS,
    DISHES,
    INGREDIENTS,
    JAIN,
    OTHER_PREFERENCES,
    PRICE_LOW,
    RATING_HIGH,
    SPEED_FAST,
)
lazy from thali.text import AREAS

MIN_BARE_BUDGET = 100
MAX_RATING = 5

_FLAGS = re.IGNORECASE
_NUM = r"\d+(?:,\d{3})*(?:\.\d+)?"
_NUM_END = r"(?![.,]?\d)"
_CURRENCY = r"(?:₹|(?<!\w)rs\.?(?![a-z])|(?<!\w)inr(?![a-z]))"
_CURRENCY_WORD = r"(?:rupees?|bucks?|rs\.?(?![a-z])|inr(?![a-z]))"
_TIME_UNIT = r"(?:minutes?|mins?|hours?|hrs?)"
_RATING_WORD = r"(?:stars?|ratings?|★)"
_NOT_TIME_OR_RATING = rf"(?!\s*(?:{_TIME_UNIT}|{_RATING_WORD})(?!\w))"
_BUDGET_CUE = (
    r"for\s+under|not\s+more\s+than|no\s+more\s+than|less\s+than|budget\s+of|up\s+to|upto"
    r"|under|below|within|maximum|max|budget"
)
_DELIVERY_CUE = (
    r"(?:(?<!\w)(?:within|inside|under|below|before|less\s+than|upto|up\s+to|maximum|max|in)\s+)?"
)
_AT_LEAST = r"(?:at\s+least|atleast|minimum|min|above|over|more\s+than|>=|>)"
_AND_ABOVE = r"(?:\s+(?:and|or)\s+(?:above|up|more|higher|better|plus))"

_BUDGET_PATTERNS = (
    (
        "cued",
        re.compile(
            rf"(?<!\w)(?P<cue>{_BUDGET_CUE})\s*(?P<cur>{_CURRENCY})?\s*(?P<num>{_NUM}){_NUM_END}"
            rf"(?:\s*(?P<tail>{_CURRENCY_WORD}))?{_NOT_TIME_OR_RATING}",
            _FLAGS,
        ),
    ),
    (
        "suffixed",
        re.compile(
            rf"(?<![\w.])(?:(?P<cur>{_CURRENCY})\s*)?(?P<num>{_NUM}){_NUM_END}"
            rf"(?:\s*(?P<tail>{_CURRENCY_WORD}))?\s*(?:tops|maximum|max)(?!\w)",
            _FLAGS,
        ),
    ),
    (
        "unit",
        re.compile(rf"(?<![\w.])(?P<num>{_NUM}){_NUM_END}\s*(?P<tail>{_CURRENCY_WORD})", _FLAGS),
    ),
    (
        "symbol",
        re.compile(rf"(?P<cur>{_CURRENCY})\s*(?P<num>{_NUM}){_NUM_END}", _FLAGS),
    ),
)

_HALF_HOUR = re.compile(rf"{_DELIVERY_CUE}half\s+(?:an?\s+)?hour(?!\w)", _FLAGS)
_ONE_HOUR = re.compile(
    r"(?<!\w)(?:within|inside|under|less\s+than|in)\s+(?:an?|one)\s+(?:hour|hr)(?!\w)", _FLAGS
)
_TIMED = re.compile(
    rf"{_DELIVERY_CUE}(?<![\w.₹,])(?P<low>{_NUM}){_NUM_END}\s*"
    rf"(?:(?:-|–|to)\s*(?P<high>{_NUM}){_NUM_END}\s*)?(?P<unit>{_TIME_UNIT})(?!\w)",
    _FLAGS,
)
_UNITLESS_WITHIN = re.compile(
    rf"(?<!\w)within\s+(?P<num>{_NUM}){_NUM_END}"
    rf"(?!\s*(?:{_TIME_UNIT}|{_CURRENCY_WORD}|₹|{_RATING_WORD})(?!\w))",
    _FLAGS,
)

_RATING_PATTERNS = (
    re.compile(
        rf"(?<!\w){_AT_LEAST}\s*(?P<num>{_NUM}){_NUM_END}\s*\+?\s*{_RATING_WORD}(?!\w)", _FLAGS
    ),
    re.compile(
        rf"(?<!\w)(?:rated|ratings?)\s+(?:(?:{_AT_LEAST}|of)\s*)?(?P<num>{_NUM}){_NUM_END}"
        rf"(?:\s*\+|{_AND_ABOVE})?",
        _FLAGS,
    ),
    re.compile(
        rf"(?<![\w.])(?P<num>{_NUM}){_NUM_END}\s*\+?\s*{_RATING_WORD}(?!\w){_AND_ABOVE}?",
        _FLAGS,
    ),
)

_ACTION = re.compile(r"\b(order|book|place an order|add to cart|buy)\b", _FLAGS)
_INFORMATION = re.compile(r"^\s*(what|what's|whats|how)\b|\b(how much|price of|cost of)\b", _FLAGS)
_DECISION = re.compile(r"\b(which|better|best|vs|versus|compare|should i|choose|decide)\b", _FLAGS)

Range = tuple[int, int]


class Extract(BaseModel):
    value: int | float | None
    start: int
    end: int
    note: str | None = None


class Hit(NamedTuple):
    key: str
    start: int
    end: int


class Claims:
    def __init__(self) -> None:
        self.ranges: list[Range] = []

    def free(self, start: int, end: int) -> bool:
        return is_free(start, end, self.ranges)

    def add(self, start: int, end: int) -> None:
        self.ranges.append((start, end))


def is_free(start: int, end: int, taken: Sequence[Range]) -> bool:
    return all(end <= taken_start or start >= taken_end for taken_start, taken_end in taken)


def phrase_regex(phrase: str) -> re.Pattern[str]:
    body = r"\s+".join(re.escape(word) for word in phrase.split())
    return re.compile(rf"(?<!\w){body}(?!\w)", _FLAGS)


def _pair_length(pair: tuple[str, str]) -> int:
    return len(pair[0])


def phrase_pairs(vocabulary: Mapping[str, Sequence[str]]) -> list[tuple[str, str]]:
    pairs = [(phrase, key) for key, phrases in vocabulary.items() for phrase in phrases]
    return sorted(pairs, key=_pair_length, reverse=True)


def find_hits(text: str, vocabulary: Mapping[str, Sequence[str]], claims: Claims) -> list[Hit]:
    hits: list[Hit] = []
    for phrase, key in phrase_pairs(vocabulary):
        for match in phrase_regex(phrase).finditer(text):
            if claims.free(match.start(), match.end()):
                claims.add(match.start(), match.end())
                hits.append(Hit(key, match.start(), match.end()))
    return sorted(hits, key=attrgetter("start"))


def _number(raw: str) -> float:
    return float(raw.replace(",", ""))


def _budget_candidate(kind: str, match: re.Match[str]) -> Extract | None:
    groups = match.groupdict()
    amount = int(_number(groups["num"]))
    start, end, shown = match.start(), match.end(), match.group(0)
    if kind == "symbol":
        return Extract(value=amount, start=start, end=end, note=f"treated “{shown}” as your budget")
    if groups.get("cur") or groups.get("tail") or amount >= MIN_BARE_BUDGET:
        return Extract(value=amount, start=start, end=end)
    if (groups.get("cue") or "").lower() == "within":
        return None
    note = f"“{shown}” has no unit, so it was ignored"
    return Extract(value=None, start=start, end=end, note=note)


def extract_budget(text: str, taken: Sequence[Range] = ()) -> Extract | None:
    ignored: Extract | None = None
    for kind, pattern in _BUDGET_PATTERNS:
        for match in pattern.finditer(text):
            if not is_free(match.start(), match.end(), taken):
                continue
            candidate = _budget_candidate(kind, match)
            if candidate is None:
                continue
            if candidate.value is not None:
                return candidate
            ignored = ignored or candidate
    return ignored


def _minutes(low: str, high: str | None, unit: str) -> int:
    amount = _number(high or low)
    return round(amount * 60) if unit.lower().startswith("h") else round(amount)


def _delivery_candidates(text: str) -> list[Extract]:
    found: list[Extract] = []
    for match in _HALF_HOUR.finditer(text):
        found.append(Extract(value=30, start=match.start(), end=match.end()))
    for match in _ONE_HOUR.finditer(text):
        found.append(Extract(value=60, start=match.start(), end=match.end()))
    for match in _TIMED.finditer(text):
        minutes = _minutes(match["low"], match["high"], match["unit"])
        if minutes > 0:
            found.append(Extract(value=minutes, start=match.start(), end=match.end()))
    return found


def _unitless_within(text: str) -> list[Extract]:
    found: list[Extract] = []
    for match in _UNITLESS_WITHIN.finditer(text):
        if _number(match["num"]) < MIN_BARE_BUDGET:
            note = f"“{match.group(0)}” has no unit (₹ or minutes?), so it was ignored"
            found.append(Extract(value=None, start=match.start(), end=match.end(), note=note))
    return found


def extract_delivery(text: str, taken: Sequence[Range] = ()) -> Extract | None:
    for candidate in _delivery_candidates(text):
        if is_free(candidate.start, candidate.end, taken):
            return candidate
    for candidate in _unitless_within(text):
        if is_free(candidate.start, candidate.end, taken):
            return candidate
    return None


def extract_min_rating(text: str, taken: Sequence[Range] = ()) -> Extract | None:
    for pattern in _RATING_PATTERNS:
        for match in pattern.finditer(text):
            value = _number(match["num"])
            if 0 < value <= MAX_RATING and is_free(match.start(), match.end(), taken):
                return Extract(value=value, start=match.start(), end=match.end())
    return None


class _Draft:
    def __init__(self, query: str) -> None:
        self.query = query
        self.claims = Claims()
        self.spans: list[Span] = []
        self.notes: list[str] = []

    def span(self, field: str, start: int, end: int) -> None:
        text = self.query[start:end]
        self.spans.append(Span(field=field, text=text, start=start, end=end, source="rules"))

    def note(self, text: str | None) -> None:
        if text and text not in self.notes:
            self.notes.append(text)

    def hits(self, vocabulary: Mapping[str, Sequence[str]]) -> list[Hit]:
        return find_hits(self.query, vocabulary, self.claims)

    def first(self, field: str, vocabulary: Mapping[str, Sequence[str]]) -> str | None:
        found = self.hits(vocabulary)
        if not found:
            return None
        self.span(field, found[0].start, found[0].end)
        return found[0].key

    def every(self, field: str, vocabulary: Mapping[str, Sequence[str]]) -> list[str]:
        values: list[str] = []
        for hit in self.hits(vocabulary):
            self.span(field, hit.start, hit.end)
            if hit.key not in values:
                values.append(hit.key)
        return values

    def extract(
        self, field: str, extractor: Callable[[str, Sequence[Range]], Extract | None]
    ) -> int | float | None:
        result = extractor(self.query, self.claims.ranges)
        if result is None:
            return None
        self.note(result.note)
        if result.value is None:
            return None
        self.claims.add(result.start, result.end)
        self.span(field, result.start, result.end)
        return result.value


def _diet(draft: _Draft) -> tuple[str | None, Hit | None]:
    diet: str | None = None
    for key, phrases in DIETS.items():
        found = draft.hits({key: phrases})
        if found and diet is None:
            diet = key
            draft.span("diet", found[0].start, found[0].end)
    jain = draft.hits({JAIN: (JAIN,)})
    if not jain:
        return diet, None
    if diet is None:
        diet = "veg"
        draft.span("diet", jain[0].start, jain[0].end)
    return diet, jain[0]


def _other_preferences(draft: _Draft, jain: Hit | None) -> list[str]:
    found = [
        (hit.start, hit.key, hit.end) for hit in draft.hits({p: (p,) for p in OTHER_PREFERENCES})
    ]
    if jain is not None:
        found.append((jain.start, JAIN, jain.end))
    values: list[str] = []
    for start, value, end in sorted(found):
        draft.span("other_preferences", start, end)
        if value not in values:
            values.append(value)
    return values


def _intent(query: str) -> Intent:
    if _ACTION.search(query):
        return "action"
    if _INFORMATION.search(query):
        return "information"
    if _DECISION.search(query):
        return "decision"
    return "discovery"


def has_content(parsed: ParsedRequest) -> bool:
    return any(
        (
            parsed.dish,
            parsed.cuisine,
            parsed.ingredients,
            parsed.diet,
            parsed.max_price_inr,
            parsed.max_eta_min,
            parsed.min_rating,
            parsed.rating_preference,
            parsed.price_preference,
            parsed.speed_preference,
            parsed.location,
            parsed.other_preferences,
        )
    )


def _missing(parsed: ParsedRequest) -> list[str]:
    gaps = {
        "food": not (parsed.dish or parsed.cuisine or parsed.ingredients),
        "diet": parsed.diet is None,
        "budget": parsed.max_price_inr is None,
        "delivery_time": parsed.max_eta_min is None,
        "rating": parsed.min_rating is None and parsed.rating_preference is None,
        "location": parsed.location is None,
    }
    return [name for name, absent in gaps.items() if absent]


def finalize(parsed: ParsedRequest) -> ParsedRequest:
    intent = parsed.intent if has_content(parsed) else "clarification"
    return parsed.model_copy(update={"intent": intent, "missing": _missing(parsed)})


def _sorted_spans(spans: list[Span]) -> list[Span]:
    return sorted(spans, key=attrgetter("start"))


def parse_rules(query: str) -> ParsedRequest:
    draft = _Draft(query)
    diet, jain = _diet(draft)
    dish = draft.first("dish", DISHES)
    cuisine = draft.first("cuisine", CUISINES)
    ingredients = draft.every("ingredients", {name: (name,) for name in INGREDIENTS})
    location = draft.first("location", AREAS)
    max_price = draft.extract("budget", extract_budget)
    max_eta = draft.extract("delivery_time", extract_delivery)
    min_rating = draft.extract("min_rating", extract_min_rating)
    rating_high = draft.first("rating_preference", {"high": RATING_HIGH})
    price_low = draft.first("price_preference", {"low": PRICE_LOW})
    speed_fast = draft.first("speed_preference", {"fast": SPEED_FAST})
    others = _other_preferences(draft, jain)
    parsed = ParsedRequest(
        intent=_intent(query),
        dish=dish,
        cuisine=cuisine,
        ingredients=ingredients,
        diet=diet,
        max_price_inr=None if max_price is None else int(max_price),
        max_eta_min=None if max_eta is None else int(max_eta),
        min_rating=None if min_rating is None else float(min_rating),
        rating_preference="high" if rating_high else None,
        price_preference="low" if price_low else None,
        speed_preference="fast" if speed_fast else None,
        location=location,
        other_preferences=others,
        spans=_sorted_spans(draft.spans),
        notes=draft.notes,
        parser="rules",
    )
    return finalize(parsed)
