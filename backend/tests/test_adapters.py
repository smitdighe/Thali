import json

import httpx
import pytest

from thali.models import ProviderSearch
from thali.providers.base import MalformedPayload
from thali.providers.bitebox import BiteboxAdapter
from thali.providers.khaana import COLUMNS, KhaanaAdapter
from thali.providers.tiffinly import TiffinlyAdapter

BITEBOX_RESULTS = [
    {
        "id": "bb_101",
        "restaurant": {"id": "rb_1", "name": "Dum Pukht House", "area": "Andheri West"},
        "dish": "Veg Dum Biryani",
        "price": 289.0,
        "rating": 4.6,
        "ratings_count": 2140,
        "eta_minutes": 24,
        "is_veg": True,
        "cuisine": ["Hyderabadi", "Biryani"],
        "offer": "10% OFF up to ₹40",
    },
    {
        "id": "bb_102",
        "restaurant": {"id": "rb_1", "name": "Dum Pukht House", "area": "Andheri West"},
        "dish": "Chicken Dum Biryani",
        "price": 349.0,
        "rating": 4.6,
        "ratings_count": 2140,
        "eta_minutes": 26,
        "is_veg": False,
        "cuisine": ["Hyderabadi", "Biryani"],
        "offer": None,
    },
    {
        "id": "bb_106",
        "restaurant": {"id": "rb_4", "name": "Spice Route Kitchen", "area": "Andheri West"},
        "dish": "Paneer Biryani",
        "price": 260.0,
        "rating": None,
        "ratings_count": None,
        "eta_minutes": 25,
        "is_veg": True,
        "cuisine": ["North Indian", "Biryani"],
        "offer": None,
    },
    {
        "id": "bb_109",
        "restaurant": {"id": "rb_7", "name": "Green Leaf Cafe", "area": "Lower Parel"},
        "dish": "Veg Biryani",
        "price": None,
        "rating": 4.2,
        "ratings_count": 150,
        "eta_minutes": 20,
        "is_veg": True,
        "cuisine": ["Biryani"],
        "offer": None,
    },
    {
        "id": "bb_206",
        "restaurant": {"id": "rb_7", "name": "Green Leaf Cafe", "area": "Lower Parel"},
        "dish": "Buddha Bowl",
        "price": 329.0,
        "rating": 4.4,
        "ratings_count": 410,
        "eta_minutes": 28,
        "is_veg": True,
        "is_vegan": True,
        "cuisine": ["Healthy", "Salads"],
        "offer": None,
    },
    {
        "id": "bb_204",
        "restaurant": {"id": "rb_11", "name": "Forno Bandra", "area": "Bandra West"},
        "dish": "Margherita Pizza",
        "price": "349",
        "rating": 4.5,
        "ratings_count": 2600,
        "eta_minutes": 30,
        "cuisine": ["Italian"],
        "offer": "Free garlic bread",
    },
]

