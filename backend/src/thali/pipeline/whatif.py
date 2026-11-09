from typing import NamedTuple
lazy from collections.abc import Callable, Sequence
lazy from functools import partial

lazy from thali.models import Factor, Listing, OptionGroup, ParsedRequest, WhatIf
lazy from thali.pipeline.fmt import rating_value, rupees
lazy from thali.pipeline.rank import (
    BONUS_CAP,
    BONUS_STEP,
    NO_ETA,
    NO_PRICE,
    Span,
    budget_violations,
    capped_factor,
    delivery_violations,
    preference_matches,
    rank,
    rating_factor,
    rating_violations,
    value_span,
    violations,
    weights,
)

MIN_BUDGET_INR = 50
MIN_ETA_MIN = 5
MAX_RATING_TENTHS = 50
PREFERENCES = (
    ("rating_preference", "highly rated"),
    ("price_preference", "cheaper"),
    ("speed_preference", "fast delivery"),
)

type Check = Callable[[Listing, ParsedRequest], list[str]]


class Candidate(NamedTuple):
    listing: Listing
    item: str
    restaurant: str
    blocked: bool
    rating: float
    bonus: float


class Sweep(NamedTuple):
    last: float
    changed_to: Candidate | None
    changed: bool


def candidates(groups: list[OptionGroup], parsed: ParsedRequest, field: str) -> list[Candidate]:
    loose = parsed.model_copy(update={field: None})
    return [
        Candidate(
            listing=listing,
            item=group.item,
            restaurant=group.restaurant,
            blocked=bool(violations(listing, loose)),
            rating=rating_factor(listing),
            bonus=min(BONUS_STEP * len(preference_matches(listing, parsed)), BONUS_CAP),
        )
        for group in groups
        for listing in group.listings
    ]


def candidate_key(
    candidate: Candidate,
    parsed: ParsedRequest,
    factor_weights: dict[Factor, float],
    price_span: Span,
    eta_span: Span,
) -> tuple[float, int, int, str, str, str]:
    listing = candidate.listing
    price_cap = None if parsed.max_price_inr is None else parsed.max_price_inr * 100
    points = [
        factor_weights["rating"] * candidate.rating,
        factor_weights["price"]
        * capped_factor(listing.effective_price_paise, price_cap, price_span),
        factor_weights["eta"] * capped_factor(listing.eta_min_high, parsed.max_eta_min, eta_span),
    ]
    score = sum(points) + candidate.bonus
    eta = NO_ETA if listing.eta_min_high is None else listing.eta_min_high
    price = NO_PRICE if listing.effective_price_paise is None else listing.effective_price_paise
    return (
        -score,
        eta,
        price,
        listing.restaurant.lower(),
        listing.item.lower(),
        listing.provider,
    )


def fast_top(pool: list[Candidate], parsed: ParsedRequest, check: Check) -> Candidate | None:
    feasible = [item for item in pool if not item.blocked and not check(item.listing, parsed)]
    if not feasible:
        return None
    key = partial(
        candidate_key,
        parsed=parsed,
        factor_weights=weights(parsed),
        price_span=value_span([item.listing.effective_price_paise for item in feasible]),
        eta_span=value_span([item.listing.eta_min_high for item in feasible]),
    )
    return min(feasible, key=key)


def pick_label(item: str, restaurant: str, listing: Listing) -> str:
    price = listing.effective_price_paise
    price_text = "no price listed" if price is None else rupees(price)
    return f"{item} at {restaurant} ({listing.provider_label}, {price_text})"


def candidate_label(candidate: Candidate | None) -> str | None:
    if candidate is None:
        return None
    return pick_label(candidate.item, candidate.restaurant, candidate.listing)


def change_text(candidate: Candidate | None) -> str:
    label = candidate_label(candidate)
    return "nothing fits" if label is None else f"it changes to {label}"


def sweep(
    pool: list[Candidate],
    parsed: ParsedRequest,
    field: str,
    check: Check,
    start: float,
    values: Sequence[float],
    pick: str,
) -> Sweep:
    last = start
    for value in values:
        top = fast_top(pool, parsed.model_copy(update={field: value}), check)
        if top is None or top.listing.listing_id != pick:
            return Sweep(last, top, True)
        last = value
    return Sweep(last, None, False)


