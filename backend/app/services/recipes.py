from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.recipe import Recipe, RecipeIngredient, RecipeRevision, SavedRecipe
from app.schemas.food_safety import FoodSafetyRequest
from app.schemas.ingredients import IngredientRequirementInput
from app.schemas.recipe import (RecipeEvaluationInput, RecipeEvaluationRead, RecipeIngredientRead,
    RecipeRead, RecipeWrite, SavedRecipeRead, SaveRecipeInput)
from app.services.allergen_policy import evaluate_food_safety
from app.services.ingredient_matching import resolve_ingredient


def get_recipe(db, household_id, recipe_id, *, lock=False):
    statement = select(Recipe).where(Recipe.household_id == household_id, Recipe.id == recipe_id)
    if lock:
        statement = statement.with_for_update()
    recipe = db.scalar(statement.execution_options(populate_existing=True))
    if recipe is None:
        raise HTTPException(404, "Recipe not found")
    return recipe


def _lock_member(db, household_id, actor_id):
    db.scalar(select(Household.id).where(Household.id == household_id).with_for_update())
    if db.scalar(select(HouseholdMembership.id).where(HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id)) is None:
        raise HTTPException(403, "Household membership is required")


def read_recipe(db, recipe):
    ingredients = db.scalars(select(RecipeIngredient).where(RecipeIngredient.household_id == recipe.household_id,
        RecipeIngredient.recipe_id == recipe.id).order_by(RecipeIngredient.position)).all()
    return RecipeRead(id=recipe.id, revision=recipe.revision, is_active=recipe.is_active,
        title=recipe.title, cuisine=recipe.cuisine, **recipe.content,
        ingredients=[RecipeIngredientRead(**{field: getattr(item, field)
            for field in RecipeIngredientRead.model_fields}) for item in ingredients])


def read_revision(db, household_id, recipe_id, revision):
    get_recipe(db, household_id, recipe_id)
    record = db.scalar(select(RecipeRevision).where(RecipeRevision.household_id == household_id,
        RecipeRevision.recipe_id == recipe_id, RecipeRevision.revision == revision))
    if record is None:
        raise HTTPException(404, "Recipe revision not found")
    return RecipeRead.model_validate(record.snapshot)


def _ingredients(db, request):
    result = []
    for position, item in enumerate(request.ingredients):
        resolution = resolve_ingredient(db, ingredient_id=item.ingredient_id, display_name=item.display_name)
        if item.ingredient_id is not None and resolution.ingredient is None:
            raise HTTPException(422, "Recipe references an unavailable ingredient")
        for option in item.substitution_options:
            if option.ingredient_id is not None and resolve_ingredient(db, ingredient_id=option.ingredient_id).ingredient is None:
                raise HTTPException(422, "Substitution references an unavailable ingredient")
        result.append(dict(position=position, ingredient_id=resolution.ingredient.id if resolution.ingredient else None,
            display_name=item.display_name or resolution.ingredient.canonical_name, amount=item.amount,
            unit=item.unit, required=item.required, preparation=item.preparation,
            substitution_options=[option.model_dump(mode="json") for option in item.substitution_options]))
    return result


def _snapshot(db, recipe):
    db.flush()
    read = read_recipe(db, recipe)
    db.add(RecipeRevision(household_id=recipe.household_id, recipe_id=recipe.id,
        revision=recipe.revision, snapshot=read.model_dump(mode="json")))
    return read


def write_recipe(db: Session, household_id: int, actor_id: int, request: RecipeWrite, recipe_id=None):
    _lock_member(db, household_id, actor_id)
    recipe = get_recipe(db, household_id, recipe_id, lock=True) if recipe_id is not None else None
    if request.expected_revision != (recipe.revision if recipe else None):
        raise HTTPException(409, "RECIPE_REVISION_CONFLICT")
    if recipe and not recipe.is_active:
        raise HTTPException(409, "RECIPE_ARCHIVED")
    ingredients = _ingredients(db, request)
    content = request.model_dump(mode="json", exclude={"title", "cuisine", "ingredients", "expected_revision"})
    if recipe is None:
        recipe = Recipe(household_id=household_id, title=request.title, cuisine=request.cuisine,
            content=content, revision=1, is_active=True, created_by_user_id=actor_id)
        db.add(recipe)
        db.flush()
    else:
        recipe.revision += 1
        recipe.title, recipe.cuisine, recipe.content = request.title, request.cuisine, content
        db.execute(delete(RecipeIngredient).where(RecipeIngredient.household_id == household_id,
            RecipeIngredient.recipe_id == recipe.id))
    for ingredient in ingredients:
        db.add(RecipeIngredient(household_id=household_id, recipe_id=recipe.id, **ingredient))
    result = _snapshot(db, recipe)
    db.commit()
    return result


