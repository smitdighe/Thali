lazy from thali.models import Offer


def rupees(paise: int) -> str:
    whole, part = divmod(paise, 100)
    return f"₹{whole:,}" if part == 0 else f"₹{whole:,}.{part:02d}"


def eta_span(low: int | None, high: int) -> str:
    return str(high) if low is None or low == high else f"{low}–{high}"


def eta_text(low: int | None, high: int) -> str:
    return f"{eta_span(low, high)} min"


def eta_words(low: int | None, high: int) -> str:
    return f"{eta_span(low, high)} minutes"


def count_text(count: int) -> str:
    return f"{count:,}"


def rating_value(rating: float) -> str:
    return f"{rating:.1f}" if round(rating, 1) == rating else f"{rating:.2f}"


def title_case(text: str) -> str:
    return " ".join(word.capitalize() for word in text.split())


def offer_text(offer: Offer) -> str:
    if offer.kind == "percent" and offer.percent is not None:
        text = f"{offer.percent:g}% off"
        if offer.max_discount_paise is None:
            return text
        return f"{text} (max {rupees(offer.max_discount_paise)})"
    if offer.kind == "flat" and offer.amount_paise is not None:
        return f"{rupees(offer.amount_paise)} off"
    return offer.label
