from datetime import timedelta
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.household import HouseholdMembership
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.recipe import RecipeEvaluationInput
from app.schemas.recommendations import RecommendationRead, RecipeRecommendation
from app.services.preferences import read_profile
from app.services.ingredient_matching import resolve_ingredient
from app.services.recipes import evaluate_recipe, read_recipe
from app.services.recipe_sources import recipe_source_context


def recommend_recipes(db, household_id, actor_id, request):
    if request.diner_user_ids is not None:
        members = set(db.scalars(select(HouseholdMembership.user_id).join(User, User.id == HouseholdMembership.user_id)
            .where(HouseholdMembership.household_id == household_id, User.is_active.is_(True))).all())
        if not set(request.diner_user_ids) <= members:
            raise HTTPException(403, "Diners must be active household members")
    personal = read_profile(db, household_id, actor_id).preferences
    shared = read_profile(db, household_id, None).preferences
    servings = request.servings if request.servings is not None else personal.servings
    cuisine_preferences = {value.casefold() for value in personal.preferred_cuisines + shared.preferred_cuisines}
    dislikes = {value.casefold() for value in personal.dislikes + shared.dislikes}
    disliked_ids = {match.ingredient.id for name in sorted(dislikes)
        if (match := resolve_ingredient(db, display_name=name)).ingredient is not None}
    times = [value for value in (personal.max_cook_minutes, shared.max_cook_minutes, request.max_total_minutes) if value is not None]
    max_minutes = min(times) if times else None
    equipment = request.available_equipment
    if equipment is None and (personal.equipment or shared.equipment):
        equipment = personal.equipment + shared.equipment
    equipment_set = {item.casefold() for item in equipment} if equipment is not None else None
    statement = select(Recipe).where(Recipe.household_id == household_id, Recipe.is_active.is_(True))
    if request.query:
        statement = statement.where(Recipe.title.icontains(request.query, autoescape=True))
    if request.cuisine:
        statement = statement.where(func.lower(Recipe.cuisine) == request.cuisine.lower())
    rows = db.scalars(statement.order_by(Recipe.id).offset(request.candidate_offset).limit(request.candidate_limit + 1)).all()
    has_more = len(rows) > request.candidate_limit
    evaluated, blocked, review, unknown = 0, 0, 0, 0
    ranked = []
    today = household_today()
    for row in rows[:request.candidate_limit]:
        recipe = read_recipe(db, row)
        total_minutes = recipe.prep_minutes + recipe.cook_minutes
        if request.ph_region and request.ph_region not in recipe.ph_regions:
            continue
        if request.course and request.course not in recipe.course_categories:
            continue
        if max_minutes is not None and total_minutes > max_minutes:
            continue
        if equipment_set is not None and not {item.casefold() for item in recipe.equipment} <= equipment_set:
            continue
        result = evaluate_recipe(db, household_id, recipe.id, RecipeEvaluationInput(
            expected_recipe_revision=recipe.revision, servings=servings, diner_user_ids=request.diner_user_ids)).result
        evaluated += 1
        if result.decision == "blocked":
            blocked += 1
            continue
        if result.decision != "eligible":
            review += 1
            continue
        required = [line for line in result.availability.requirements if line.required]
        if any(line.status == "unknown" for line in required):
            unknown += 1
            continue
        missing = sum(1 for line in required if line.shortfall and line.shortfall > 0)
        if request.mode == "cook_now" and result.availability.overall_status != "full":
            continue
        if request.mode == "almost_there" and not 0 < missing <= request.max_missing_ingredients:
            continue
        fractions = [min(line.available_amount, line.required_amount) / line.required_amount for line in required]
        coverage = sum(fractions, Decimal("0")) / len(fractions) if fractions else Decimal("1")
        batch_ids = {batch for line in required for batch in line.covered_batch_ids}
        near_expiry = len(db.scalars(select(InventoryBatch.id).where(InventoryBatch.household_id == household_id,
            InventoryBatch.id.in_(batch_ids), InventoryBatch.expiration_date >= today,
            InventoryBatch.expiration_date <= today + timedelta(days=request.expiry_window_days))).all())
        preference_match = recipe.cuisine.casefold() in cuisine_preferences
        disliked = sum(1 for ingredient in recipe.ingredients
            if ingredient.display_name.casefold() in dislikes or ingredient.ingredient_id in disliked_ids)
        _, source_rank, source_reference = recipe_source_context(db, household_id, recipe.id)
        pantry_key = (-coverage, missing, -near_expiry, -source_rank, -int(preference_match), disliked, total_minutes)
        key = (total_minutes, *pantry_key) if request.priority == "quick" else (
            (-int(preference_match), *pantry_key) if request.priority == "preferred_cuisine" else pantry_key)
        ranked.append(((*key, recipe.title.casefold(), recipe.id), RecipeRecommendation(recipe=recipe, evaluation=result,
            coverage=coverage, missing_ingredient_count=missing, near_expiry_batch_count=near_expiry,
            preference_match=preference_match, source_reference=source_reference)))
    ranked.sort(key=lambda item: item[0])
    return RecommendationRead(items=[item for _, item in ranked[:request.limit]], candidates_evaluated=evaluated,
        has_more_candidates=has_more, excluded_blocked=blocked, excluded_review_required=review, excluded_unknown_quantities=unknown)