def budget_what_if(groups: list[OptionGroup], parsed: ParsedRequest, pick: str) -> WhatIf:
    budget = parsed.max_price_inr or 0
    pool = candidates(groups, parsed, "max_price_inr")
    check = budget_violations
    down = range(budget - 1, MIN_BUDGET_INR - 1, -1)
    up = range(budget + 1, 2 * budget + 1)
    below = sweep(pool, parsed, "max_price_inr", check, budget, down, pick)
    above = sweep(pool, parsed, "max_price_inr", check, budget, up, pick)
    low, high = rupees(round(below.last) * 100), rupees(round(above.last) * 100)
    text = f"The pick holds for any budget from {low} to {high}."
    if below.changed:
        text += f" Under {low}, {change_text(below.changed_to)}."
    if above.changed:
        text += f" From {rupees((round(above.last) + 1) * 100)}, {change_text(above.changed_to)}."
    return WhatIf(
        kind="budget",
        statement=text,
        threshold=below.last,
        new_pick=candidate_label(below.changed_to),
    )


def delivery_what_if(groups: list[OptionGroup], parsed: ParsedRequest, pick: str) -> WhatIf:
    limit = parsed.max_eta_min or 0
    pool = candidates(groups, parsed, "max_eta_min")
    check = delivery_violations
    down = range(limit - 1, MIN_ETA_MIN - 1, -1)
    up = range(limit + 1, 2 * limit + 1)
    below = sweep(pool, parsed, "max_eta_min", check, limit, down, pick)
    above = sweep(pool, parsed, "max_eta_min", check, limit, up, pick)
    text = f"The pick holds for any time limit from {below.last:g} to {above.last:g} minutes."
    if below.changed:
        text += f" Under {below.last:g} minutes, {change_text(below.changed_to)}."
    if above.changed:
        text += f" From {above.last + 1:g} minutes, {change_text(above.changed_to)}."
    return WhatIf(
        kind="delivery",
        statement=text,
        threshold=below.last,
        new_pick=candidate_label(below.changed_to),
    )


def rating_what_if(groups: list[OptionGroup], parsed: ParsedRequest, pick: str) -> WhatIf:
    minimum = parsed.min_rating or 0.0
    pool = candidates(groups, parsed, "min_rating")
    steps = [step / 10 for step in range(round(minimum * 10) + 1, MAX_RATING_TENTHS + 1)]
    above = sweep(pool, parsed, "min_rating", rating_violations, minimum, steps, pick)
    high = rating_value(above.last)
    text = f"The pick holds for any minimum rating up to {high}."
    if above.changed:
        text += f" Above {high}, {change_text(above.changed_to)}."
    return WhatIf(
        kind="min_rating",
        statement=text,
        threshold=above.last,
        new_pick=candidate_label(above.changed_to),
    )


def preference_what_if(
    groups: list[OptionGroup], parsed: ParsedRequest, pick: str, field: str, label: str
) -> WhatIf:
    ranked = rank(groups, parsed.model_copy(update={field: None})).ranked
    prefix = f"Without the “{label}” preference"
    if not ranked or ranked[0].best.listing.listing_id == pick:
        return WhatIf(kind="preference", statement=f"{prefix}, the pick stays the same.")
    top = ranked[0]
    new_pick = pick_label(top.item, top.restaurant, top.best.listing)
    return WhatIf(
        kind="preference",
        statement=f"{prefix}, the pick would be {new_pick}.",
        new_pick=new_pick,
    )


def what_ifs(
    groups: list[OptionGroup], parsed: ParsedRequest, pick: Listing | None
) -> list[WhatIf]:
    if pick is None:
        return []
    chosen = pick.listing_id
    results: list[WhatIf] = []
    if parsed.max_price_inr is not None:
        results.append(budget_what_if(groups, parsed, chosen))
    if parsed.max_eta_min is not None:
        results.append(delivery_what_if(groups, parsed, chosen))
    if parsed.min_rating is not None:
        results.append(rating_what_if(groups, parsed, chosen))
    results.extend(
        preference_what_if(groups, parsed, chosen, field, label)
        for field, label in PREFERENCES
        if getattr(parsed, field) is not None
    )
    return results
