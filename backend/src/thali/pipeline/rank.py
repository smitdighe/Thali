lazy from thali.models import (
    Factor,
    FactorScore,
    Listing,
    OptionGroup,
    OptionResult,
    ParsedRequest,
    RankOutcome,
    ScoredListing,
)
lazy from thali.pipeline.fmt import rating_value, rupees
lazy from thali.text import contains_phrase, name_tokens

BASE_WEIGHTS: dict[Factor, float] = {"rating": 0.4, "price": 0.3, "eta": 0.3}
PRIOR_COUNT = 100
PRIOR_MEAN = 4.0
UNKNOWN_RATING_COUNT = 25
BONUS_STEP = 0.03
BONUS_CAP = 0.06
NO_ETA = 10**6
NO_PRICE = 10**9
CLOSEST_LIMIT = 3
DIGITS = 4

DIET_RULES: dict[str, tuple[frozenset[str], str, str]] = {
    "veg": (frozenset({"veg", "vegan"}), "not vegetarian", "vegetarian status not listed by {}"),
    "vegan": (frozenset({"vegan"}), "not vegan", "vegan status not listed by {}"),
    "egg": (frozenset({"veg", "vegan", "egg"}), "not eggetarian", "diet not listed by {}"),
    "non_veg": (frozenset({"non_veg"}), "not non-veg", "diet not listed by {}"),
}

Span = tuple[int, int] | None


def clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def is_discounted(listing: Listing) -> bool:
    price, effective = listing.price_paise, listing.effective_price_paise
    return price is not None and effective is not None and effective < price


def dish_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.dish is None:
        return []
    if contains_phrase(name_tokens(listing.item), name_tokens(parsed.dish)):
        return []
    return [f"not a {parsed.dish}"]


def ingredient_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    item_tokens = set(name_tokens(listing.item))
    return [
        f"doesn't mention {ingredient}"
        for ingredient in parsed.ingredients
        if not set(name_tokens(ingredient)) <= item_tokens
    ]


def cuisine_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.cuisine is None:
        return []
    wanted = name_tokens(parsed.cuisine)
    sources = [*listing.cuisines, *listing.tags, listing.item]
    if any(contains_phrase(name_tokens(source), wanted) for source in sources):
        return []
    return [f"not {parsed.cuisine}"]


def diet_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.diet is None:
        return []
    allowed, mismatch, unknown = DIET_RULES[parsed.diet]
    if listing.diet is None:
        return [unknown.format(listing.provider_label)]
    return [] if listing.diet in allowed else [mismatch]


def budget_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.max_price_inr is None:
        return []
    effective = listing.effective_price_paise
    if effective is None:
        return [f"price not listed by {listing.provider_label}"]
    budget = parsed.max_price_inr * 100
    if effective <= budget:
        return []
    after = " after offer" if is_discounted(listing) else ""
    return [f"{rupees(effective)}{after} is over your {rupees(budget)} budget"]


def delivery_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    limit = parsed.max_eta_min
    if limit is None:
        return []
    low, high = listing.eta_min_low, listing.eta_min_high
    if high is None:
        return [f"delivery time not listed by {listing.provider_label}"]
    if high <= limit:
        return []
    if low is None or low == high:
        return [f"{high} min is over your {limit}-minute limit"]
    return [f"{low}–{high} min can exceed your {limit}-minute limit"]


def rating_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    minimum = parsed.min_rating
    if minimum is None:
        return []
    if listing.rating is None:
        return [f"rating not listed by {listing.provider_label}"]
    if listing.rating >= minimum:
        return []
    return [f"rated {rating_value(listing.rating)} — below your minimum {rating_value(minimum)}"]


def location_violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.location is None:
        return []
    if listing.area is None:
        return [f"area not listed by {listing.provider_label}"]
    if listing.area == parsed.location:
        return []
    return [f"in {listing.area}, not {parsed.location}"]


CHECKS = (
    dish_violations,
    ingredient_violations,
    cuisine_violations,
    diet_violations,
    budget_violations,
    delivery_violations,
    rating_violations,
    location_violations,
)


def violations(listing: Listing, parsed: ParsedRequest) -> list[str]:
    return [problem for check in CHECKS for problem in check(listing, parsed)]


def weights(parsed: ParsedRequest) -> dict[Factor, float]:
    raw = dict(BASE_WEIGHTS)
    if parsed.rating_preference is not None:
        raw["rating"] *= 2
    if parsed.price_preference is not None:
        raw["price"] *= 2
    if parsed.speed_preference is not None:
        raw["eta"] *= 2
    total = sum(raw.values())
    return {factor: weight / total for factor, weight in raw.items()}


def rating_factor(listing: Listing) -> float:
    if listing.rating is None:
        return 0.5
    votes = listing.rating_count if listing.rating_count is not None else UNKNOWN_RATING_COUNT
    # Bayesian average: pull the rating toward PRIOR_MEAN with the weight of PRIOR_COUNT ratings.
    adjusted = (votes * listing.rating + PRIOR_COUNT * PRIOR_MEAN) / (votes + PRIOR_COUNT)
    return clamp((adjusted - 3.0) / 2.0)