def archive_recipe(db, household_id, actor_id, recipe_id, expected_revision):
    _lock_member(db, household_id, actor_id)
    recipe = get_recipe(db, household_id, recipe_id, lock=True)
    if recipe.revision != expected_revision or not recipe.is_active:
        raise HTTPException(409, "RECIPE_REVISION_CONFLICT")
    recipe.is_active = False
    recipe.revision += 1
    _snapshot(db, recipe)
    db.commit()


def evaluate_recipe(db, household_id, recipe_id, request: RecipeEvaluationInput):
    recipe = get_recipe(db, household_id, recipe_id)
    if recipe.revision != request.expected_recipe_revision or not recipe.is_active:
        raise HTTPException(409, "RECIPE_REVISION_CONFLICT")
    record = read_recipe(db, recipe)
    if any(item.requirement_index >= len(record.ingredients) for item in request.substitutions):
        raise HTTPException(422, "Substitution references an absent recipe line")
    requirements = [IngredientRequirementInput(ingredient_id=item.ingredient_id,
        display_name=None if item.ingredient_id else item.display_name, amount=item.amount, unit=item.unit, required=item.required)
        for item in record.ingredients]
    evaluation = FoodSafetyRequest(recipe_servings=record.servings, servings=request.servings,
        diner_user_ids=request.diner_user_ids, requirements=requirements, substitutions=request.substitutions)
    result = evaluate_food_safety(db, household_id, evaluation)
    from app.services.recipe_sources import recipe_source_context
    source_allowed, _, _ = recipe_source_context(db, household_id, recipe.id)
    if record.content_permission == "NOT_DECLARED" or not source_allowed:
        if result.decision != "blocked":
            result.decision = "review_required"
        result.reasons = sorted(set(result.reasons) | ({"recipe_content_permission_not_declared"}
            if record.content_permission == "NOT_DECLARED" else set()) | ({"recipe_source_unavailable"} if not source_allowed else set()))
    return RecipeEvaluationRead(recipe_id=recipe.id, recipe_revision=recipe.revision, result=result)


def _saved(db, household_id, member_id, recipe_id):
    return db.scalar(select(SavedRecipe).where(SavedRecipe.household_id == household_id,
        SavedRecipe.member_user_id == member_id, SavedRecipe.recipe_id == recipe_id)
        .execution_options(populate_existing=True))


def saved_read(saved):
    return SavedRecipeRead(**{field: getattr(saved, field) for field in SavedRecipeRead.model_fields})


def read_saved(db, household_id, member_id, recipe_id):
    get_recipe(db, household_id, recipe_id)
    saved = _saved(db, household_id, member_id, recipe_id)
    if saved is None:
        raise HTTPException(404, "Saved recipe not found")
    return saved_read(saved)


def save_recipe(db, household_id, member_id, recipe_id, request: SaveRecipeInput):
    _lock_member(db, household_id, member_id)
    recipe = get_recipe(db, household_id, recipe_id, lock=True)
    if recipe.revision != request.expected_recipe_revision or not recipe.is_active:
        raise HTTPException(409, "RECIPE_REVISION_CONFLICT")
    saved = _saved(db, household_id, member_id, recipe_id)
    if request.expected_revision != (saved.revision if saved else None):
        raise HTTPException(409, "SAVED_RECIPE_REVISION_CONFLICT")
    if saved is None:
        saved = SavedRecipe(household_id=household_id, member_user_id=member_id, recipe_id=recipe_id, revision=1)
        db.add(saved)
    else:
        saved.revision += 1
    saved.recipe_revision = recipe.revision
    saved.is_saved, saved.favorite, saved.servings, saved.notes = True, request.favorite, request.servings, request.notes
    db.commit()
    return saved_read(saved)


def remove_saved(db, household_id, member_id, recipe_id, expected_revision):
    _lock_member(db, household_id, member_id)
    get_recipe(db, household_id, recipe_id)
    saved = _saved(db, household_id, member_id, recipe_id)
    if saved is None or saved.revision != expected_revision or not saved.is_saved:
        raise HTTPException(409, "SAVED_RECIPE_REVISION_CONFLICT")
    saved.is_saved, saved.favorite, saved.servings, saved.notes = False, False, None, None
    saved.revision += 1
    db.commit()
