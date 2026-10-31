from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.ingredient import Ingredient, ProductIngredientMapping, ProductIngredientMappingTarget, ProductPackageFactor
from app.models.product import Product
from app.schemas.ingredients import RecipeAvailabilityRequest
from app.services.recipe_availability import calculate_availability


def pantry(db, household, user, *, unit="g", default_unit="g", quantity=10, expiration=0, verified=True, factor=None):
    ingredient = Ingredient(canonical_name="test rice", normalized_name="test rice", default_unit=default_unit)
    product = Product(household_id=household.id, name="Rice", unit=unit)
    db.add_all([ingredient, product])
    db.flush()
    mapping = ProductIngredientMapping(household_id=household.id, product_id=product.id, version=1,
        mode="DIRECT", ingredient_id=ingredient.id, verification_status="VERIFIED" if verified else "UNVERIFIED",
        method="manual", unknown_composition=False, verified_by_user_id=user.id,
        verified_at=datetime.now(timezone.utc) if verified else None)
    db.add(mapping)
    db.flush()
    db.add(ProductIngredientMappingTarget(household_id=household.id, product_id=product.id,
        mapping_version=1, ingredient_id=ingredient.id))
    db.flush()
    if factor:
        db.add(ProductPackageFactor(household_id=household.id, product_id=product.id, mapping_version=1,
            ingredient_id=ingredient.id, inventory_unit=unit, ingredient_amount=factor[0], ingredient_unit=factor[1],
            source_reference="Explicit test package label", verified_by_user_id=user.id, verified_at=datetime.now(timezone.utc)))
    batch = InventoryBatch(household_id=household.id, product_id=product.id, original_quantity=quantity,
        remaining_quantity=quantity, expiration_date=None if expiration is None else household_today()+timedelta(days=expiration))
    db.add(batch)
    db.commit()
    return ingredient, batch


def request(ingredient, amount, unit, **kwargs):
    return RecipeAvailabilityRequest(recipe_servings=1, servings=kwargs.pop("servings", 1),
        requirements=[dict(ingredient_id=ingredient.id, amount=amount, unit=unit, **kwargs)])


@pytest.mark.parametrize("demand", range(1, 31))
def test_quantity_shortfalls_are_exact_and_preview_never_writes(db, auth_household, auth_user, demand):
    ingredient, batch = pantry(db, auth_household, auth_user)
    before = db.scalar(select(func.count()).select_from(InventoryBatch))
    req = request(ingredient, demand, "g")
    result = calculate_availability(db, auth_household.id, req)
    line = result.requirements[0]
    assert line.shortfall == max(Decimal(demand)-10, 0)
    assert line.status == ("full" if demand <= 10 else "partial")
    assert result == calculate_availability(db, auth_household.id, req)
    assert batch.remaining_quantity == 10
    assert not db.new and not db.dirty and not db.deleted
    assert db.scalar(select(func.count()).select_from(InventoryBatch)) == before


def test_package_factor_uses_curated_reporting_unit(db, auth_household, auth_user):
    ingredient, _ = pantry(db, auth_household, auth_user, unit="bag", default_unit="kg", quantity=2, factor=("500", "g"))
    line = calculate_availability(db, auth_household.id, request(ingredient, 1, "kg")).requirements[0]
    assert line.available_amount == Decimal("1")
    assert line.unit == "kg" and line.status == "full"


@pytest.mark.parametrize("expiration,verified,unit,status", [
    (-1, True, "g", "missing"), (0, True, "g", "full"),
    (None, True, "g", "full"), (1, False, "g", "unknown"),
    (1, True, "pack", "unknown"),
])
def test_expiry_and_mapping_uncertainty(db, auth_household, auth_user, expiration, verified, unit, status):
    ingredient, batch = pantry(db, auth_household, auth_user, unit=unit, expiration=expiration, verified=verified)
    line = calculate_availability(db, auth_household.id, request(ingredient, 1, "g")).requirements[0]
    assert line.status == status
    if expiration is None:
        assert line.missing_expiry_batch_ids == [batch.id]


def test_duplicate_requirements_share_one_stock_pool(db, auth_household, auth_user):
    ingredient, _ = pantry(db, auth_household, auth_user)
    req = request(ingredient, 6, "g")
    req.requirements.append(req.requirements[0].model_copy())
    line = calculate_availability(db, auth_household.id, req).requirements[0]
    assert line.required_amount == 12 and line.shortfall == 2


def test_unknown_required_quantity_is_retained_and_never_becomes_full(db, auth_household, auth_user):
    ingredient, _ = pantry(db, auth_household, auth_user)
    req = request(ingredient, 1, "cup")
    req.requirements.append(req.requirements[0].model_copy(update={"unit": "g", "required": False}))
    result = calculate_availability(db, auth_household.id, req)
    assert result.overall_status == "unknown"
    assert len(result.requirements) == 2
    required, optional = result.requirements
    assert required.required is True and required.status == "unknown"
    assert required.required_amount is None and required.shortfall is None
    assert "unsupported_or_incompatible_requirement_unit" in required.unknown_reasons
    assert optional.status == "unknown"
    assert "required_demand_unknown_for_optional_coverage" in optional.unknown_reasons


