lazy from thali.models import (
    Factor,
    Listing,
    OptionResult,
    ParsedRequest,
    ProviderReport,
    RankOutcome,
    Recommendation,
    ScoredListing,
)
lazy from thali.pipeline.fmt import (
    count_text,
    eta_text,
    eta_words,
    offer_text,
    rating_value,
    rupees,
    title_case,
)
lazy from thali.pipeline.rank import is_discounted

DIET_CLAUSES = {
    "veg": "matches your vegetarian requirement",
    "vegan": "matches your vegan requirement",
    "egg": "matches your eggetarian requirement",
    "non_veg": "matches your non-veg request",
}
DIET_HEADINGS = {
    "veg": "Vegetarian",
    "vegan": "Vegan",
    "egg": "Eggetarian-friendly",
    "non_veg": "Non-veg",
}
DIET_MARKS = {"veg": "veg", "vegan": "vegan", "egg": "egg", "non_veg": "non-veg"}
PROVIDER_PROBLEMS = {
    "timeout": "timed out",
    "error": "returned an error",
    "malformed": "sent an unreadable response",
    "circuit_open": "was skipped after repeated failures",
}
COMPARED_FACTORS: tuple[Factor, ...] = ("rating", "price", "eta")
WEAK_FACTORS: tuple[Factor, ...] = ("rating", "eta")
LOW_RATING_COUNT = 50


def join_clauses(parts: list[str]) -> str:
    if len(parts) <= 2:
        return " and ".join(parts)
    return ", ".join(parts[:-1]) + ", and " + parts[-1]


def points(scored: ScoredListing) -> dict[Factor, float]:
    return {factor.factor: factor.points for factor in scored.factors}


def point_gaps(top: ScoredListing, other: ScoredListing) -> dict[Factor, float]:
    top_points, other_points = points(top), points(other)
    return {factor: top_points[factor] - other_points[factor] for factor in COMPARED_FACTORS}


def largest_gap(gaps: dict[Factor, float], candidates: tuple[Factor, ...]) -> Factor:
    return max(candidates, key=gaps.__getitem__)


def rating_phrase(listing: Listing) -> str:
    if listing.rating is None:
        return "no rating"
    return rating_value(listing.rating)


def price_phrase(listing: Listing) -> str:
    if listing.effective_price_paise is None:
        return "no price"
    return rupees(listing.effective_price_paise)


def eta_phrase(listing: Listing) -> str:
    if listing.eta_min_high is None:
        return "no delivery time"
    return eta_text(listing.eta_min_low, listing.eta_min_high)


def summary_text(listing: Listing, parsed: ParsedRequest) -> str:
    clauses: list[str] = []
    if parsed.diet is not None:
        clauses.append(DIET_CLAUSES[parsed.diet])
    if parsed.location is not None and listing.area is not None:
        clauses.append(f"is in {listing.area}")
    effective = listing.effective_price_paise
    if parsed.max_price_inr is not None and effective is not None:
        after = " after the offer" if is_discounted(listing) else ""
        budget = rupees(parsed.max_price_inr * 100)
        clauses.append(f"stays within your {budget} budget at {rupees(effective)}{after}")
    if listing.rating is not None:
        rating = rating_value(listing.rating)
        if listing.rating_count is None:
            clauses.append(f"has a {rating} rating")
        else:
            clauses.append(f"has a {rating} rating from {count_text(listing.rating_count)} ratings")
    if parsed.max_price_inr is None and effective is not None:
        clauses.append(f"costs {rupees(effective)}")
    if listing.eta_min_high is not None:
        eta = eta_words(listing.eta_min_low, listing.eta_min_high)
        clauses.append(f"has an estimated delivery time of {eta}")
    if not clauses:
        clauses.append("meets every requirement you stated")
    return f"Recommended because it {join_clauses(clauses)}."


