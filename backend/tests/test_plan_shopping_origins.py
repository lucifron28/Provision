from datetime import date

from app.models.shopping import ShoppingListItem
from app.schemas.meal_plan import MealPlanReplaceRequest
from app.schemas.recipe import RecipeWrite
from app.services.meal_plans import replace_week
from app.services.recipes import write_recipe


def test_manual_recipe_origin_edit_replaces_plan_origin_without_losing_notes(
    client, db, auth_household, auth_user
):
    plan = replace_week(db, auth_household.id, auth_user.id, date(2026, 10, 26),
        MealPlanReplaceRequest(entries=[]))
    recipe = write_recipe(db, auth_household.id, auth_user.id, RecipeWrite(
        title="Household recipe", servings=1, instructions=["Synthetic origin fixture."],
        content_permission="OWNED_OR_PERMISSION_GRANTED",
        ingredients=[dict(display_name="garlic", amount=1, unit="g")]))
    item = ShoppingListItem(household_id=auth_household.id, name="Garlic", quantity=2,
        unit="g", notes="Keep my brand", origin_plan_id=plan.id, origin_plan_revision=plan.revision)
    db.add(item)
    db.commit()

    ordinary_edit = client.patch(f"/api/v1/shopping-list/{item.id}", json={"quantity": "3"})
    assert ordinary_edit.status_code == 200, ordinary_edit.text
    assert ordinary_edit.json()["origin_plan_id"] == plan.id
    response = client.patch(f"/api/v1/shopping-list/{item.id}", json={"origin_recipe_id": recipe.id})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["origin_recipe_id"] == recipe.id
    assert result["origin_recipe_revision"] == recipe.revision
    assert result["origin_plan_id"] is None and result["origin_plan_revision"] is None
    assert result["notes"] == "Keep my brand"
    assert result["quantity"] == 3