@pytest.mark.parametrize("amounts,units,expected", [
    (["3"], ["g"], "1"),
    (["1", "1", "1"], ["g", "g", "g"], "1"),
    (["0.001", "2"], ["kg", "g"], "1"),
    (["9"], ["g"], "3"),
])
def test_fraction_servings_aggregate_before_division(db, auth_household, auth_user, amounts, units, expected):
    ingredient, _ = pantry(db, auth_household, auth_user, quantity=float(expected))
    req = RecipeAvailabilityRequest(recipe_servings=3, servings=1, requirements=[
        dict(ingredient_id=ingredient.id, amount=amount, unit=unit)
        for amount, unit in zip(amounts, units)
    ])
    line = calculate_availability(db, auth_household.id, req).requirements[0]
    assert line.required_amount == Decimal(expected)
    assert line.shortfall == 0 and line.status == "full"


def test_optional_demand_uses_remaining_stock_and_does_not_block(db, auth_household, auth_user):
    ingredient, _ = pantry(db, auth_household, auth_user)
    req = request(ingredient, 8, "g")
    req.requirements.append(req.requirements[0].model_copy(update={"amount": Decimal("5"), "required": False}))
    result = calculate_availability(db, auth_household.id, req)
    assert result.overall_status == "full"
    assert result.requirements[1].available_amount == 2
    assert result.requirements[1].shortfall == 3


def test_multiple_products_share_stock_in_expiry_order_without_foreign_batches(db, auth_household, auth_user):
    from app.models.household import Household

    ingredient, first = pantry(db, auth_household, auth_user, quantity=3, expiration=2)
    second_product = Product(household_id=auth_household.id, name="Other rice brand", unit="kg")
    other_household = Household(name="Private pantry", slug="private-pantry")
    db.add_all([second_product, other_household])
    db.flush()
    mapping = ProductIngredientMapping(household_id=auth_household.id, product_id=second_product.id,
        version=1, mode="DIRECT", ingredient_id=ingredient.id, verification_status="VERIFIED",
        method="Reviewed label", unknown_composition=False, verified_by_user_id=auth_user.id,
        verified_at=datetime.now(timezone.utc))
    db.add(mapping)
    db.flush()
    db.add(ProductIngredientMappingTarget(household_id=auth_household.id, product_id=second_product.id,
        mapping_version=1, ingredient_id=ingredient.id))
    second = InventoryBatch(household_id=auth_household.id, product_id=second_product.id,
        original_quantity=0.02, remaining_quantity=0.02, expiration_date=household_today())
    expired = InventoryBatch(household_id=auth_household.id, product_id=second_product.id,
        original_quantity=100, remaining_quantity=100, expiration_date=household_today()-timedelta(days=1))
    foreign_product = Product(household_id=other_household.id, name="Private rice", unit="g")
    db.add_all([second, expired, foreign_product])
    db.flush()
    db.add(InventoryBatch(household_id=other_household.id, product_id=foreign_product.id,
        original_quantity=500, remaining_quantity=500))
    db.commit()

    result = calculate_availability(db, auth_household.id, request(ingredient, 24, "g"))
    line = result.requirements[0]
    assert line.available_amount == 23 and line.shortfall == 1
    assert line.covered_batch_ids == [second.id, first.id]
    assert result.overall_status == "partial"
    assert first.remaining_quantity == 3 and second.remaining_quantity == Decimal("0.02")
    assert not db.new and not db.dirty and not db.deleted


def test_package_factor_becomes_unknown_after_inventory_unit_changes(db, auth_household, auth_user):
    ingredient, batch = pantry(db, auth_household, auth_user, unit="bag", factor=("500", "g"))
    product = db.get(Product, batch.product_id)
    product.unit = "box"
    db.commit()
    line = calculate_availability(db, auth_household.id, request(ingredient, 1, "g")).requirements[0]
    assert line.status == "unknown" and line.shortfall is None
    assert line.available_amount == 0
    assert "unknown_or_incompatible_product_unit" in line.unknown_reasons


def test_composite_requires_explicit_component_quantities(client, db, auth_household):
    from app.services.ingredient_matching import seed_ingredient_catalog_v1
    seed_ingredient_catalog_v1(db)
    db.commit()
    rice = client.get("/api/v1/ingredients/?query=bigas").json()["results"][0]["id"]
    salt = client.get("/api/v1/ingredients/?query=asin").json()["results"][0]["id"]
    product = client.post("/api/v1/products/", json={"name": "Rice mix", "unit": "pack"}).json()
    mapping = dict(mode="COMPOSITE", components=[{"ingredient_id": rice}, {"ingredient_id": salt}],
        verified=True, unknown_composition=False, method="Reviewed package label", package_factors=[dict(
            ingredient_id=rice, inventory_unit="pack", ingredient_amount=100, ingredient_unit="g", source_reference="100g rice per pack")])
    url = f"/api/v1/ingredients/products/{product['id']}/mapping"
    assert client.put(url, json=mapping).status_code == 200
    assert client.post("/api/v1/batches/", json={"product_id": product["id"], "original_quantity": 2}).status_code == 201
    result = client.post("/api/v1/ingredients/availability", json=dict(recipe_servings=2, servings=1,
        requirements=[dict(ingredient_id=rice, amount=300, unit="g"), dict(ingredient_id=salt, amount=2, unit="g")]))
    assert result.status_code == 200, result.text
    lines = {line["ingredient_id"]: line for line in result.json()["requirements"]}
    assert Decimal(lines[rice]["available_amount"]) == 200
    assert Decimal(lines[rice]["required_amount"]) == 150
    assert lines[rice]["status"] == "full"
    assert lines[salt]["status"] == "unknown"
    assert "verified_component_quantity_missing" in lines[salt]["unknown_reasons"]
    assert result.json()["overall_status"] == "unknown"
