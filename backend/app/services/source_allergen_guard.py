"""Reject known source-ingredient conflicts without inventing quantities."""

from collections import defaultdict
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.allergens import IngredientAllergen, IngredientDerivative
from app.models.household import HouseholdMembership
from app.models.ingredient import Ingredient, IngredientAlias
from app.models.user import User
from app.services.allergen_policy import _ancestry
from app.services.ingredient_matching import normalize_ingredient_name, resolve_ingredient
from app.services.preferences import read_profile


def has_known_source_conflict(db: Session, household_id: int, names: list[str]) -> bool:
    """Reject only confirmed conflicts; false never means a recipe is safe."""
    member_ids = db.scalars(select(HouseholdMembership.user_id).join(
        User, User.id == HouseholdMembership.user_id
    ).where(HouseholdMembership.household_id == household_id, User.is_active.is_(True))).all()
    profiles = [read_profile(db, household_id, member_id) for member_id in member_ids]
    profiles.append(read_profile(db, household_id, None))
    declarations = [item for profile in profiles for item in profile.allergies]
    codes = {item.allergen_code for item in declarations if item.allergen_code}
    diets = {diet for profile in profiles for diet in profile.preferences.diet_patterns}
    excluded = {item for profile in profiles for item in profile.preferences.ingredient_exclusions}
    custom = set()
    for declaration in declarations:
        if declaration.custom_text:
            ingredient = resolve_ingredient(db, display_name=declaration.custom_text).ingredient
            if ingredient is not None:
                custom.add(ingredient.id)
    if "dairy_free" in diets or "vegan" in diets:
        codes.add("milk")
    if "vegan" in diets:
        codes.add("egg")
    if "gluten_free" in diets:
        codes.add("wheat")
    if "vegetarian" in diets or "vegan" in diets:
        codes.update({"fish", "crustacean_shellfish"})

    edges, associations = defaultdict(list), defaultdict(list)
    for edge in db.scalars(select(IngredientDerivative).order_by(IngredientDerivative.id)).all():
        edges[edge.ingredient_id].append(edge)
    for association in db.scalars(select(IngredientAllergen).order_by(IngredientAllergen.id)).all():
        associations[association.ingredient_id].append(association)
    ingredients = {item.id: item for item in db.scalars(select(Ingredient)).all()}
    for name in names:
        ingredient = resolve_ingredient(db, display_name=name).ingredient
        if ingredient is None:
            continue
        certain, _, _ = _ancestry(ingredient.id, edges)
        if certain & (excluded | custom):
            return True
        if any(association.allergen_code in codes and association.checked_at is not None
               and bool(association.evidence_reference.strip())
               and association.relation in {"DIRECT", "DERIVATIVE"}
               for node in certain for association in associations.get(node, [])):
            return True
        known_names = {ingredients[node].normalized_name for node in certain if node in ingredients}
        families = {ingredients[node].family for node in certain if node in ingredients}
        meat = bool(known_names & {"pork", "beef", "chicken"} or families & {"meat", "poultry"})
        animal = meat or bool(known_names & {"fish", "shrimp"} or "seafood" in families)
        if (({"no_pork", "halal"} & diets and "pork" in known_names)
                or ("pescatarian" in diets and meat)
                or ("vegetarian" in diets and animal)
                or ("vegan" in diets and (animal or known_names & {"egg", "milk", "honey"}
                                           or families & {"dairy", "egg"}))):
            return True
    return False


def has_known_text_ingredient_conflict(db: Session, household_id: int, lines: list[str]) -> bool:
    """Find known ingredient names in source lines, without inferring amounts."""
    names = set(db.scalars(select(Ingredient.normalized_name).where(Ingredient.is_active.is_(True))).all())
    names.update(db.scalars(select(IngredientAlias.normalized_alias).join(
        Ingredient, Ingredient.id == IngredientAlias.ingredient_id
    ).where(Ingredient.is_active.is_(True))).all())
    matched = set()
    for line in lines:
        normalized = normalize_ingredient_name(line)
        for name in names:
            if name and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", normalized):
                matched.add(name)
    return has_known_source_conflict(db, household_id, sorted(matched))
