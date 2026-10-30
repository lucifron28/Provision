from collections import defaultdict

import pytest

from app.data.ingredient_catalog_v1 import INGREDIENT_CATALOG_V1
from app.services.units import normalize_unit


def _normalize_name(value: str) -> str:
    return " ".join(value.casefold().split())


def test_catalog_v1_is_a_versioned_tuple_with_at_least_30_entries() -> None:
    assert isinstance(INGREDIENT_CATALOG_V1, tuple)
    assert len(INGREDIENT_CATALOG_V1) >= 30


def test_canonical_names_are_unique_after_normalization() -> None:
    names = [_normalize_name(entry["canonical_name"]) for entry in INGREDIENT_CATALOG_V1]

    assert len(names) == len(set(names))


def test_entries_have_only_identity_fields_and_supported_default_units() -> None:
    expected_keys = {
        "canonical_name",
        "filipino_name",
        "family",
        "default_unit",
        "aliases",
    }

    for entry in INGREDIENT_CATALOG_V1:
        assert isinstance(entry, dict)
        assert set(entry) == expected_keys
        assert entry["canonical_name"].strip()
        assert entry["filipino_name"].strip()
        assert entry["family"].strip()
        assert isinstance(entry["aliases"], tuple)
        assert entry["aliases"]
        assert all(alias.strip() for alias in entry["aliases"])
        assert normalize_unit(entry["default_unit"]) == entry["default_unit"]
        assert entry["default_unit"] in {"g", "ml", "count"}


@pytest.mark.parametrize(
    ("canonical_name", "filipino_name", "alias"),
    [
        ("garlic", "bawang", "garlic cloves"),
        ("onion", "sibuyas", "yellow onion"),
        ("ginger", "luya", "fresh ginger"),
        ("egg", "itlog", "chicken egg"),
        ("eggplant", "talong", "aubergine"),
        ("water spinach", "kangkong", "swamp cabbage"),
        ("fish sauce", "patis", "patis"),
        ("soy sauce", "toyo", "toyo"),
        ("shrimp paste", "bagoong alamang", "alamang"),
    ],
)
def test_catalog_contains_requested_filipino_and_english_names(
    canonical_name: str, filipino_name: str, alias: str
) -> None:
    entry = next(
        item for item in INGREDIENT_CATALOG_V1 if item["canonical_name"] == canonical_name
    )

    assert entry["filipino_name"] == filipino_name
    assert entry["canonical_name"].casefold() == canonical_name.casefold()
    assert _normalize_name(alias) in {
        _normalize_name(alias) for alias in entry["aliases"]
    }


def test_bagoong_alias_is_deliberately_ambiguous() -> None:
    matches = [
        entry["canonical_name"]
        for entry in INGREDIENT_CATALOG_V1
        if any(_normalize_name(alias) == "bagoong" for alias in entry["aliases"])
    ]

    assert matches == ["shrimp paste", "fish paste"]


def test_dish_name_is_not_registered_as_an_ingredient_alias() -> None:
    aliases = {
        _normalize_name(alias)
        for entry in INGREDIENT_CATALOG_V1
        for alias in entry["aliases"]
    }

    assert "pancit" not in aliases


def test_alias_collisions_are_limited_to_the_curated_ambiguous_term() -> None:
    owners: dict[str, set[str]] = defaultdict(set)
    for entry in INGREDIENT_CATALOG_V1:
        for alias in entry["aliases"]:
            owners[_normalize_name(alias)].add(entry["canonical_name"])

    collisions = {alias: names for alias, names in owners.items() if len(names) > 1}

    assert collisions == {"bagoong": {"shrimp paste", "fish paste"}}
