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
