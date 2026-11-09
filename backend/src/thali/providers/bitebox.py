lazy import httpx

lazy from thali.models import Diet, DroppedRecord, ProviderSearch
lazy from thali.pipeline.normalize import (
    money_to_paise,
    parse_count,
    parse_eta,
    parse_offer_text,
    rating_out_of_5,
)
lazy from thali.providers.base import MalformedPayload, NormalizedBatch, build_listing, read_json
lazy from thali.text import canonical_area

NAME = "bitebox"
LABEL = "Bitebox"


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _diet(record: dict) -> Diet | None:
    if record.get("is_vegan") is True:
        return "vegan"
    if record.get("is_veg") is True:
        return "veg"
    if record.get("is_veg") is False:
        return "non_veg"
    return None


class BiteboxAdapter:
    name = NAME
    label = LABEL

    async def fetch(self, client: httpx.AsyncClient, search: ProviderSearch) -> httpx.Response:
        params = {"q": search.query}
        if search.area is not None:
            params["area"] = search.area
        return await client.get("bitebox/v2/search", params=params)

    def normalize(self, response: httpx.Response) -> NormalizedBatch:
        payload = read_json(response)
        if not isinstance(payload, dict):
            raise MalformedPayload("unsupported api_version None")
        version = payload.get("api_version")
        if not isinstance(version, str) or not version.startswith("2."):
            raise MalformedPayload(f"unsupported api_version {version}")
        results = payload.get("results")
        if not isinstance(results, list):
            raise MalformedPayload("missing results list")
        batch = NormalizedBatch(records_received=len(results), schema_seen=f"bitebox {version}")
        for record in results:
            self._add_record(batch, record)
        return batch

    def _drop(self, batch: NormalizedBatch, ref: str | None, reason: str) -> None:
        batch.dropped.append(DroppedRecord(provider=NAME, record_ref=ref, reason=reason))

    def _add_record(self, batch: NormalizedBatch, record: object) -> None:
        if not isinstance(record, dict):
            return self._drop(batch, None, "record is not an object")
        record_id = record.get("id")
        raw = str(record_id) if record_id not in (None, "") else None
        ref = f"{NAME}:{raw}" if raw is not None else None
        restaurant = record.get("restaurant")
        restaurant = restaurant if isinstance(restaurant, dict) else {}
        restaurant_name = _text(restaurant.get("name"))
        if restaurant_name is None:
            return self._drop(batch, raw, "missing restaurant name")
        item = _text(record.get("dish"))
        if item is None:
            return self._drop(batch, raw, "missing item name")
        if ref is None:
            return self._drop(batch, raw, "missing id")
        eta_low, eta_high = parse_eta(record.get("eta_minutes"))
        cuisine = record.get("cuisine")
        batch.listings.append(
            build_listing(
                listing_id=ref,
                provider=NAME,
                provider_label=LABEL,
                restaurant=restaurant_name,
                area=canonical_area(restaurant.get("area")),
                item=item,
                cuisines=[c for c in cuisine if isinstance(c, str)]
                if isinstance(cuisine, list)
                else [],
                tags=[],
                diet=_diet(record),
                price_paise=money_to_paise(record.get("price")),
                offer=parse_offer_text(record.get("offer")),
                rating=rating_out_of_5(record.get("rating")),
                rating_count=parse_count(record.get("ratings_count")),
                eta_min_low=eta_low,
                eta_min_high=eta_high,
            )
        )
