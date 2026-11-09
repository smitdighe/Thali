lazy from thali.models import DedupeStats, Listing, OptionGroup
lazy from thali.text import RESTAURANT_STOPWORDS, name_tokens


def option_id_for(listing: Listing) -> str:
    restaurant_key = " ".join(
        token for token in name_tokens(listing.restaurant) if token not in RESTAURANT_STOPWORDS
    )
    item_key = " ".join(sorted(name_tokens(listing.item)))
    area_key = listing.area.lower() if listing.area else None
    option_id = f"{restaurant_key}|{area_key or ''}|{item_key}"
    return option_id if area_key else f"{option_id}|{listing.listing_id}"


def group_listings(listings: list[Listing]) -> tuple[list[OptionGroup], DedupeStats]:
    by_option: dict[str, dict[str, Listing]] = {}
    duplicates_removed = 0
    for listing in listings:
        per_provider = by_option.setdefault(option_id_for(listing), {})
        kept = per_provider.get(listing.provider)
        if kept is None:
            per_provider[listing.provider] = listing
            continue
        duplicates_removed += 1
        if len(listing.missing_fields) < len(kept.missing_fields):
            per_provider[listing.provider] = listing
    groups = [_build_group(option_id, members) for option_id, members in by_option.items()]
    merged_options = sum(1 for group in groups if len(group.listings) > 1)
    return groups, DedupeStats(duplicates_removed=duplicates_removed, merged_options=merged_options)


def _build_group(option_id: str, members: dict[str, Listing]) -> OptionGroup:
    members_in_order = list(members.values())
    first = members_in_order[0]
    return OptionGroup(
        option_id=option_id,
        restaurant=first.restaurant,
        area=first.area,
        item=min((m.item for m in members_in_order), key=len),
        listings=members_in_order,
    )
