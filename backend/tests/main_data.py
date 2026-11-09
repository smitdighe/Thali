lazy from thali.models import Listing, Offer, OptionGroup, ParsedRequest

LABELS = {"bitebox": "Bitebox", "tiffinly": "Tiffinly", "khaana": "Khaana Open Data"}


def offer_percent(label: str, percent: float, cap: int) -> Offer:
    return Offer(label=label, kind="percent", percent=percent, max_discount_paise=cap)


def offer_flat(label: str, amount: int, minimum: int) -> Offer:
    return Offer(label=label, kind="flat", amount_paise=amount, min_order_paise=minimum)


def make_listing(
    ref: str,
    restaurant: str,
    area: str | None,
    item: str,
    diet: str | None,
    price: int | None,
    rating: float | None,
    count: int | None,
    eta: tuple[int, int] | None,
    offer: Offer | None = None,
    effective: int | None = None,
    tags: tuple[str, ...] = (),
) -> Listing:
    provider = ref.split(":")[0]
    low, high = eta if eta is not None else (None, None)
    values = {"price": price, "rating": rating, "eta": high, "diet": diet, "area": area}
    return Listing(
        listing_id=ref,
        provider=provider,
        provider_label=LABELS[provider],
        restaurant=restaurant,
        area=area,
        item=item,
        tags=list(tags),
        diet=diet,
        price_paise=price,
        offer=offer,
        effective_price_paise=price if effective is None else effective,
        rating=rating,
        rating_count=count,
        eta_min_low=low,
        eta_min_high=high,
        missing_fields=[name for name, value in values.items() if value is None],
    )


def make_group(option_id: str, listings: list[Listing]) -> OptionGroup:
    first = listings[0]
    return OptionGroup(
        option_id=option_id,
        restaurant=first.restaurant,
        area=first.area,
        item=first.item,
        listings=listings,
    )


def main_parsed() -> ParsedRequest:
    return ParsedRequest(
        intent="discovery",
        dish="biryani",
        diet="veg",
        max_price_inr=300,
        max_eta_min=30,
        rating_preference="high",
        missing=["location"],
    )


def bitebox(
    ref: str,
    restaurant: str,
    area: str,
    item: str,
    diet: str,
    price: int | None,
    rating: float | None,
    count: int | None,
    eta: int | None,
    partial: bool,
    offer: Offer | None = None,
    effective: int | None = None,
) -> Listing:
    if partial:
        rating, count, eta = None, None, None
    return make_listing(
        f"bitebox:{ref}",
        restaurant,
        area,
        item,
        diet,
        price,
        rating,
        count,
        None if eta is None else (eta, eta),
        offer,
        effective,
    )


