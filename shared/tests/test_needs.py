from shared import NeedsProfile, ProductLine, merge_profiles


def test_merge_never_overwrites_with_none() -> None:
    base = NeedsProfile(age=34, product_lines=[ProductLine.LIFE])
    update = NeedsProfile(dependents=2)  # age unknown in this update
    merged = merge_profiles(base, update)
    assert merged.age == 34
    assert merged.dependents == 2
    assert merged.product_lines == [ProductLine.LIFE]


def test_merge_unions_lines_and_merges_per_line() -> None:
    base = NeedsProfile(
        product_lines=[ProductLine.TRAVEL],
        per_line={"travel": {"destination_region": "asia"}},
    )
    update = NeedsProfile(
        product_lines=[ProductLine.PET, ProductLine.TRAVEL],
        per_line={"travel": {"trip_days": 14}, "pet": {"species": "dog"}},
    )
    merged = merge_profiles(base, update)
    assert set(merged.product_lines) == {ProductLine.TRAVEL, ProductLine.PET}
    assert merged.per_line["travel"] == {"destination_region": "asia", "trip_days": 14}
    assert merged.per_line["pet"] == {"species": "dog"}


def test_merge_lets_corrections_win() -> None:
    base = NeedsProfile(age=34)
    update = NeedsProfile(age=35)  # user corrected themselves
    assert merge_profiles(base, update).age == 35