TIFFINLY_PAYLOAD = {
    "meta": {"schema": "tiffinly.v3", "generated_at": "2026-11-09T10:00:00Z"},
    "data": {
        "outlets": [
            {
                "outletId": "T-88",
                "outletName": "Dum Pukht House",
                "locality": "Andheri (W)",
                "score": "9.2/10",
                "votes": "1.8k",
                "deliveryTime": "20-30 mins",
                "menu": [
                    {
                        "sku": "T-88-4",
                        "title": "Veg Dum Biryani (Serves 1)",
                        "pricePaise": 27900,
                        "tags": ["VEG", "BESTSELLER"],
                        "promo": {"kind": "FLAT", "valuePaise": 5000, "minOrderPaise": 24900},
                    },
                    {
                        "sku": "T-88-7",
                        "title": "Chicken Dum Biryani (Serves 1)",
                        "pricePaise": 33900,
                        "tags": ["NON_VEG"],
                        "promo": None,
                    },
                ],
            },
            {
                "outletId": "T-55",
                "outletName": "Mirchi Mahal",
                "locality": "Dadar",
                "score": None,
                "votes": None,
                "deliveryTime": None,
                "menu": [
                    {
                        "sku": "T-55-2",
                        "title": "Veg Pulao",
                        "pricePaise": "abc",
                        "tags": ["VEG"],
                        "promo": None,
                    },
                    {"sku": "T-55-3", "title": "", "pricePaise": 15000, "tags": [], "promo": None},
                ],
            },
            {
                "outletId": "T-70",
                "outletName": "Thali Ghar",
                "locality": "Dadar",
                "score": "8.8/10",
                "votes": "980",
                "deliveryTime": "30-40 mins",
                "menu": [
                    {
                        "sku": "T-70-2",
                        "title": "Gujarati Thali",
                        "pricePaise": 30000,
                        "tags": ["VEG"],
                        "promo": {"kind": "BOGO"},
                    },
                    {
                        "sku": "T-70-3",
                        "title": "Vegan Bowl",
                        "pricePaise": 28000,
                        "tags": ["Veg", "Vegan"],
                        "promo": None,
                    },
                    {
                        "sku": "T-70-4",
                        "title": "Egg Roll",
                        "pricePaise": 9000,
                        "tags": ["Egg"],
                        "promo": None,
                    },
                    {
                        "sku": "T-70-5",
                        "title": "Plain Rice",
                        "pricePaise": 9000,
                        "tags": ["JAIN"],
                        "promo": None,
                    },
                ],
            },
        ]
    },
}

KHAANA_ROWS = [
    "A-1,Biryani Junction,Powai,Veg Biryani,Y,₹ 175,3.5,380,Biryani|Mughlai",
    'A-5,Bombay Tiffin Co,Bandra West,"Veg Biryani, Large",Y,N/A,4.0,90,Biryani',
    "A-6,Chaat Corner,Dadar,Pani Puri,Y,60,4.1,300,Street Food,extra,column",
    "A-4,Udupi Corner,Dadar,Mysore Masala Dosa,,140,4.3,2100,South Indian",
    "A-8,Salad Studio,Bandra West,Vegan Quinoa Salad,VG,299,4.2,180,Healthy|Salads",
    "A-9,Egg Hut,Dadar,Egg Bhurji,E,90,4.0,50,",
    "A-10,Kebab Hut,Dadar,Seekh Kebab,N,220,4.0,70,Mughlai",
]


def khaana_csv(rows: list[str], header: list[str] | None = None) -> str:
    return "\n".join([",".join(header or COLUMNS), *rows]) + "\n"


def json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def bitebox_response(results: list[dict], version: str = "2.1") -> httpx.Response:
    return json_response({"api_version": version, "results": results})


def by_id(batch):
    return {listing.listing_id: listing for listing in batch.listings}


def test_bitebox_listings():
    batch = BiteboxAdapter().normalize(bitebox_response(BITEBOX_RESULTS))
    listings = by_id(batch)
    assert batch.schema_seen == "bitebox 2.1"
    assert batch.records_received == 6
    assert batch.dropped == []

    dum = listings["bitebox:bb_101"]
    assert dum.provider == "bitebox"
    assert dum.provider_label == "Bitebox"
    assert dum.restaurant == "Dum Pukht House"
    assert dum.area == "Andheri West"
    assert dum.price_paise == 28900
    assert dum.effective_price_paise == 26010
    assert dum.offer is not None and dum.offer.kind == "percent"
    assert dum.rating == 4.6 and dum.rating_count == 2140
    assert (dum.eta_min_low, dum.eta_min_high) == (24, 24)
    assert dum.cuisines == ["Hyderabadi", "Biryani"]
    assert dum.tags == []
    assert dum.missing_fields == []


def test_bitebox_diet_mapping():
    listings = by_id(BiteboxAdapter().normalize(bitebox_response(BITEBOX_RESULTS)))
    assert listings["bitebox:bb_101"].diet == "veg"
    assert listings["bitebox:bb_102"].diet == "non_veg"
    assert listings["bitebox:bb_206"].diet == "vegan"
    assert listings["bitebox:bb_204"].diet is None
    assert "diet" in listings["bitebox:bb_204"].missing_fields