def main_groups(bitebox_partial: bool = False) -> list[OptionGroup]:
    partial = bitebox_partial
    pct10 = offer_percent("10% OFF up to ₹40", 10.0, 4000)
    pct20 = offer_percent("20% OFF up to ₹50", 20.0, 5000)
    pct15 = offer_percent("15% off up to ₹60", 15.0, 6000)
    flat50 = offer_flat("₹50 off above ₹249", 5000, 24900)
    dp, aw = "Dum Pukht House", "Andheri West"
    return [
        make_group(
            "dum pukht house|andheri west|biryani dum veg",
            [
                bitebox(
                    "bb_101",
                    dp,
                    aw,
                    "Veg Dum Biryani",
                    "veg",
                    28900,
                    4.6,
                    2140,
                    24,
                    partial,
                    pct10,
                    26010,
                ),
                make_listing(
                    "tiffinly:T-88-4",
                    dp,
                    aw,
                    "Veg Dum Biryani (Serves 1)",
                    "veg",
                    27900,
                    4.6,
                    1800,
                    (20, 30),
                    flat50,
                    22900,
                    ("veg", "bestseller"),
                ),
            ],
        ),
        make_group(
            "dum pukht house|andheri west|biryani chicken dum",
            [
                bitebox(
                    "bb_102",
                    dp,
                    aw,
                    "Chicken Dum Biryani",
                    "non_veg",
                    34900,
                    4.6,
                    2140,
                    26,
                    partial,
                ),
                make_listing(
                    "tiffinly:T-88-7",
                    dp,
                    aw,
                    "Chicken Dum Biryani (Serves 1)",
                    "non_veg",
                    33900,
                    4.6,
                    1800,
                    (20, 30),
                    tags=("non_veg",),
                ),
            ],
        ),
        make_group(
            "biryani junction|powai|biryani veg",
            [
                bitebox(
                    "bb_103",
                    "Biryani Junction",
                    "Powai",
                    "Veg Biryani",
                    "veg",
                    18000,
                    3.4,
                    410,
                    28,
                    partial,
                ),
                make_listing(
                    "khaana:A-1",
                    "Biryani Junction",
                    "Powai",
                    "Veg Biryani",
                    "veg",
                    17500,
                    3.5,
                    380,
                    None,
                ),
            ],
        ),
        make_group(
            "lucknowi degh|bandra west|biryani dum subz",
            [
                bitebox(
                    "bb_105",
                    "Lucknowi Degh",
                    "Bandra West",
                    "Subz Dum Biryani",
                    "veg",
                    28500,
                    4.8,
                    950,
                    22,
                    partial,
                    pct20,
                    23500,
                ),
                make_listing(
                    "tiffinly:T-12-1",
                    "Lucknowi Degh",
                    "Bandra West",
                    "Subz Dum Biryani",
                    "veg",
                    32000,
                    4.7,
                    620,
                    (25, 35),
                    pct15,
                    27200,
                    ("veg",),
                ),
            ],
        ),
        make_group(
            "spice route kitchen|andheri west|biryani paneer",
            [
                bitebox(
                    "bb_106",
                    "Spice Route Kitchen",
                    aw,
                    "Paneer Biryani",
                    "veg",
                    26000,
                    None,
                    None,
                    25,
                    partial,
                )
            ],
        ),
        make_group(
            "hyderabad house|andheri west|biryani veg",
            [
                bitebox(
                    "bb_107",
                    "Hyderabad House",
                    aw,
                    "Veg Biryani",
                    "veg",
                    24000,
                    4.1,
                    300,
                    None,
                    partial,
                )
            ],
        ),
        make_group(
            "hyderabad house|dadar|biryani veg",
            [
                bitebox(
                    "bb_108",
                    "Hyderabad House",
                    "Dadar",
                    "Veg Biryani",
                    "veg",
                    24000,
                    4.0,
                    520,
                    31,
                    partial,
                )
            ],
        ),
        make_group(
            "green leaf cafe|lower parel|biryani veg",
            [
                bitebox(
                    "bb_109",
                    "Green Leaf Cafe",
                    "Lower Parel",
                    "Veg Biryani",
                    "veg",
                    None,
                    4.2,
                    150,
                    20,
                    partial,
                )
            ],
        ),
        make_group(
            "tandoor tales|powai|biryani bowl veg",
            [
                make_listing(
                    "tiffinly:T-40-2",
                    "Tandoor Tales",
                    "Powai",
                    "Veg Biryani Bowl",
                    "veg",
                    21000,
                    4.1,
                    2300,
                    (15, 25),
                    tags=("veg",),
                )
            ],
        ),
        make_group(
            "mirchi mahal|dadar|biryani hyderabadi veg",
            [
                make_listing(
                    "tiffinly:T-55-1",
                    "Mirchi Mahal",
                    "Dadar",
                    "Veg Hyderabadi Biryani",
                    "veg",
                    25000,
                    None,
                    None,
                    None,
                    tags=("veg",),
                )
            ],
        ),
        make_group(
            "annapurna bhojanalay|dadar|gujarati thali",
            [
                make_listing(
                    "khaana:A-2",
                    "Annapurna Bhojanalay",
                    "Dadar",
                    "Gujarati Thali",
                    "veg",
                    28000,
                    4.5,
                    1200,
                    None,
                )
            ],
        ),
        make_group(
            "udupi corner|dadar|dosa masala",
            [
                make_listing(
                    "khaana:A-3",
                    "Udupi Corner",
                    "Dadar",
                    "Masala Dosa",
                    "veg",
                    12000,
                    4.3,
                    2100,
                    None,
                )
            ],
        ),
        make_group(
            "udupi corner|dadar|dosa masala mysore",
            [
                make_listing(
                    "khaana:A-4",
                    "Udupi Corner",
                    "Dadar",
                    "Mysore Masala Dosa",
                    None,
                    14000,
                    4.3,
                    2100,
                    None,
                )
            ],
        ),
        make_group(
            "bombay tiffin co|bandra west|biryani large veg",
            [
                make_listing(
                    "khaana:A-5",
                    "Bombay Tiffin Co",
                    "Bandra West",
                    "Veg Biryani, Large",
                    "veg",
                    None,
                    4.0,
                    90,
                    None,
                )
            ],
        ),
        make_group(
            "biryani darbar|andheri west|biryani hyderabadi veg",
            [
                make_listing(
                    "khaana:A-7",
                    "Biryani Darbar",
                    aw,
                    "Hyderabadi Veg Biriyani",
                    "veg",
                    23000,
                    4.4,
                    640,
                    None,
                )
            ],
        ),
        make_group(
            "salad studio|bandra west|quinoa salad vegan",
            [
                make_listing(
                    "khaana:A-8",
                    "Salad Studio",
                    "Bandra West",
                    "Vegan Quinoa Salad",
                    "vegan",
                    29900,
                    4.2,
                    180,
                    None,
                )
            ],
        ),
    ]
