from decimal import Decimal

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.models.batch import InventoryBatch
from app.models.recipe_source import RecipeSource
from app.models.shopping import ShoppingListItem
from app.schemas.themealdb import MealDBAssessmentInput
from app.services.themealdb_assessment import assess_reviewed_meal
from app.services.themealdb_recipe import validate_reviewed_meal
from app.services.themealdb_reviewed import ReviewedMeal
from test_deepseek_discovery import _grant
from test_food_safety import catalog, declare
from test_recipe_shopping import add_pantry, ready_profiles, setup_ingredient
from test_themealdb_reviewed import Budget, Client, add_api_source, add_origin


def record(measure="10 g"):
    return {"idMeal": "123", "strMeal": "Garlic dish", "strIngredient1": "garlic",
            "strMeasure1": measure, "strInstructions": "Cook the garlic.",
            "strSource": "https://recipes.publisher.example.com/garlic"}


def assessment(db, user, household, *, measure="10 g", servings=1):
    return assess_reviewed_meal(db, household.id, user.id, "123",
        MealDBAssessmentInput(source_digest=digest(db, record(measure)), confirmed_recipe_servings=1, requested_servings=servings),
        client=Client(record(measure)), budget=Budget())


def setup_sources(db, user, household):
    _grant(db, user, household)
    add_api_source(db)
    add_origin(db)
    db.commit()


def digest(db, data):
    api = db.scalar(select(RecipeSource).where(RecipeSource.canonical_host == "www.themealdb.com"))
    origin = db.scalar(select(RecipeSource).where(RecipeSource.canonical_host == "recipes.publisher.example.com"))
    return validate_reviewed_meal(ReviewedMeal(data, api.id, origin.id, api.revision, origin.revision)).content_digest


def test_source_quantities_assess_stock_without_mutation(db, auth_user, auth_household):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    _, batch = add_pantry(db, auth_household, auth_user, ingredient, 8)
    setup_sources(db, auth_user, auth_household)
    result = assessment(db, auth_user, auth_household)
    line = result.safety.availability.requirements[0]
    assert result.servings_basis == "user_confirmed"
    assert result.safety.decision == "review_required"
    assert "source_recipe_requires_review" in result.safety.reasons
    assert (line.required_amount, line.available_amount, line.shortfall) == (Decimal("10"), Decimal("8"), Decimal("2"))
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0


def test_user_confirmed_servings_scale_only_source_amounts(db, auth_user, auth_household):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    add_pantry(db, auth_household, auth_user, ingredient, 8)
    setup_sources(db, auth_user, auth_household)
    line = assessment(db, auth_user, auth_household, servings=2).safety.availability.requirements[0]
    assert (line.required_amount, line.available_amount, line.shortfall) == (Decimal("20"), Decimal("8"), Decimal("12"))


def test_assessment_blocks_known_source_allergen(client, db, catalog, auth_user, auth_household):
    declare(client, "milk")
    setup_sources(db, auth_user, auth_household)
    milk = {**record("10 ml"), "strIngredient1": "milk"}
    result = assess_reviewed_meal(db, auth_household.id, auth_user.id, "123",
        MealDBAssessmentInput(source_digest=digest(db, milk), confirmed_recipe_servings=1, requested_servings=1), client=Client(milk), budget=Budget())
    assert result.safety.decision == "blocked"
    assert "allergen_conflict" in result.safety.reasons


def test_revocation_during_assessment_discards_result(db, auth_user, auth_household, monkeypatch):
    import app.services.themealdb_assessment as service

    setup_sources(db, auth_user, auth_household)
    source = db.scalar(select(RecipeSource).where(RecipeSource.canonical_host == "www.themealdb.com"))
    original_evaluate = service.evaluate_food_safety
    def revoke_after_evaluation(*args):
        result = original_evaluate(*args)
        source.policy = {**source.policy, "enabled": False}
        db.flush()
        return result
    monkeypatch.setattr(service, "evaluate_food_safety", revoke_after_evaluation)
    with pytest.raises(HTTPException):
        assessment(db, auth_user, auth_household)


@pytest.mark.parametrize("measure", ["to taste", "1 cup", "1/2 g", ""])
def test_unknown_source_quantities_never_become_stock_amounts(db, auth_user, auth_household, measure):
    setup_sources(db, auth_user, auth_household)
    with pytest.raises(HTTPException) as error:
        assessment(db, auth_user, auth_household, measure=measure)
    assert error.value.detail == {"code": "SOURCE_MEASURES_REQUIRE_REVIEW", "ingredient_indexes": [0]}