def diet_reasons(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.diet is None or listing.diet is None:
        return []
    mark = f"marked {DIET_MARKS[listing.diet]} by {listing.provider_label}"
    return [f"{DIET_HEADINGS[parsed.diet]} ({mark})"]


def food_reasons(listing: Listing, parsed: ParsedRequest) -> list[str]:
    reasons: list[str] = []
    if parsed.dish is not None:
        reasons.append(f"{listing.item} matches “{parsed.dish}”")
    if parsed.cuisine is not None:
        reasons.append(f"Listed under {title_case(parsed.cuisine)}")
    reasons.extend(f"{listing.item} includes {ingredient}" for ingredient in parsed.ingredients)
    return reasons


def budget_reasons(listing: Listing, parsed: ParsedRequest) -> list[str]:
    effective = listing.effective_price_paise
    if parsed.max_price_inr is None or effective is None:
        return []
    within = f"within your {rupees(parsed.max_price_inr * 100)} budget"
    if is_discounted(listing) and listing.price_paise is not None and listing.offer is not None:
        offer = offer_text(listing.offer)
        return [f"{rupees(listing.price_paise)}, {rupees(effective)} after {offer} — {within}"]
    return [f"{rupees(effective)} — {within}"]


def delivery_reasons(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.max_eta_min is None or listing.eta_min_high is None:
        return []
    eta = eta_text(listing.eta_min_low, listing.eta_min_high)
    return [f"{eta} delivery — inside your {parsed.max_eta_min}-minute limit"]


def rating_reasons(listing: Listing, ranked: list[OptionResult]) -> list[str]:
    if listing.rating is None:
        return []
    text = f"Rated {rating_value(listing.rating)}"
    if listing.rating_count is not None:
        text = f"{text} from {count_text(listing.rating_count)} ratings"
    known = [
        option.best.listing.rating for option in ranked if option.best.listing.rating is not None
    ]
    if listing.rating >= max(known):
        text = f"{text} — the highest rating among options that fit"
    return [text]


def location_reasons(listing: Listing, parsed: ParsedRequest) -> list[str]:
    if parsed.location is None or listing.area is None:
        return []
    return [f"In {listing.area}, as requested"]


def reasons_for(
    best: ScoredListing, parsed: ParsedRequest, ranked: list[OptionResult]
) -> list[str]:
    listing = best.listing
    return [
        *diet_reasons(listing, parsed),
        *food_reasons(listing, parsed),
        *budget_reasons(listing, parsed),
        *delivery_reasons(listing, parsed),
        *rating_reasons(listing, ranked),
        *location_reasons(listing, parsed),
        *(f"Matches “{preference}”" for preference in best.matched_preferences),
    ]


def comparison_text(ranked: list[OptionResult]) -> str | None:
    if len(ranked) < 2:
        return None
    top, runner = ranked[0].best, ranked[1].best
    factor = largest_gap(point_gaps(top, runner), COMPARED_FACTORS)
    first, second = top.listing, runner.listing
    if factor == "rating":
        phrase = f"mainly on rating: {rating_phrase(first)} vs {rating_phrase(second)}"
    elif factor == "price":
        phrase = f"mainly on price: {price_phrase(first)} vs {price_phrase(second)}"
    else:
        phrase = f"mainly on delivery time: {eta_phrase(first)} vs {eta_phrase(second)}"
    label = f"{second.item} at {second.restaurant} ({second.provider_label})"
    return f"Ranked above {label} {phrase}."


def effective_price(scored: ScoredListing) -> int:
    price = scored.listing.effective_price_paise
    return 0 if price is None else price


def weakness_phrase(listing: Listing, factor: Factor) -> str:
    if factor == "eta":
        if listing.eta_min_high is None:
            return "has no delivery time listed"
        return f"takes {eta_text(listing.eta_min_low, listing.eta_min_high)}"
    if listing.rating is None:
        return "has no rating listed"
    if listing.rating_count is None:
        return f"is rated {rating_value(listing.rating)}"
    rating = rating_value(listing.rating)
    return f"is rated {rating} from {count_text(listing.rating_count)} ratings"


def cheaper_alternative_text(ranked: list[OptionResult]) -> str | None:
    top = ranked[0].best
    top_price = top.listing.effective_price_paise
    priced = [
        option.best
        for option in ranked[1:]
        if option.best.listing.effective_price_paise is not None
    ]
    if top_price is None or not priced:
        return None
    cheap = min(priced, key=effective_price)
    price = effective_price(cheap)
    if price >= top_price:
        return None
    factor = largest_gap(point_gaps(top, cheap), WEAK_FACTORS)
    listing = cheap.listing
    saving = rupees(top_price - price)
    return (
        f"{listing.item} at {listing.restaurant} is {saving} cheaper ({rupees(price)}) "
        f"but {weakness_phrase(listing, factor)}."
    )


def also_on_line(scored: ScoredListing) -> str:
    listing = scored.listing
    if not scored.feasible:
        return f"Also on {listing.provider_label}, but {scored.violations[0]}."
    text = f"Also on {listing.provider_label}"
    if listing.effective_price_paise is not None:
        text = f"{text} for {rupees(listing.effective_price_paise)}"
        if is_discounted(listing) and listing.offer is not None:
            text = f"{text} after {offer_text(listing.offer)}"
    if listing.eta_min_high is not None:
        text = f"{text}, {eta_text(listing.eta_min_low, listing.eta_min_high)}"
    return f"{text}."


def also_on_lines(option: OptionResult) -> list[str]:
    best_id = option.best.listing.listing_id
    return [
        also_on_line(scored) for scored in option.listings if scored.listing.listing_id != best_id
    ]


def matched_anywhere(ranked: list[OptionResult]) -> set[str]:
    return {
        preference
        for option in ranked
        for scored in option.listings
        if scored.feasible
        for preference in scored.matched_preferences
    }


def caveats_for(
    listing: Listing,
    parsed: ParsedRequest,
    ranked: list[OptionResult],
    reports: list[ProviderReport],
) -> list[str]:
    caveats: list[str] = []
    if listing.rating is None:
        caveats.append("No rating is listed for this item, so it was scored as average.")
    elif listing.rating_count is not None and listing.rating_count < LOW_RATING_COUNT:
        caveats.append(f"The rating comes from only {listing.rating_count} ratings.")
    caveats.extend(
        f"{report.label} wasn't compared ({PROVIDER_PROBLEMS[report.status]})."
        for report in reports
        if report.status != "ok"
    )
    matched = matched_anywhere(ranked)
    caveats.extend(
        f"Couldn't check “{preference}”: none of the sources describe it."
        for preference in parsed.other_preferences
        if preference not in matched
    )
    low, high = listing.eta_min_low, listing.eta_min_high
    if parsed.max_eta_min is not None and low is not None and high is not None and low != high:
        caveats.append(
            f"Delivery is quoted as {low}–{high} min; the upper end was checked against your limit."
        )
    return caveats


def explain(
    outcome: RankOutcome, parsed: ParsedRequest, reports: list[ProviderReport]
) -> Recommendation | None:
    if not outcome.ranked:
        return None
    top = outcome.ranked[0]
    return Recommendation(
        option=top,
        summary=summary_text(top.best.listing, parsed),
        reasons=reasons_for(top.best, parsed, outcome.ranked),
        comparison=comparison_text(outcome.ranked),
        cheaper_alternative=cheaper_alternative_text(outcome.ranked),
        also_on=also_on_lines(top),
        caveats=caveats_for(top.best.listing, parsed, outcome.ranked, reports),
    )


FACTOR_NAMES: dict[Factor, str] = {"rating": "rating", "price": "price", "eta": "delivery time"}


def own_rating(listing: Listing) -> str:
    if listing.rating is None:
        return "no rating listed"
    if listing.rating_count is None:
        return rating_value(listing.rating)
    return f"{rating_value(listing.rating)} from {count_text(listing.rating_count)} ratings"


def top_rating(listing: Listing) -> str:
    if listing.rating is None:
        return "no rating listed"
    if listing.rating_count is None:
        return rating_value(listing.rating)
    return f"{rating_value(listing.rating)} from {count_text(listing.rating_count)}"


def deficit_text(factor: Factor, other: Listing, top: Listing) -> str:
    if factor == "rating":
        return f"rating ({own_rating(other)} vs {top_rating(top)})"
    if factor == "price":
        return f"price ({price_phrase(other)} vs {price_phrase(top)})"
    return f"delivery time ({eta_phrase(other)} vs {eta_phrase(top)})"


def win_text(factor: Factor, other: Listing, top: Listing) -> str | None:
    if factor == "price":
        mine, theirs = other.effective_price_paise, top.effective_price_paise
        if mine is None or theirs is None or mine >= theirs:
            return None
        return f"It is {rupees(theirs - mine)} cheaper"
    if factor == "eta":
        mine_eta, theirs_eta = other.eta_min_high, top.eta_min_high
        if mine_eta is None or theirs_eta is None or mine_eta >= theirs_eta:
            return None
        return f"It arrives {theirs_eta - mine_eta} min sooner"
    if other.rating is None or top.rating is None or other.rating <= top.rating:
        return None
    return f"It is rated higher ({rating_value(other.rating)} vs {rating_value(top.rating)})"


def weight_of(scored: ScoredListing, factor: Factor) -> float:
    return next(item.weight for item in scored.factors if item.factor == factor)


def win_clause(top: ScoredListing, other: ScoredListing, gaps: dict[Factor, float]) -> str:
    wins = sorted((factor for factor in COMPARED_FACTORS if gaps[factor] < 0), key=gaps.__getitem__)
    for factor in wins:
        text = win_text(factor, other.listing, top.listing)
        if text is not None:
            share = round(weight_of(other, factor) * 100)
            return f" {text}, but {FACTOR_NAMES[factor]} carries {share}% of the score here."
    return ""


def feasible_why_not(top: ScoredListing, other: ScoredListing) -> str:
    gaps = point_gaps(top, other)
    scores = f"Scores {other.score:.4f} vs {top.score:.4f}"
    factor = largest_gap(gaps, COMPARED_FACTORS)
    if gaps[factor] <= 0:
        return f"{scores}.{win_clause(top, other, gaps)}"
    deficit = deficit_text(factor, other.listing, top.listing)
    return f"{scores}: mainly {deficit}.{win_clause(top, other, gaps)}"


def why_not_text(option: OptionResult, top: OptionResult | None) -> str:
    if not option.feasible or top is None:
        return f"Filtered out: {'; '.join(option.best.violations)}."
    return feasible_why_not(top.best, option.best)


def with_why_not(outcome: RankOutcome) -> RankOutcome:
    top = outcome.ranked[0] if outcome.ranked else None

    def annotate(option: OptionResult) -> OptionResult:
        return option.model_copy(update={"why_not": why_not_text(option, top)})

    return RankOutcome(
        ranked=[*outcome.ranked[:1], *map(annotate, outcome.ranked[1:])],
        excluded=list(map(annotate, outcome.excluded)),
        closest=list(map(annotate, outcome.closest)),
    )