def capped_factor(value: int | None, cap: int | None, span: Span) -> float:
    if cap is not None:
        return 0.0 if value is None else clamp(1 - value / cap)
    if value is None or span is None:
        return 0.5
    low, high = span
    return clamp((high - value) / (high - low))


def value_span(values: list[int | None]) -> Span:
    distinct = {value for value in values if value is not None}
    return (min(distinct), max(distinct)) if len(distinct) >= 2 else None


def preference_matches(listing: Listing, parsed: ParsedRequest) -> list[str]:
    pool = set(name_tokens(listing.item))
    for tag in listing.tags:
        pool.update(name_tokens(tag))
    return [
        preference
        for preference in parsed.other_preferences
        if name_tokens(preference) and set(name_tokens(preference)) <= pool
    ]


def score_listing(
    listing: Listing,
    problems: list[str],
    parsed: ParsedRequest,
    price_span: Span,
    eta_span: Span,
) -> ScoredListing:
    factor_weights = weights(parsed)
    price_cap = None if parsed.max_price_inr is None else parsed.max_price_inr * 100
    values: dict[Factor, float] = {
        "rating": rating_factor(listing),
        "price": capped_factor(listing.effective_price_paise, price_cap, price_span),
        "eta": capped_factor(listing.eta_min_high, parsed.max_eta_min, eta_span),
    }
    factors = [
        FactorScore(
            factor=factor,
            value=value,
            weight=factor_weights[factor],
            points=factor_weights[factor] * value,
        )
        for factor, value in values.items()
    ]
    matched = preference_matches(listing, parsed)
    bonus = min(BONUS_STEP * len(matched), BONUS_CAP)
    return ScoredListing(
        listing=listing,
        feasible=not problems,
        violations=problems,
        score=sum(factor.points for factor in factors) + bonus,
        factors=factors,
        bonus=bonus,
        matched_preferences=matched,
    )


def listing_key(scored: ScoredListing) -> tuple[float, int, int, str, str, str]:
    listing = scored.listing
    eta = NO_ETA if listing.eta_min_high is None else listing.eta_min_high
    price = NO_PRICE if listing.effective_price_paise is None else listing.effective_price_paise
    return (
        -scored.score,
        eta,
        price,
        listing.restaurant.lower(),
        listing.item.lower(),
        listing.provider,
    )


def closeness_key(scored: ScoredListing) -> tuple[int, tuple[float, int, int, str, str, str]]:
    return (len(scored.violations), listing_key(scored))


def option_key(option: OptionResult) -> tuple[float, int, int, str, str, str]:
    return listing_key(option.best)


def excluded_key(option: OptionResult) -> tuple[int, float, str, str]:
    return (len(option.best.violations), -option.best.score, option.restaurant, option.option_id)


def build_option(group: OptionGroup, scored: list[ScoredListing]) -> OptionResult:
    feasible = sorted((item for item in scored if item.feasible), key=listing_key)
    infeasible = sorted((item for item in scored if not item.feasible), key=closeness_key)
    best = feasible[0] if feasible else infeasible[0]
    return OptionResult(
        option_id=group.option_id,
        restaurant=group.restaurant,
        area=group.area,
        item=group.item,
        feasible=bool(feasible),
        score=best.score,
        best=best,
        listings=[*feasible, *infeasible],
    )


def rounded_listing(scored: ScoredListing) -> ScoredListing:
    factors = [
        factor.model_copy(
            update={
                "value": round(factor.value, DIGITS),
                "weight": round(factor.weight, DIGITS),
                "points": round(factor.points, DIGITS),
            }
        )
        for factor in scored.factors
    ]
    return scored.model_copy(
        update={
            "score": round(scored.score, DIGITS),
            "bonus": round(scored.bonus, DIGITS),
            "factors": factors,
        }
    )


def rounded_option(option: OptionResult, position: int | None) -> OptionResult:
    best = rounded_listing(option.best)
    return option.model_copy(
        update={
            "rank": position,
            "score": best.score,
            "best": best,
            "listings": [rounded_listing(scored) for scored in option.listings],
        }
    )


def rank(groups: list[OptionGroup], parsed: ParsedRequest) -> RankOutcome:
    listings = [listing for group in groups for listing in group.listings]
    problems = {listing.listing_id: violations(listing, parsed) for listing in listings}
    feasible = [listing for listing in listings if not problems[listing.listing_id]]
    basis = feasible or listings
    price_span = value_span([listing.effective_price_paise for listing in basis])
    eta_span = value_span([listing.eta_min_high for listing in basis])
    options = [
        build_option(
            group,
            [
                score_listing(listing, problems[listing.listing_id], parsed, price_span, eta_span)
                for listing in group.listings
            ],
        )
        for group in groups
    ]
    ranked = sorted((option for option in options if option.feasible), key=option_key)
    excluded = sorted((option for option in options if not option.feasible), key=excluded_key)
    ranked_out = [rounded_option(option, position) for position, option in enumerate(ranked, 1)]
    excluded_out = [rounded_option(option, None) for option in excluded]
    return RankOutcome(
        ranked=ranked_out,
        excluded=excluded_out,
        closest=[] if ranked_out else excluded_out[:CLOSEST_LIMIT],
    )
