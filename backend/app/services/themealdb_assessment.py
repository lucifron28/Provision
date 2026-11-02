"""Deterministic pantry and safety assessment of explicit source measures."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.schemas.food_safety import FoodSafetyRequest
from app.schemas.ingredients import IngredientRequirementInput
from app.schemas.themealdb import MealDBAssessmentInput, MealDBAssessmentRead
from app.services.allergen_policy import evaluate_food_safety
from app.services.deepseek_discovery import _require_member_and_consent
from app.services.themealdb_reviewed import ensure_meal_source_approvals, lookup_reviewed_meal


def assess_reviewed_meal(
    db: Session, household_id: int, actor_id: int, meal_id: str, request: MealDBAssessmentInput, *,
    client, budget,
) -> MealDBAssessmentRead:
    """Assess only literal source quantities, using a user-confirmed serving basis."""
    recipe = lookup_reviewed_meal(db, household_id, actor_id, meal_id, client=client, budget=budget,
                                  allow_broader_web=request.allow_broader_web)
    if recipe is None:
        raise HTTPException(404, "MEAL_NOT_FOUND")
    if request.source_digest != recipe.content_digest:
        raise HTTPException(409, "SOURCE_RECIPE_CHANGED")
    confirmed = {item.ingredient_index: item for item in request.confirmed_measures}
    if any(index >= len(recipe.ingredients) or recipe.ingredients[index].exact_measure is not None for index in confirmed):
        raise HTTPException(422, "INVALID_CONFIRMED_SOURCE_MEASURE")
    unknown = [index for index, ingredient in enumerate(recipe.ingredients)
               if ingredient.exact_measure is None and index not in confirmed]
    if unknown:
        raise HTTPException(422, detail={"code": "SOURCE_MEASURES_REQUIRE_REVIEW", "ingredient_indexes": unknown})
    requirements = []
    for index, ingredient in enumerate(recipe.ingredients):
        measure = ingredient.exact_measure or confirmed[index]
        requirements.append(IngredientRequirementInput(display_name=ingredient.name,
            amount=measure.amount, unit=measure.unit, required=True))
    safety = evaluate_food_safety(db, household_id, FoodSafetyRequest(
        recipe_servings=request.confirmed_recipe_servings, servings=request.requested_servings,
        requirements=requirements,
    ))
    if safety.decision != "blocked":
        safety = safety.model_copy(update={
            "decision": "review_required",
            "reasons": sorted(set(safety.reasons) | {"source_recipe_requires_review"}),
        })
    ensure_meal_source_approvals(db, recipe, request.allow_broader_web)
    _require_member_and_consent(db, household_id, actor_id)
    return MealDBAssessmentRead(source=recipe, confirmed_recipe_servings=request.confirmed_recipe_servings,
                                requested_servings=request.requested_servings,
                                confirmed_measures=request.confirmed_measures, safety=safety)
