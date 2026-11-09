import pytest

from thali.models import Listing, Offer
from thali.pipeline.normalize import (
    effective_price,
    missing_fields,
    money_to_paise,
    offer_from_promo,
    parse_count,
    parse_eta,
    parse_offer_text,
    rating_out_of_5,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (289.0, 28900),
        (289, 28900),
        ("₹ 175", 17500),
        ("240.00", 24000),
        ("Rs. 99", 9900),
        ("₹1,250", 125000),
        (0.125, 13),
        ("N/A", None),
        ("", None),
        (None, None),
        ("abc", None),
        (-5, None),
        ("-5", None),
        (True, None),
        (float("nan"), None),
        (float("inf"), None),
    ],
)
def test_money_to_paise(value, expected):
    assert money_to_paise(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (4.6, 4.6),
        ("9.2/10", 4.6),
        ("4.3", 4.3),
        (7, None),
        ("7", None),
        ("11/10", None),
        (-1, None),
        (True, None),
        ("n/a", None),
        (None, None),
    ],
)
def test_rating_out_of_5(value, expected):
    assert rating_out_of_5(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (950, 950),
        ("1.8k", 1800),
        ("2.3K", 2300),
        ("620", 620),
        ("1,200", 1200),
        (True, None),
        (-4, None),
        ("many", None),
        (None, None),
        ("", None),
    ],
)
def test_parse_count(value, expected):
    assert parse_count(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (24, (24, 24)),
        ("20-30 mins", (20, 30)),
        ("25–35 min", (25, 35)),
        ("40 mins", (40, 40)),
        ("35", (35, 35)),
        ("30-20 mins", (20, 30)),
        (0, (None, None)),
        (True, (None, None)),
        (None, (None, None)),
        ("soon", (None, None)),
    ],
)
def test_parse_eta(value, expected):
    assert parse_eta(value) == expected


def test_parse_offer_text_percent_with_cap():
    offer = parse_offer_text("10% OFF up to ₹40")
    assert offer == Offer(
        label="10% OFF up to ₹40", kind="percent", percent=10.0, max_discount_paise=4000
    )


def test_parse_offer_text_flat_with_minimum():
    offer = parse_offer_text("FLAT ₹30 OFF above ₹149")
    assert offer == Offer(
        label="FLAT ₹30 OFF above ₹149", kind="flat", amount_paise=3000, min_order_paise=14900
    )


def test_parse_offer_text_unknown_keeps_raw_label():
    assert parse_offer_text("Free garlic bread") == Offer(label="Free garlic bread", kind="unknown")


@pytest.mark.parametrize("value", [None, "", "   ", 5])
def test_parse_offer_text_empty(value):
    assert parse_offer_text(value) is None


def test_offer_from_promo_flat():
    offer = offer_from_promo({"kind": "FLAT", "valuePaise": 5000, "minOrderPaise": 24900})
    assert offer == Offer(
        label="₹50 off above ₹249", kind="flat", amount_paise=5000, min_order_paise=24900
    )


def test_offer_from_promo_flat_without_minimum():
    offer = offer_from_promo({"kind": "FLAT", "valuePaise": 3000})
    assert offer is not None
    assert offer.label == "₹30 off"
    assert offer.min_order_paise is None


def test_offer_from_promo_percent():
    offer = offer_from_promo({"kind": "PERCENT", "percent": 15, "maxDiscountPaise": 6000})
    assert offer == Offer(
        label="15% off up to ₹60", kind="percent", percent=15.0, max_discount_paise=6000
    )


def test_offer_from_promo_percent_without_cap():
    offer = offer_from_promo({"kind": "PERCENT", "percent": 10})
    assert offer is not None
    assert offer.label == "10% off"
    assert offer.max_discount_paise is None


def test_offer_from_promo_other_kind_is_unknown():
    assert offer_from_promo({"kind": "BOGO"}) == Offer(label="BOGO offer", kind="unknown")


def test_offer_from_promo_flat_without_value_is_unknown():
    offer = offer_from_promo({"kind": "FLAT"})
    assert offer == Offer(label="FLAT offer", kind="unknown")


@pytest.mark.parametrize("value", [None, "FLAT", []])
def test_offer_from_promo_none(value):
    assert offer_from_promo(value) is None


@pytest.mark.parametrize(
    ("price", "offer", "expected"),
    [
        (28500, Offer(label="x", kind="percent", percent=20, max_discount_paise=5000), 23500),
        (28900, Offer(label="x", kind="percent", percent=10, max_discount_paise=4000), 26010),
        (
            27900,
            Offer(label="x", kind="flat", amount_paise=5000, min_order_paise=24900),
            22900,
        ),
        (32000, Offer(label="x", kind="percent", percent=15, max_discount_paise=6000), 27200),
        (
            14900,
            Offer(label="x", kind="flat", amount_paise=3000, min_order_paise=14900),
            11900,
        ),
        (
            14800,
            Offer(label="x", kind="flat", amount_paise=3000, min_order_paise=14900),
            14800,
        ),
        (2000, Offer(label="x", kind="flat", amount_paise=5000), 0),
        (10000, Offer(label="x", kind="percent", percent=10), 9000),
        (10000, Offer(label="Free garlic bread", kind="unknown"), 10000),
        (10000, None, 10000),
        (None, Offer(label="x", kind="flat", amount_paise=5000), None),
    ],
)
def test_effective_price(price, offer, expected):
    assert effective_price(price, offer) == expected


def test_missing_fields_in_order():
    listing = Listing(
        listing_id="p:1",
        provider="p",
        provider_label="P",
        restaurant="R",
        item="I",
    )
    assert missing_fields(listing) == ["price", "rating", "eta", "diet", "area"]


def test_missing_fields_partial():
    listing = Listing(
        listing_id="p:1",
        provider="p",
        provider_label="P",
        restaurant="R",
        item="I",
        price_paise=1000,
        rating=4.0,
        eta_min_high=30,
        diet="veg",
        area="Powai",
    )
    assert missing_fields(listing) == []
    listing.rating = None
    listing.area = None
    assert missing_fields(listing) == ["rating", "area"]
