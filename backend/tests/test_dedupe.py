from thali.models import Listing
from thali.pipeline.dedupe import group_listings
from thali.pipeline.normalize import missing_fields


def make(
    listing_id: str,
    restaurant: str,
    item: str,
    area: str | None,
    **overrides,
) -> Listing:
    provider = listing_id.split(":")[0]
    values = {
        "listing_id": listing_id,
        "provider": provider,
        "provider_label": provider.title(),
        "restaurant": restaurant,
        "item": item,
        "area": area,
        "price_paise": 20000,
        "rating": 4.0,
        "eta_min_high": 30,
        "diet": "veg",
    }
    values.update(overrides)
    listing = Listing(**values)
    listing.missing_fields = missing_fields(listing)
    return listing


def build_full_data() -> list[Listing]:
    return [
        make("bitebox:bb_101", "Dum Pukht House", "Veg Dum Biryani", "Andheri West"),
        make("bitebox:bb_103", "Biryani Junction", "Veg Biryani", "Powai"),
        make("bitebox:bb_104", "Biryani Junction", "Veg Biryani", "Powai"),
        make("bitebox:bb_105", "Lucknowi Degh", "Subz Dum Biryani", "Bandra West"),
        make("bitebox:bb_107", "Hyderabad House", "Veg Biryani", "Andheri West"),
        make("bitebox:bb_108", "Hyderabad House", "Veg Biryani", "Dadar"),
        make("bitebox:bb_201", "Momo Mia", "Veg Steamed Momos", "Powai"),
        make("bitebox:bb_203", "Udupi Corner", "Masala Dosa", "Dadar"),
        make("bitebox:bb_207", "Wok Express", "Hakka Noodles", "Lower Parel"),
        make("tiffinly:T-88-4", "Dum Pukht House", "Veg Dum Biryani (Serves 1)", "Andheri West"),
        make("tiffinly:T-12-1", "Lucknowi Degh", "Subz Dum Biryani", "Bandra West"),
        make("tiffinly:T-31-1", "Momo Mia", "Veg Steamed Momos", "Powai"),
        make("tiffinly:T-64-1", "Wok Express", "Veg Hakka Noodles", "Lower Parel"),
        make("khaana:A-1", "Biryani Junction", "Veg Biryani", "Powai"),
        make("khaana:A-3", "Udupi Corner", "Masala Dosa", "Dadar"),
        make("khaana:A-4", "Udupi Corner", "Mysore Masala Dosa", "Dadar"),
    ]


def ids_by_option(groups):
    return {(g.restaurant, g.area, g.item): [m.listing_id for m in g.listings] for g in groups}


def test_expected_groups_on_full_data():
    groups, stats = group_listings(build_full_data())
    by_option = ids_by_option(groups)
    assert by_option[("Dum Pukht House", "Andheri West", "Veg Dum Biryani")] == [
        "bitebox:bb_101",
        "tiffinly:T-88-4",
    ]
    assert by_option[("Lucknowi Degh", "Bandra West", "Subz Dum Biryani")] == [
        "bitebox:bb_105",
        "tiffinly:T-12-1",
    ]
    assert by_option[("Biryani Junction", "Powai", "Veg Biryani")] == [
        "bitebox:bb_103",
        "khaana:A-1",
    ]
    assert by_option[("Udupi Corner", "Dadar", "Masala Dosa")] == [
        "bitebox:bb_203",
        "khaana:A-3",
    ]
    assert by_option[("Momo Mia", "Powai", "Veg Steamed Momos")] == [
        "bitebox:bb_201",
        "tiffinly:T-31-1",
    ]
    assert stats.duplicates_removed == 1
    assert stats.merged_options == 5


def test_chain_branches_in_different_areas_stay_separate():
    groups, _ = group_listings(build_full_data())
    hyderabad = [g for g in groups if g.restaurant == "Hyderabad House"]
    assert sorted(g.area for g in hyderabad) == ["Andheri West", "Dadar"]
    assert all(len(g.listings) == 1 for g in hyderabad)


def test_item_variants_stay_separate():
    groups, _ = group_listings(build_full_data())
    wok = [g for g in groups if g.restaurant == "Wok Express"]
    assert sorted(g.item for g in wok) == ["Hakka Noodles", "Veg Hakka Noodles"]
    dosa = [g for g in groups if g.restaurant == "Udupi Corner"]
    assert len(dosa) == 2


def test_groups_keep_first_seen_order():
    groups, _ = group_listings(build_full_data())
    assert [g.restaurant for g in groups][:4] == [
        "Dum Pukht House",
        "Biryani Junction",
        "Lucknowi Degh",
        "Hyderabad House",
    ]


def test_in_provider_duplicate_keeps_first_on_tie():
    first = make("bitebox:bb_103", "Biryani Junction", "Veg Biryani", "Powai")
    second = make("bitebox:bb_104", "Biryani Junction", "Veg Biryani", "Powai")
    groups, stats = group_listings([first, second])
    assert len(groups) == 1
    assert [m.listing_id for m in groups[0].listings] == ["bitebox:bb_103"]
    assert stats.duplicates_removed == 1
    assert stats.merged_options == 0


def test_in_provider_duplicate_keeps_listing_with_fewer_missing_fields():
    sparse = make("bitebox:bb_1", "Cafe", "Veg Biryani", "Powai", rating=None, eta_min_high=None)
    complete = make("bitebox:bb_2", "Cafe", "Veg Biryani", "Powai")
    groups, stats = group_listings([sparse, complete])
    assert [m.listing_id for m in groups[0].listings] == ["bitebox:bb_2"]
    assert stats.duplicates_removed == 1


def test_display_item_is_shortest_in_group():
    long_first = make("bitebox:b1", "Cafe", "Veg Dum Biryani", "Powai")
    shorter = make("tiffinly:t1", "Cafe", "Dum Veg Biryani", "Powai")
    groups, _ = group_listings([long_first, shorter])
    assert len(groups) == 1
    assert groups[0].item == "Veg Dum Biryani"
    assert groups[0].restaurant == "Cafe"


def test_restaurant_stopwords_and_punctuation_are_ignored():
    first = make("bitebox:b1", "The Dum Pukht House", "Veg Biryani", "Powai")
    second = make("tiffinly:t1", "Dum Pukht House Restaurant", "Veg Biryani (Serves 2)", "Powai")
    groups, stats = group_listings([first, second])
    assert len(groups) == 1
    assert stats.merged_options == 1


def test_synonym_spelling_merges():
    first = make("bitebox:b1", "Biryani Darbar", "Hyderabadi Veg Biryani", "Andheri West")
    second = make("khaana:A-7", "Biryani Darbar", "Hyderabadi Veg Biriyani", "Andheri West")
    groups, _ = group_listings([first, second])
    assert len(groups) == 1


def test_unknown_area_never_merges():
    first = make("bitebox:b1", "Cafe", "Veg Biryani", None)
    second = make("tiffinly:t1", "Cafe", "Veg Biryani", None)
    third = make("bitebox:b2", "Cafe", "Veg Biryani", None)
    groups, stats = group_listings([first, second, third])
    assert len(groups) == 3
    assert all(g.option_id.endswith(g.listings[0].listing_id) for g in groups)
    assert stats.duplicates_removed == 0
    assert stats.merged_options == 0


def test_empty_input():
    groups, stats = group_listings([])
    assert groups == []
    assert stats.duplicates_removed == 0
    assert stats.merged_options == 0
