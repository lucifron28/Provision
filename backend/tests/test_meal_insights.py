from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.household import Household
from app.models.product import Product
from app.models.session import GrocerySession, GrocerySessionStatus
from test_food_safety import catalog
from test_recipes import create
from test_product_labels import stock


def test_recipe_budget_reports_historical_price_basis_and_serving_scale(client, db, catalog, auth_household):
    product, _ = stock(client, catalog, name="rice")
    batch = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == product["id"]))
    session = GrocerySession(household_id=auth_household.id, store_name="Historical test store",
        status=GrocerySessionStatus.COMPLETED)
    db.add(session)
    db.flush()
    batch.grocery_session_id = session.id
    batch.unit_price = Decimal("0.25")
    batch.purchased_at = datetime.now(timezone.utc)-timedelta(days=30)
    db.commit()
    recipe = create(client, ingredients=[dict(display_name="rice", amount=100, unit="g")])
    response = client.post(f"/api/v1/meal-insights/recipes/{recipe['id']}/budget",
        json=dict(expected_recipe_revision=1, servings=1))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["complete"] is True and result["price_basis"] == "historical_purchase_prices"
    assert Decimal(result["estimated_total_php"]) == Decimal("12.50")
    assert result["lines"][0]["store_name"] == "Historical test store"
    assert result["lines"][0]["price_batch_id"] == batch.id
    assert response.headers["cache-control"] == "no-store"
    assert batch.remaining_quantity == 10


def test_budget_missing_price_does_not_become_a_zero_total(client, catalog):
    recipe = create(client)
    response = client.post(f"/api/v1/meal-insights/recipes/{recipe['id']}/budget",
        json=dict(expected_recipe_revision=1, servings=2))
    assert response.status_code == 200
    result = response.json()
    assert result["complete"] is False and result["estimated_total_php"] is None
    assert result["estimated_within_budget"] is None
    assert all(line["estimated_cost_php"] is None for line in result["lines"])


def test_budget_does_not_infer_package_conversion_and_ignores_future_price(client, db, catalog):
    product, mapping = stock(client, catalog, name="rice")
    batch = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == product["id"]))
    batch.unit_price = Decimal("50")
    batch.purchased_at = datetime.now(timezone.utc)+timedelta(days=30)
    db.commit()
    recipe = create(client, ingredients=[dict(display_name="rice", amount=100, unit="g")])
    url = f"/api/v1/meal-insights/recipes/{recipe['id']}/budget"
    request = dict(expected_recipe_revision=1, servings=2)
    assert client.post(url, json=request).json()["estimated_total_php"] is None
    batch.purchased_at = datetime.now(timezone.utc)-timedelta(days=1)
    db.get(Product, product["id"]).unit = "pack"
    db.commit()
    assert client.post(url, json=request).json()["estimated_total_php"] is None


def test_budget_uses_explicit_package_factor_and_respects_budget_goal(client, db, catalog):
    product, mapping = stock(client, catalog, name="rice")
    product = client.patch(f"/api/v1/products/{product['id']}", json=dict(unit="bag")).json()
    mapping.update(expected_version=1, package_factors=[dict(ingredient_id=catalog["rice"].id,
        inventory_unit="bag", ingredient_amount=500, ingredient_unit="g", source_reference="500g label")])
    assert client.put(f"/api/v1/ingredients/products/{product['id']}/mapping", json=mapping).status_code == 200
    receipt = client.post("/api/v1/batches/", json=dict(product_id=product["id"], original_quantity=1, unit_price="25"))
    assert receipt.status_code == 201
    batch = db.get(InventoryBatch, receipt.json()["id"])
    assert client.put("/api/v1/food-profiles/me", json=dict(allergy_status="NONE_DECLARED",
        preferences=dict(meal_budget_php="10"))).status_code == 200
    recipe = create(client, ingredients=[dict(display_name="rice", amount=100, unit="g")])
    url = f"/api/v1/meal-insights/recipes/{recipe['id']}/budget"
    response = client.post(url, json=dict(expected_recipe_revision=1, servings=2))
    assert response.status_code == 200, response.text
    assert Decimal(response.json()["estimated_total_php"]) == 5
    assert response.json()["estimated_within_budget"] is True
    batch.unit_price = Decimal("0")
    db.commit()
    result = client.post(url, json=dict(expected_recipe_revision=1, servings=2)).json()
    assert result["complete"] is True and Decimal(result["estimated_total_php"]) == 0


def test_older_price_is_unknown_after_product_unit_changes(client, db, catalog):
    product, _ = stock(client, catalog, name="rice")
    batch = db.scalar(select(InventoryBatch).where(InventoryBatch.product_id == product["id"]))
    batch.unit_price = Decimal("0.25")
    db.commit()
    recipe = create(client, ingredients=[dict(display_name="rice", amount=100, unit="g")])
    url = f"/api/v1/meal-insights/recipes/{recipe['id']}/budget"
    request = dict(expected_recipe_revision=1, servings=2)
    assert client.post(url, json=request).json()["complete"] is True
    assert client.patch(f"/api/v1/products/{product['id']}", json=dict(unit="kg")).status_code == 200
    result = client.post(url, json=request).json()
    assert result["complete"] is False and result["estimated_total_php"] is None


