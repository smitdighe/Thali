import re
lazy import math
lazy from decimal import ROUND_HALF_UP, Decimal
lazy from typing import Any

lazy from thali.models import Listing, Offer

_MONEY_PREFIX = re.compile(r"^(?:₹|rs\.?|inr)\s*", re.IGNORECASE)
_NUMBER = re.compile(r"^\d+(?:\.\d+)?$")
_RATIO = re.compile(r"^(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)$")
_COUNT = re.compile(r"^(\d+(?:\.\d+)?)\s*([kK])?$")
_ETA_RANGE = re.compile(r"^\s*(\d+)\s*[-–—]\s*(\d+)\s*(?:min\w*)?\s*$", re.IGNORECASE)
_ETA_SINGLE = re.compile(r"^\s*(\d+)\s*(?:min\w*)?\s*$", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*%\s*off", re.IGNORECASE)
_FLAT = re.compile(r"flat\s*(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)\s*off", re.IGNORECASE)
_UP_TO = re.compile(r"up\s*to\s*(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_ABOVE = re.compile(r"above\s*(?:₹|rs\.?)?\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _is_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _to_decimal(value: Any) -> Decimal | None:
    if _is_number(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        return Decimal(str(value))
    if isinstance(value, str):
        text = _MONEY_PREFIX.sub("", value.strip()).replace(",", "").strip()
        if _NUMBER.match(text):
            return Decimal(text)
    return None


def _rupees_to_paise(amount: Decimal) -> int:
    return int((amount * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def money_to_paise(value: Any) -> int | None:
    amount = _to_decimal(value)
    if amount is None or amount < 0:
        return None
    return _rupees_to_paise(amount)


def rating_out_of_5(value: Any) -> float | None:
    if _is_number(value):
        number = Decimal(str(value))
        scale = Decimal(5)
    elif isinstance(value, str):
        text = value.strip()
        ratio = _RATIO.match(text)
        if ratio:
            number, scale = Decimal(ratio.group(1)), Decimal(ratio.group(2))
        elif _NUMBER.match(text):
            number, scale = Decimal(text), Decimal(5)
        else:
            return None
    else:
        return None
    if scale <= 0 or number < 0 or number > scale:
        return None
    return round(float(number / scale * 5), 2)


def parse_count(value: Any) -> int | None:
    if _is_number(value):
        if value < 0 or (isinstance(value, float) and not value.is_integer()):
            return None
        return int(value)
    if isinstance(value, str):
        match = _COUNT.match(value.strip().replace(",", ""))
        if match:
            number = Decimal(match.group(1))
            if match.group(2):
                number *= 1000
            return int(number.quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return None


def parse_eta(value: Any) -> tuple[int | None, int | None]:
    if _is_number(value):
        if value > 0 and (isinstance(value, int) or value.is_integer()):
            return int(value), int(value)
        return None, None
    if isinstance(value, str):
        ranged = _ETA_RANGE.match(value)
        if ranged:
            low, high = int(ranged.group(1)), int(ranged.group(2))
            if low > 0 and high > 0:
                return min(low, high), max(low, high)
            return None, None
        single = _ETA_SINGLE.match(value)
        if single and int(single.group(1)) > 0:
            minutes = int(single.group(1))
            return minutes, minutes
    return None, None


def _group_paise(pattern: re.Pattern[str], text: str) -> int | None:
    match = pattern.search(text)
    return _rupees_to_paise(Decimal(match.group(1))) if match else None


def parse_offer_text(text: Any) -> Offer | None:
    if not isinstance(text, str) or not text.strip():
        return None
    label = text.strip()
    percent = _PERCENT.search(label)
    if percent:
        return Offer(
            label=label,
            kind="percent",
            percent=float(percent.group(1)),
            max_discount_paise=_group_paise(_UP_TO, label),
            min_order_paise=_group_paise(_ABOVE, label),
        )
    flat = _group_paise(_FLAT, label)
    if flat is not None:
        return Offer(
            label=label,
            kind="flat",
            amount_paise=flat,
            min_order_paise=_group_paise(_ABOVE, label),
        )
    return Offer(label=label, kind="unknown")


def _is_paise(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _rupee_text(paise: int) -> str:
    rupees = Decimal(paise) / 100
    return f"₹{rupees:f}" if rupees != rupees.to_integral_value() else f"₹{int(rupees)}"


def _percent_text(percent: float) -> str:
    return f"{int(percent)}" if float(percent).is_integer() else f"{percent}"


def offer_from_promo(promo: Any) -> Offer | None:
    if not isinstance(promo, dict):
        return None
    kind = promo.get("kind")
    kind_text = kind.strip().upper() if isinstance(kind, str) else ""
    minimum = promo.get("minOrderPaise")
    min_order = minimum if _is_paise(minimum) else None
    above = f" above {_rupee_text(min_order)}" if min_order is not None else ""
    if kind_text == "FLAT" and _is_paise(promo.get("valuePaise")):
        value = promo["valuePaise"]
        return Offer(
            label=f"{_rupee_text(value)} off{above}",
            kind="flat",
            amount_paise=value,
            min_order_paise=min_order,
        )
    percent = promo.get("percent")
    if kind_text == "PERCENT" and _is_number(percent) and percent >= 0:
        cap = promo.get("maxDiscountPaise")
        max_discount = cap if _is_paise(cap) else None
        upto = f" up to {_rupee_text(max_discount)}" if max_discount is not None else ""
        return Offer(
            label=f"{_percent_text(percent)}% off{upto}",
            kind="percent",
            percent=float(percent),
            max_discount_paise=max_discount,
            min_order_paise=min_order,
        )
    return Offer(label=f"{kind_text or 'UNKNOWN'} offer", kind="unknown")


def effective_price(price: int | None, offer: Offer | None) -> int | None:
    if price is None:
        return None
    if offer is None or offer.kind == "unknown":
        return price
    if offer.min_order_paise is not None and price < offer.min_order_paise:
        return price
    if offer.kind == "percent" and offer.percent is not None:
        discount = int(price * offer.percent // 100)
        if offer.max_discount_paise is not None:
            discount = min(discount, offer.max_discount_paise)
    elif offer.kind == "flat" and offer.amount_paise is not None:
        discount = offer.amount_paise
    else:
        return price
    return max(0, price - discount)


def missing_fields(listing: Listing) -> list[str]:
    checks = (
        ("price", listing.price_paise),
        ("rating", listing.rating),
        ("eta", listing.eta_min_high),
        ("diet", listing.diet),
        ("area", listing.area),
    )
    return [name for name, value in checks if value is None]
