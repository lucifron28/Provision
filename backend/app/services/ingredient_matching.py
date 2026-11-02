"""Deterministic ingredient name lookup and v1 catalog seeding."""

from dataclasses import dataclass
from datetime import datetime, timezone
import unicodedata

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.data.ingredient_catalog_v1 import INGREDIENT_CATALOG_V1
from app.models.ingredient import Ingredient, IngredientAlias
from app.schemas.ingredients import (
    IngredientAliasRead,
    IngredientLookupCandidate,
    IngredientLookupRead,
)
from app.services.units import normalize_unit


_UNIT_DIMENSIONS = {"g": "mass", "kg": "mass", "ml": "volume", "l": "volume", "count": "count"}


@dataclass(frozen=True)
class IngredientResolution:
    ingredient: Ingredient | None
    ambiguous: bool = False
    candidate_ids: tuple[int, ...] = ()
    reason: str | None = None


def normalize_ingredient_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(normalized.split())


def seed_ingredient_catalog_v1(db: Session) -> None:
    """Insert missing v1 identities and aliases without overwriting curated rows."""
    existing_ingredients = {
        item.normalized_name: item
        for item in db.scalars(select(Ingredient)).all()
    }
    now = datetime.now(timezone.utc)

    for entry in INGREDIENT_CATALOG_V1:
        canonical = entry["canonical_name"]
        normalized_name = normalize_ingredient_name(canonical)
        ingredient = existing_ingredients.get(normalized_name)
        if ingredient is None:
            default_unit = normalize_unit(entry["default_unit"])
            ingredient = Ingredient(
                canonical_name=canonical,
                normalized_name=normalized_name,
                filipino_name=entry["filipino_name"],
                family=entry["family"],
                default_dimension=_UNIT_DIMENSIONS[default_unit],
                default_unit=default_unit,
                is_active=True,
            )
            db.add(ingredient)
            db.flush()
            existing_ingredients[normalized_name] = ingredient

        existing_aliases = {
            (alias.normalized_alias, alias.language)
            for alias in db.scalars(
                select(IngredientAlias).where(IngredientAlias.ingredient_id == ingredient.id)
            ).all()
        }
        aliases = tuple(dict.fromkeys((entry["filipino_name"], *entry["aliases"])))
        for alias in aliases:
            normalized_alias = normalize_ingredient_name(alias)
            language = "fil" if normalized_alias == normalize_ingredient_name(entry["filipino_name"]) else "und"
            key = (normalized_alias, language)
            if key in existing_aliases:
                continue
            db.add(
                IngredientAlias(
                    ingredient_id=ingredient.id,
                    alias=alias,
                    normalized_alias=normalized_alias,
                    language=language,
                    region="PH" if language == "fil" else None,
                    reviewed_at=now,
                )
            )
            existing_aliases.add(key)


def lookup_ingredients(
    db: Session,
    query: str | None,
    limit: int = 50,
) -> IngredientLookupRead:
    normalized = normalize_ingredient_name(query) if query is not None else None
    exact_ids: set[int] = set()
    matched_aliases: dict[int, str] = {}

    if normalized:
        exact_ids.update(
            db.scalars(
                select(Ingredient.id).where(
                    Ingredient.is_active.is_(True),
                    Ingredient.normalized_name == normalized,
                )
            ).all()
        )
        exact_alias_rows = db.execute(
            select(IngredientAlias.ingredient_id, IngredientAlias.alias)
            .join(Ingredient, Ingredient.id == IngredientAlias.ingredient_id)
            .where(
                Ingredient.is_active.is_(True),
                IngredientAlias.normalized_alias == normalized,
            )
            .order_by(IngredientAlias.ingredient_id, IngredientAlias.alias)
        ).all()
        for ingredient_id, alias in exact_alias_rows:
            exact_ids.add(ingredient_id)
            matched_aliases.setdefault(ingredient_id, alias)

    if exact_ids:
        ingredients = db.scalars(
            select(Ingredient)
            .where(Ingredient.id.in_(sorted(exact_ids)))
            .order_by(Ingredient.canonical_name)
            .limit(limit)
        ).all()
    elif normalized:
        escaped = normalized.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        ingredients = db.scalars(
            select(Ingredient)
            .outerjoin(IngredientAlias, IngredientAlias.ingredient_id == Ingredient.id)
            .where(
                Ingredient.is_active.is_(True),
                or_(
                    Ingredient.normalized_name.ilike(pattern, escape="\\"),
                    IngredientAlias.normalized_alias.ilike(pattern, escape="\\"),
                ),
            )
            .distinct()
            .order_by(Ingredient.canonical_name)
            .limit(limit)
        ).all()
    else:
        ingredients = db.scalars(
            select(Ingredient)
            .where(Ingredient.is_active.is_(True))
            .order_by(Ingredient.canonical_name)
            .limit(limit)
        ).all()

    results = []
    for ingredient in ingredients:
        aliases = db.scalars(
            select(IngredientAlias)
            .where(IngredientAlias.ingredient_id == ingredient.id)
            .order_by(IngredientAlias.normalized_alias, IngredientAlias.language)
        ).all()
        results.append(
            IngredientLookupCandidate(
                id=ingredient.id,
                canonical_name=ingredient.canonical_name,
                filipino_name=ingredient.filipino_name,
                family=ingredient.family,
                default_unit=ingredient.default_unit,
                aliases=[
                    IngredientAliasRead(alias=item.alias, language=item.language, region=item.region)
                    for item in aliases
                ],
                is_active=ingredient.is_active,
                matched_alias=matched_aliases.get(ingredient.id),
            )
        )

    ambiguous = len(exact_ids) > 1
    if len(exact_ids) > limit:
        ambiguous = True
    return IngredientLookupRead(query=query, ambiguous=ambiguous, results=results)


def resolve_ingredient(
    db: Session,
    *,
    ingredient_id: int | None = None,
    display_name: str | None = None,
) -> IngredientResolution:
    if ingredient_id is not None:
        ingredient = db.scalar(
            select(Ingredient).where(
                Ingredient.id == ingredient_id,
                Ingredient.is_active.is_(True),
            )
        )
        return IngredientResolution(
            ingredient=ingredient,
            candidate_ids=(ingredient.id,) if ingredient else (),
            reason=None if ingredient else "ingredient_not_found",
        )

    if display_name is None:
        return IngredientResolution(None, reason="ingredient_reference_missing")
    normalized = normalize_ingredient_name(display_name)
    ids = set(
        db.scalars(
            select(Ingredient.id).where(
                Ingredient.is_active.is_(True), Ingredient.normalized_name == normalized
            )
        ).all()
    )
    ids.update(
        db.scalars(
            select(IngredientAlias.ingredient_id)
            .join(Ingredient, Ingredient.id == IngredientAlias.ingredient_id)
            .where(
                Ingredient.is_active.is_(True),
                IngredientAlias.normalized_alias == normalized,
            )
        ).all()
    )
    ordered_ids = tuple(sorted(ids))
    if len(ordered_ids) != 1:
        return IngredientResolution(
            ingredient=None,
            ambiguous=len(ordered_ids) > 1,
            candidate_ids=ordered_ids,
            reason="ambiguous_ingredient_name" if ordered_ids else "ingredient_name_not_found",
        )
    ingredient = db.get(Ingredient, ordered_ids[0])
    return IngredientResolution(
        ingredient=ingredient,
        candidate_ids=ordered_ids,
        reason=None if ingredient else "ingredient_name_not_found",
    )
