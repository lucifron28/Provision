from sqlalchemy import func, select

from app.models.ingredient import Ingredient, IngredientAlias
from app.services.ingredient_matching import (
    lookup_ingredients,
    resolve_ingredient,
    seed_ingredient_catalog_v1,
)


def _seed_catalog(db) -> None:
    seed_ingredient_catalog_v1(db)
    db.flush()
    db.commit()


def test_catalog_seeding_is_idempotent_by_record_count(db) -> None:
    _seed_catalog(db)
    initial_counts = (
        db.scalar(select(func.count()).select_from(Ingredient)),
        db.scalar(select(func.count()).select_from(IngredientAlias)),
    )

    _seed_catalog(db)
    repeated_counts = (
        db.scalar(select(func.count()).select_from(Ingredient)),
        db.scalar(select(func.count()).select_from(IngredientAlias)),
    )

    assert initial_counts[0] > 0
    assert initial_counts[1] > initial_counts[0]
    assert repeated_counts == initial_counts


def test_curated_filipino_and_english_aliases_resolve_exactly(db) -> None:
    _seed_catalog(db)

    for display_name, canonical_name in (
        ("bawang", "garlic"),
        ("garlic cloves", "garlic"),
        ("toyo", "soy sauce"),
        ("soy sauce", "soy sauce"),
    ):
        resolution = resolve_ingredient(db, display_name=display_name)
        assert resolution.ingredient is not None
        assert resolution.ingredient.canonical_name == canonical_name
        assert resolution.ambiguous is False


def test_bagoong_stays_ambiguous_even_when_lookup_limit_is_one(db) -> None:
    _seed_catalog(db)

    resolution = resolve_ingredient(db, display_name="bagoong")
    limited_lookup = lookup_ingredients(db, "bagoong", limit=1)

    candidate_names = set(
        db.scalars(
            select(Ingredient.canonical_name).where(
                Ingredient.id.in_(resolution.candidate_ids)
            )
        ).all()
    )
    assert resolution.ingredient is None
    assert resolution.ambiguous is True
    assert candidate_names == {"shrimp paste", "fish paste"}
    assert limited_lookup.ambiguous is True
    assert len(limited_lookup.results) == 1


def test_normalization_handles_nfkc_case_and_repeated_spacing(db) -> None:
    _seed_catalog(db)

    for display_name in ("  ＢＡＷＡＮＧ　", "  GARLIC   CLOVES "):
        resolution = resolve_ingredient(db, display_name=display_name)
        assert resolution.ingredient is not None
        assert resolution.ingredient.canonical_name == "garlic"


def test_unknown_names_do_not_resolve_by_substring_but_lookup_can_suggest(db) -> None:
    _seed_catalog(db)

    prefix_resolution = resolve_ingredient(db, display_name="garli")
    prefix_suggestions = lookup_ingredients(db, "garli")
    unknown_resolution = resolve_ingredient(db, display_name="zxqv-unlisted")
    unknown_lookup = lookup_ingredients(db, "zxqv-unlisted")

    assert prefix_resolution.ingredient is None
    assert prefix_resolution.ambiguous is False
    assert prefix_resolution.reason == "ingredient_name_not_found"
    assert "garlic" in {item.canonical_name for item in prefix_suggestions.results}
    assert unknown_resolution.ingredient is None
    assert unknown_lookup.results == []


def test_inactive_ingredient_stays_inactive_and_cannot_be_resolved_after_reseed(db) -> None:
    _seed_catalog(db)
    garlic = db.scalar(select(Ingredient).where(Ingredient.normalized_name == "garlic"))
    assert garlic is not None

    garlic.is_active = False
    db.commit()
    seed_ingredient_catalog_v1(db)
    db.flush()
    db.commit()
    db.refresh(garlic)

    by_id = resolve_ingredient(db, ingredient_id=garlic.id)
    by_alias = resolve_ingredient(db, display_name="bawang")
    alias_lookup = lookup_ingredients(db, "bawang")

    assert garlic.is_active is False
    assert by_id.ingredient is None
    assert by_alias.ingredient is None
    assert all(item.canonical_name != "garlic" for item in alias_lookup.results)


def test_percent_and_underscore_are_literal_lookup_characters(db) -> None:
    _seed_catalog(db)

    percent_results = lookup_ingredients(db, "%")
    underscore_results = lookup_ingredients(db, "_")

    assert percent_results.results == []
    assert underscore_results.results == []