def test_bitebox_missing_fields_and_offers():
    listings = by_id(BiteboxAdapter().normalize(bitebox_response(BITEBOX_RESULTS)))
    assert listings["bitebox:bb_106"].rating is None
    assert listings["bitebox:bb_106"].rating_count is None
    assert listings["bitebox:bb_106"].missing_fields == ["rating"]
    assert listings["bitebox:bb_109"].price_paise is None
    assert listings["bitebox:bb_109"].effective_price_paise is None
    assert listings["bitebox:bb_109"].missing_fields == ["price"]
    pizza = listings["bitebox:bb_204"]
    assert pizza.price_paise == 34900
    assert pizza.offer is not None and pizza.offer.kind == "unknown"
    assert pizza.effective_price_paise == 34900


def test_bitebox_partial_payload_marks_fields_missing():
    stripped = [
        {k: v for k, v in r.items() if k not in {"rating", "ratings_count", "eta_minutes"}}
        for r in BITEBOX_RESULTS
    ]
    batch = BiteboxAdapter().normalize(bitebox_response(stripped))
    assert len(batch.listings) == len(stripped)
    for listing in batch.listings:
        assert "rating" in listing.missing_fields
        assert "eta" in listing.missing_fields


def test_bitebox_drops_bad_records():
    results = [
        "not an object",
        {"id": "bb_1", "restaurant": {"area": "Powai"}, "dish": "Veg Biryani", "price": 100},
        {"id": "bb_2", "restaurant": {"name": "Cafe"}, "dish": "  ", "price": 100},
        {"restaurant": {"name": "Cafe"}, "dish": "Veg Biryani", "price": 100},
        {"id": "bb_5", "restaurant": {"name": "Cafe"}, "dish": "Veg Biryani", "price": 100},
    ]
    batch = BiteboxAdapter().normalize(bitebox_response(results))
    assert [lst.listing_id for lst in batch.listings] == ["bitebox:bb_5"]
    assert [(d.record_ref, d.reason) for d in batch.dropped] == [
        (None, "record is not an object"),
        ("bb_1", "missing restaurant name"),
        ("bb_2", "missing item name"),
        (None, "missing id"),
    ]
    assert all(d.provider == "bitebox" for d in batch.dropped)
    assert batch.records_received == 5


def test_bitebox_invalid_price_becomes_null_and_flagged():
    results = [
        {
            "id": "bb_9",
            "restaurant": {"name": "Cafe", "area": "Powai"},
            "dish": "Dosa",
            "price": "N/A",
        }
    ]
    listing = BiteboxAdapter().normalize(bitebox_response(results)).listings[0]
    assert listing.price_paise is None
    assert "price" in listing.missing_fields


@pytest.mark.parametrize("version", ["3.0", "1.9", ""])
def test_bitebox_unsupported_version(version):
    with pytest.raises(MalformedPayload, match="unsupported api_version"):
        BiteboxAdapter().normalize(bitebox_response([], version=version))


def test_bitebox_missing_version_and_non_dict_payload():
    with pytest.raises(MalformedPayload, match="unsupported api_version None"):
        BiteboxAdapter().normalize(json_response({"results": []}))
    with pytest.raises(MalformedPayload):
        BiteboxAdapter().normalize(json_response([1, 2]))


def test_bitebox_missing_results_list():
    with pytest.raises(MalformedPayload, match="missing results list"):
        BiteboxAdapter().normalize(json_response({"api_version": "2.1", "results": "nope"}))


def test_bitebox_truncated_json_is_malformed():
    body = json.dumps({"api_version": "2.1", "results": BITEBOX_RESULTS})[:120]
    response = httpx.Response(200, content=body, headers={"content-type": "application/json"})
    with pytest.raises(MalformedPayload):
        BiteboxAdapter().normalize(response)