def test_user_can_confirm_an_unknown_measure_without_changing_the_source(db, auth_user, auth_household):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    _, batch = add_pantry(db, auth_household, auth_user, ingredient, 8)
    setup_sources(db, auth_user, auth_household)
    request = MealDBAssessmentInput(source_digest=digest(db, record("to taste")), confirmed_recipe_servings=1, requested_servings=1,
                                    confirmed_measures=[{"ingredient_index": 0, "amount": "10", "unit": "g"}])
    result = assess_reviewed_meal(db, auth_household.id, auth_user.id, "123", request,
                                  client=Client(record("to taste")), budget=Budget())
    assert result.source.ingredients[0].source_measure == "to taste"
    assert result.source.ingredients[0].exact_measure is None
    assert result.confirmed_measures[0].amount == Decimal("10")
    assert result.safety.availability.requirements[0].shortfall == Decimal("2")
    db.expire_all()
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8")


@pytest.mark.parametrize("index,measure", [(0, "10 g"), (1, "to taste")])
def test_confirmed_measure_cannot_replace_exact_or_missing_ingredient(db, auth_user, auth_household, index, measure):
    setup_sources(db, auth_user, auth_household)
    request = MealDBAssessmentInput(source_digest=digest(db, record(measure)), confirmed_recipe_servings=1, requested_servings=1,
                                    confirmed_measures=[{"ingredient_index": index, "amount": 5, "unit": "g"}])
    with pytest.raises(HTTPException) as error:
        assess_reviewed_meal(db, auth_household.id, auth_user.id, "123", request,
                             client=Client(record(measure)), budget=Budget())
    assert error.value.detail == "INVALID_CONFIRMED_SOURCE_MEASURE"


def test_duplicate_and_invalid_confirmed_measures_are_rejected():
    item = {"ingredient_index": 0, "amount": 1, "unit": "g"}
    with pytest.raises(ValidationError):
        MealDBAssessmentInput(source_digest="a" * 64, confirmed_recipe_servings=1, requested_servings=1, confirmed_measures=[item, item])
    with pytest.raises(ValidationError):
        MealDBAssessmentInput(source_digest="a" * 64, confirmed_recipe_servings=1, requested_servings=1,
                              confirmed_measures=[{"ingredient_index": 0, "amount": 1, "unit": "cup"}])


def test_assessment_endpoint_requires_explicit_serving_basis(client, db, auth_user, auth_household):
    from app.api.v1.endpoints.recipe_sources import get_mealdb_budget, get_mealdb_client
    from app.main import app

    setup_sources(db, auth_user, auth_household)
    app.dependency_overrides[get_mealdb_client] = lambda: Client(record())
    app.dependency_overrides[get_mealdb_budget] = lambda: Budget()
    preview = client.post("/api/v1/recipe-sources/mealdb/123/preview", json={})
    assert preview.status_code == 200, preview.text
    source_digest = preview.json()["source"]["content_digest"]
    missing = client.post("/api/v1/recipe-sources/mealdb/123/assess", json={"source_digest": source_digest, "requested_servings": 1})
    assert missing.status_code == 422
    response = client.post("/api/v1/recipe-sources/mealdb/123/assess",
                           json={"source_digest": source_digest, "confirmed_recipe_servings": 1, "requested_servings": 1})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["servings_basis"] == "user_confirmed"


def test_assessment_endpoint_records_user_confirmed_measure(client, db, auth_user, auth_household):
    from app.api.v1.endpoints.recipe_sources import get_mealdb_budget, get_mealdb_client
    from app.main import app

    setup_sources(db, auth_user, auth_household)
    app.dependency_overrides[get_mealdb_client] = lambda: Client(record("to taste"))
    app.dependency_overrides[get_mealdb_budget] = lambda: Budget()
    preview = client.post("/api/v1/recipe-sources/mealdb/123/preview", json={})
    assert preview.status_code == 200, preview.text
    response = client.post("/api/v1/recipe-sources/mealdb/123/assess", json={
        "source_digest": preview.json()["source"]["content_digest"],
        "confirmed_recipe_servings": 1, "requested_servings": 1,
        "confirmed_measures": [{"ingredient_index": 0, "amount": "10", "unit": "g"}],
    })
    assert response.status_code == 200, response.text
    assert response.json()["source"]["ingredients"][0]["source_measure"] == "to taste"
    assert response.json()["confirmed_measures"][0]["amount"] == "10"


def test_changed_source_invalidates_user_confirmation(db, auth_user, auth_household):
    setup_sources(db, auth_user, auth_household)
    previous_digest = digest(db, record("to taste"))
    request = MealDBAssessmentInput(source_digest=previous_digest, confirmed_recipe_servings=1, requested_servings=1,
                                    confirmed_measures=[{"ingredient_index": 0, "amount": 10, "unit": "g"}])
    with pytest.raises(HTTPException) as error:
        assess_reviewed_meal(db, auth_household.id, auth_user.id, "123", request,
                             client=Client(record("1 cup")), budget=Budget())
    assert error.value.status_code == 409 and error.value.detail == "SOURCE_RECIPE_CHANGED"
