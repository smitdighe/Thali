lazy import math

lazy from thali.models import Listing, ParsedRequest, RefineAction
lazy from thali.parsing.rules import finalize

FIELDS: dict[str, str] = {
    "dish": "dish",
    "cuisine": "cuisine",
    "ingredients": "ingredients",
    "diet": "diet",
    "budget": "max_price_inr",
    "delivery_time": "max_eta_min",
    "min_rating": "min_rating",
    "rating_preference": "rating_preference",
    "price_preference": "price_preference",
    "speed_preference": "speed_preference",
    "location": "location",
    "other_preferences": "other_preferences",
}

ACTION_LABELS = {"cheaper": "Cheaper", "faster": "Faster", "better_rated": "Better rated"}

MAX_RATING = 5.0


def drop_label(name: str) -> str:
    return f"Remove {name.replace('_', ' ')}"


def is_set(parsed: ParsedRequest, name: str) -> bool:
    value = getattr(parsed, FIELDS[name])
    return value is not None and value != []


def refined(
    stored: ParsedRequest,
    updated: ParsedRequest,
    request_id: str,
    followup: ParsedRequest | None = None,
) -> ParsedRequest:
    adjusted = [
        name for name, attr in FIELDS.items() if getattr(updated, attr) != getattr(stored, attr)
    ]
    carried = [name for name in FIELDS if is_set(updated, name) and name not in adjusted]
    intent = stored.intent
    if intent == "clarification":
        intent = "discovery"
        if followup is not None and followup.intent != "clarification":
            intent = followup.intent
    update: dict[str, object] = {
        "intent": intent,
        "adjusted": adjusted,
        "carried_over": carried,
        "refined_from": request_id,
        "spans": [],
    }
    if followup is not None:
        update["spans"] = followup.spans
        update["notes"] = followup.notes
        update["parser"] = followup.parser
    return finalize(updated.model_copy(update=update))


def apply_action(
    parsed: ParsedRequest, pick: Listing, action: RefineAction, request_id: str
) -> ParsedRequest:
    update: dict[str, object] = {}
    if action == "cheaper":
        update["price_preference"] = "low"
        if pick.effective_price_paise is not None:
            update["max_price_inr"] = math.ceil(pick.effective_price_paise / 100) - 1
    elif action == "faster":
        update["speed_preference"] = "fast"
        if pick.eta_min_high is not None:
            update["max_eta_min"] = pick.eta_min_high - 1
    else:
        update["rating_preference"] = "high"
        if pick.rating is not None:
            update["min_rating"] = round(min(MAX_RATING, pick.rating + 0.1), 1)
    return refined(parsed, parsed.model_copy(update=update), request_id)


def apply_drop(parsed: ParsedRequest, name: str, request_id: str) -> ParsedRequest:
    attr = FIELDS[name]
    cleared: list[str] | None = [] if isinstance(getattr(parsed, attr), list) else None
    return refined(parsed, parsed.model_copy(update={attr: cleared}), request_id)


def merge_text(stored: ParsedRequest, followup: ParsedRequest, request_id: str) -> ParsedRequest:
    update = {
        attr: getattr(followup, attr) for name, attr in FIELDS.items() if is_set(followup, name)
    }
    return refined(stored, stored.model_copy(update=update), request_id, followup)
