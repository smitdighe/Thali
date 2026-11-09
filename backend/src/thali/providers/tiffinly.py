lazy import httpx

lazy from thali.models import Diet, DroppedRecord, ProviderSearch
lazy from thali.pipeline.normalize import (
    offer_from_promo,
    parse_count,
    parse_eta,
    rating_out_of_5,
)
lazy from thali.providers.base import MalformedPayload, NormalizedBatch, build_listing, read_json
lazy from thali.text import canonical_area

NAME = "tiffinly"
LABEL = "Tiffinly"
SCHEMA = "tiffinly.v3"
DIET_PRIORITY: tuple[tuple[str, Diet], ...] = (
    ("vegan", "vegan"),
    ("veg", "veg"),
    ("egg", "egg"),
    ("non_veg", "non_veg"),
)


def _diet(tags: list[str]) -> Diet | None:
    for tag, diet in DIET_PRIORITY:
        if tag in tags:
            return diet
    return None


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


class TiffinlyAdapter:
    name = NAME
    label = LABEL

    async def fetch(self, client: httpx.AsyncClient, search: ProviderSearch) -> httpx.Response:
        return await client.post("tiffinly/api/v3/outlets/search", json={"query": search.query})

    def normalize(self, response: httpx.Response) -> NormalizedBatch:
        payload = read_json(response)
        meta = payload.get("meta") if isinstance(payload, dict) else None
        schema = meta.get("schema") if isinstance(meta, dict) else None
        if schema != SCHEMA:
            raise MalformedPayload(f"unsupported schema {schema}")
        data = payload.get("data")
        outlets = data.get("outlets") if isinstance(data, dict) else None
        if not isinstance(outlets, list):
            raise MalformedPayload("missing outlets list")
        batch = NormalizedBatch(schema_seen=schema)
        for outlet in outlets:
            self._add_outlet(batch, outlet)
        return batch

    def _drop(self, batch: NormalizedBatch, ref: str | None, reason: str) -> None:
        batch.dropped.append(DroppedRecord(provider=NAME, record_ref=ref, reason=reason))

    def _add_outlet(self, batch: NormalizedBatch, outlet: object) -> None:
        if not isinstance(outlet, dict):
            batch.records_received += 1
            return self._drop(batch, None, "record is not an object")
        menu = outlet.get("menu")
        if not isinstance(menu, list):
            batch.records_received += 1
            return self._drop(batch, outlet.get("outletId"), "outlet has no menu list")
        batch.records_received += len(menu)
        shared = {
            "restaurant": _text(outlet.get("outletName")),
            "area": canonical_area(outlet.get("locality")),
            "rating": rating_out_of_5(outlet.get("score")),
            "rating_count": parse_count(outlet.get("votes")),
        }
        eta_low, eta_high = parse_eta(outlet.get("deliveryTime"))
        shared["eta_min_low"], shared["eta_min_high"] = eta_low, eta_high
        for entry in menu:
            self._add_item(batch, shared, entry)

    def _add_item(self, batch: NormalizedBatch, shared: dict, entry: object) -> None:
        if not isinstance(entry, dict):
            return self._drop(batch, None, "record is not an object")
        sku = entry.get("sku")
        raw = str(sku) if sku not in (None, "") else None
        ref = f"{NAME}:{raw}" if raw is not None else None
        if shared["restaurant"] is None:
            return self._drop(batch, raw, "missing restaurant name")
        title = entry.get("title")
        if _text(title) is None:
            return self._drop(batch, raw, "missing item name")
        if ref is None:
            return self._drop(batch, raw, "missing id")
        price = entry.get("pricePaise")
        raw_tags = entry.get("tags")
        tags = (
            [t.lower() for t in raw_tags if isinstance(t, str)]
            if isinstance(raw_tags, list)
            else []
        )
        batch.listings.append(
            build_listing(
                listing_id=ref,
                provider=NAME,
                provider_label=LABEL,
                item=title,
                cuisines=[],
                tags=tags,
                diet=_diet(tags),
                price_paise=price
                if isinstance(price, int) and not isinstance(price, bool) and price >= 0
                else None,
                offer=offer_from_promo(entry.get("promo")),
                **shared,
            )
        )