def test_waste_interval_excludes_foreign_and_end_boundary_events(client, db, auth_household):
    at = datetime.now(timezone.utc)
    foreign = Household(name="Foreign", slug="waste-private")
    db.add(foreign)
    db.flush()
    for household, occurred in [(foreign, at-timedelta(seconds=1)), (auth_household, at)]:
        product = Product(name="Private" if household is foreign else "Boundary", unit="count", household_id=household.id)
        db.add(product)
        db.flush()
        batch = InventoryBatch(household_id=household.id, product_id=product.id,
            original_quantity=1, remaining_quantity=0, unit_price=10)
        db.add(batch)
        db.flush()
        db.add(InventoryEvent(batch_id=batch.id, event_type=EventType.DISCARDED, quantity=1, occurred_at=occurred))
    db.commit()
    response = client.post("/api/v1/meal-insights/waste", json=dict(
        start=(at-timedelta(days=1)).isoformat(), end=at.isoformat()))
    assert response.status_code == 200
    assert response.json()["event_count"] == 0 and "Private" not in response.text


def test_waste_price_and_unit_remain_unknown_after_metadata_edit(client, db, auth_household):
    at = datetime.now(timezone.utc)
    product = Product(name="Edited product", unit="g", household_id=auth_household.id)
    db.add(product)
    db.flush()
    batch = InventoryBatch(household_id=auth_household.id, product_id=product.id,
        original_quantity=10, remaining_quantity=0, unit_price=Decimal("0.25"))
    db.add(batch)
    db.flush()
    db.add(InventoryEvent(batch_id=batch.id, event_type=EventType.DISCARDED, quantity=10, occurred_at=at))
    db.commit()
    assert client.patch(f"/api/v1/products/{product.id}", json=dict(unit="kg")).status_code == 200
    result = client.post("/api/v1/meal-insights/waste", json=dict(
        start=(at-timedelta(days=1)).isoformat(), end=(at+timedelta(days=1)).isoformat())).json()
    assert result["unpriced_event_count"] == 1 and result["estimated_total_loss_php"] is None
    assert result["events"][0]["unit"] is None
    assert result["events"][0]["cost_unknown_reason"] == "purchase_unit_history_unknown"


def test_waste_reports_only_recorded_events_and_keeps_units_separate(client, db, auth_household):
    now = datetime.now(timezone.utc)
    records = []
    for name, unit, price in [("Milk", "ml", Decimal("2")), ("Rice", "g", None)]:
        product = Product(name=name, unit=unit, household_id=auth_household.id)
        db.add(product)
        db.flush()
        batch = InventoryBatch(household_id=auth_household.id, product_id=product.id,
            original_quantity=10, remaining_quantity=10, unit_price=price)
        db.add(batch)
        db.flush()
        records.append(batch)
        db.add(InventoryEvent(batch_id=batch.id, event_type=EventType.DISCARDED, quantity=2, occurred_at=now))
        db.add(InventoryEvent(batch_id=batch.id, event_type=EventType.CONSUMED, quantity=1, occurred_at=now))
        db.add(InventoryEvent(batch_id=batch.id, event_type=EventType.EXPIRED, quantity=1, occurred_at=now-timedelta(days=4)))
    db.commit()
    request = dict(start=(now-timedelta(days=1)).isoformat(), end=(now+timedelta(days=1)).isoformat())
    response = client.post("/api/v1/meal-insights/waste", json=request)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["event_count"] == 2 and result["unpriced_event_count"] == 1
    assert result["estimated_total_loss_php"] is None
    assert Decimal(result["known_loss_subtotal_php"]) == 4
    assert {line["unit"]: Decimal(line["quantity"]) for line in result["quantities_by_unit"]} == {"g": 2, "ml": 2}
    assert all(batch.remaining_quantity == 10 for batch in records)


@pytest.mark.parametrize("start,end", [
    ("2026-01-01T00:00:00", "2026-01-02T00:00:00Z"),
    ("2026-01-02T00:00:00Z", "2026-01-01T00:00:00Z"),
    ("2026-01-01T00:00:00Z", "2027-01-03T00:00:00Z"),
])
def test_waste_periods_are_aware_ordered_and_bounded(client, start, end):
    assert client.post("/api/v1/meal-insights/waste", json=dict(start=start, end=end)).status_code == 422


def test_insights_reject_foreign_recipe(client, db):
    from app.models.recipe import Recipe
    foreign = Household(name="Other", slug="insights-other")
    db.add(foreign)
    db.flush()
    recipe = Recipe(household_id=foreign.id, title="Other recipe", cuisine="Filipino", revision=1, content={}, is_active=True)
    db.add(recipe)
    db.commit()
    url = f"/api/v1/meal-insights/recipes/{recipe.id}/budget"
    assert client.post(url, json=dict(expected_recipe_revision=1, servings=2)).status_code == 404


def test_insights_require_authentication(unauthed_client):
    assert unauthed_client.post("/api/v1/meal-insights/recipes/1/budget",
        json=dict(expected_recipe_revision=1, servings=2)).status_code == 401
