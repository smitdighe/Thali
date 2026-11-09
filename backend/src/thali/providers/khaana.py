lazy import csv
lazy import io

lazy import httpx

lazy from thali.models import Diet, DroppedRecord, ProviderSearch
lazy from thali.pipeline.normalize import money_to_paise, parse_count, rating_out_of_5
lazy from thali.providers.base import MalformedPayload, NormalizedBatch, build_listing
lazy from thali.text import canonical_area

NAME = "khaana"
LABEL = "Khaana Open Data"
SCHEMA = "khaana csv v1"
COLUMNS = [
    "listing_ref",
    "eatery",
    "neighbourhood",
    "item",
    "veg_flag",
    "price",
    "avg_rating",
    "num_ratings",
    "cuisines",
]
DIET_FLAGS: dict[str, Diet] = {"VG": "vegan", "Y": "veg", "E": "egg", "N": "non_veg"}


class KhaanaAdapter:
    name = NAME
    label = LABEL

    async def fetch(self, client: httpx.AsyncClient, search: ProviderSearch) -> httpx.Response:
        return await client.get("khaana/v1/listings.csv")

    def normalize(self, response: httpx.Response) -> NormalizedBatch:
        rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
        if not rows or rows[0] != COLUMNS:
            raise MalformedPayload("unexpected CSV header")
        batch = NormalizedBatch(schema_seen=SCHEMA)
        for row in rows[1:]:
            if row:
                batch.records_received += 1
                self._add_row(batch, row)
        return batch

    def _drop(self, batch: NormalizedBatch, ref: str | None, reason: str) -> None:
        batch.dropped.append(DroppedRecord(provider=NAME, record_ref=ref, reason=reason))

    def _add_row(self, batch: NormalizedBatch, row: list[str]) -> None:
        ref_value = row[0].strip()
        raw = ref_value or None
        ref = f"{NAME}:{raw}" if raw else None
        if len(row) != len(COLUMNS):
            return self._drop(
                batch, raw, f"malformed CSV row: expected {len(COLUMNS)} fields, got {len(row)}"
            )
        _, eatery, area, item, veg_flag, price, rating, rating_count, cuisines = row
        if not eatery.strip():
            return self._drop(batch, raw, "missing restaurant name")
        if not item.strip():
            return self._drop(batch, raw, "missing item name")
        if ref is None:
            return self._drop(batch, raw, "missing id")
        batch.listings.append(
            build_listing(
                listing_id=ref,
                provider=NAME,
                provider_label=LABEL,
                restaurant=eatery.strip(),
                area=canonical_area(area),
                item=item.strip(),
                cuisines=[c.strip() for c in cuisines.split("|") if c.strip()],
                tags=[],
                diet=DIET_FLAGS.get(veg_flag.strip().upper()),
                price_paise=money_to_paise(price),
                offer=None,
                rating=rating_out_of_5(rating),
                rating_count=parse_count(rating_count),
                eta_min_low=None,
                eta_min_high=None,
            )
        )