def test_tiffinly_listings():
    batch = TiffinlyAdapter().normalize(json_response(TIFFINLY_PAYLOAD))
    listings = by_id(batch)
    assert batch.schema_seen == "tiffinly.v3"
    assert batch.records_received == 8

    veg = listings["tiffinly:T-88-4"]
    assert veg.provider == "tiffinly"
    assert veg.provider_label == "Tiffinly"
    assert veg.restaurant == "Dum Pukht House"
    assert veg.item == "Veg Dum Biryani (Serves 1)"
    assert veg.area == "Andheri West"
    assert veg.price_paise == 27900
    assert veg.effective_price_paise == 22900
    assert veg.rating == 4.6
    assert veg.rating_count == 1800
    assert (veg.eta_min_low, veg.eta_min_high) == (20, 30)
    assert veg.tags == ["veg", "bestseller"]
    assert veg.diet == "veg"
    assert veg.cuisines == []
    assert veg.offer is not None and veg.offer.label == "₹50 off above ₹249"
    assert veg.missing_fields == []


def test_tiffinly_diet_priority_and_offers():
    listings = by_id(TiffinlyAdapter().normalize(json_response(TIFFINLY_PAYLOAD)))
    assert listings["tiffinly:T-88-7"].diet == "non_veg"
    assert listings["tiffinly:T-70-3"].diet == "vegan"
    assert listings["tiffinly:T-70-4"].diet == "egg"
    assert listings["tiffinly:T-70-5"].diet is None
    bogo = listings["tiffinly:T-70-2"]
    assert bogo.offer is not None and bogo.offer.kind == "unknown"
    assert bogo.offer.label == "BOGO offer"
    assert bogo.effective_price_paise == 30000


def test_tiffinly_invalid_price_and_blank_title():
    batch = TiffinlyAdapter().normalize(json_response(TIFFINLY_PAYLOAD))
    listings = by_id(batch)
    pulao = listings["tiffinly:T-55-2"]
    assert pulao.price_paise is None
    assert pulao.rating is None
    assert (pulao.eta_min_low, pulao.eta_min_high) == (None, None)
    assert pulao.missing_fields == ["price", "rating", "eta"]
    assert "tiffinly:T-55-3" not in listings
    assert [(d.record_ref, d.reason) for d in batch.dropped] == [("T-55-3", "missing item name")]
    assert len(batch.listings) + len(batch.dropped) == batch.records_received


def test_tiffinly_partial_payload():
    payload = json.loads(json.dumps(TIFFINLY_PAYLOAD))
    for outlet in payload["data"]["outlets"]:
        for key in ("score", "votes", "deliveryTime"):
            outlet.pop(key)
    listings = by_id(TiffinlyAdapter().normalize(json_response(payload)))
    assert "rating" in listings["tiffinly:T-88-4"].missing_fields
    assert "eta" in listings["tiffinly:T-88-4"].missing_fields


@pytest.mark.parametrize("payload", [{"meta": {"schema": "tiffinly.v2"}, "data": {}}, {"data": {}}])
def test_tiffinly_unsupported_schema(payload):
    with pytest.raises(MalformedPayload, match="unsupported schema"):
        TiffinlyAdapter().normalize(json_response(payload))


def test_tiffinly_missing_outlets():
    payload = {"meta": {"schema": "tiffinly.v3"}, "data": {"outlets": {}}}
    with pytest.raises(MalformedPayload, match="missing outlets list"):
        TiffinlyAdapter().normalize(json_response(payload))


def test_tiffinly_drops_nameless_outlet_and_bad_entries():
    payload = {
        "meta": {"schema": "tiffinly.v3"},
        "data": {
            "outlets": [
                "junk",
                {"outletId": "X", "menu": [{"sku": "X-1", "title": "Dosa"}]},
                {
                    "outletId": "Y",
                    "outletName": "Y Cafe",
                    "menu": ["junk", {"sku": "Y-1", "title": "Dosa"}],
                },
            ]
        },
    }
    batch = TiffinlyAdapter().normalize(json_response(payload))
    assert [lst.listing_id for lst in batch.listings] == ["tiffinly:Y-1"]
    assert [d.reason for d in batch.dropped] == [
        "record is not an object",
        "missing restaurant name",
        "record is not an object",
    ]
    assert batch.records_received == 4
    assert [d.record_ref for d in batch.dropped] == [None, "X-1", None]


def test_khaana_listings():
    batch = KhaanaAdapter().normalize(httpx.Response(200, text=khaana_csv(KHAANA_ROWS)))
    listings = by_id(batch)
    assert batch.schema_seen == "khaana csv v1"
    assert batch.records_received == 7

    junction = listings["khaana:A-1"]
    assert junction.provider == "khaana"
    assert junction.provider_label == "Khaana Open Data"
    assert junction.restaurant == "Biryani Junction"
    assert junction.area == "Powai"
    assert junction.price_paise == 17500
    assert junction.rating == 3.5
    assert junction.rating_count == 380
    assert junction.cuisines == ["Biryani", "Mughlai"]
    assert junction.offer is None
    assert (junction.eta_min_low, junction.eta_min_high) == (None, None)
    assert junction.missing_fields == ["eta"]


def test_khaana_diet_flags():
    listings = by_id(KhaanaAdapter().normalize(httpx.Response(200, text=khaana_csv(KHAANA_ROWS))))
    assert listings["khaana:A-1"].diet == "veg"
    assert listings["khaana:A-8"].diet == "vegan"
    assert listings["khaana:A-9"].diet == "egg"
    assert listings["khaana:A-10"].diet == "non_veg"
    assert listings["khaana:A-4"].diet is None
    assert listings["khaana:A-4"].missing_fields == ["eta", "diet"]
    assert listings["khaana:A-9"].cuisines == []


def test_khaana_invalid_price_quoted_field_and_dropped_row():
    batch = KhaanaAdapter().normalize(httpx.Response(200, text=khaana_csv(KHAANA_ROWS)))
    listings = by_id(batch)
    large = listings["khaana:A-5"]
    assert large.item == "Veg Biryani, Large"
    assert large.price_paise is None
    assert large.missing_fields == ["price", "eta"]
    assert "khaana:A-6" not in listings
    assert [(d.record_ref, d.reason) for d in batch.dropped] == [
        ("A-6", "malformed CSV row: expected 9 fields, got 11")
    ]


def test_khaana_blank_ratings_and_blank_lines():
    text = khaana_csv(["", "A-2,Cafe,Dadar,Thali,Y,280,,,Thali", ""])
    batch = KhaanaAdapter().normalize(httpx.Response(200, text=text))
    assert batch.records_received == 1
    assert batch.listings[0].rating is None
    assert batch.listings[0].rating_count is None


def test_khaana_wrong_header():
    text = khaana_csv([], header=["ref", "name", "area"])
    with pytest.raises(MalformedPayload, match="unexpected CSV header"):
        KhaanaAdapter().normalize(httpx.Response(200, text=text))


@pytest.mark.parametrize("body", ["", "<html><body>Service temporarily unavailable</body></html>"])
def test_khaana_non_csv_body(body):
    with pytest.raises(MalformedPayload, match="unexpected CSV header"):
        KhaanaAdapter().normalize(httpx.Response(200, text=body))


def seen_request(adapter):
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, text="")

    search = ProviderSearch(query="biryani", area="Powai")
    return adapter, search, captured, httpx.MockTransport(handler)


async def test_bitebox_request_shape():
    adapter, search, captured, transport = seen_request(BiteboxAdapter())
    async with httpx.AsyncClient(transport=transport, base_url="http://mock/mock") as client:
        await adapter.fetch(client, search)
        await adapter.fetch(client, ProviderSearch(query="dosa"))
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/mock/bitebox/v2/search"
    assert dict(captured[0].url.params) == {"q": "biryani", "area": "Powai"}
    assert dict(captured[1].url.params) == {"q": "dosa"}


async def test_tiffinly_request_shape():
    adapter, search, captured, transport = seen_request(TiffinlyAdapter())
    async with httpx.AsyncClient(transport=transport, base_url="http://mock/mock") as client:
        await adapter.fetch(client, search)
    assert captured[0].method == "POST"
    assert captured[0].url.path == "/mock/tiffinly/api/v3/outlets/search"
    assert json.loads(captured[0].content) == {"query": "biryani"}


async def test_khaana_request_shape():
    adapter, search, captured, transport = seen_request(KhaanaAdapter())
    async with httpx.AsyncClient(transport=transport, base_url="http://mock") as client:
        await adapter.fetch(client, search)
    assert captured[0].method == "GET"
    assert captured[0].url.path == "/khaana/v1/listings.csv"
