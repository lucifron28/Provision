from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.household import Household
from app.models.ingredient import (
    Ingredient,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
)
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.shopping import ShoppingListItem
from app.services.product_labels import product_fingerprint
from test_recipe_shopping import (
    confirm_payload,
    local_client,
    make_recipe,
    preview,
    ready_profiles,
    setup_ingredient,
)


def _add_reviewed_product_and_batches(
    db, household, user, ingredient, *, name: str, batch_count: int
):
    product = Product(household_id=household.id, name=name, unit="g")
    db.add(product)
    db.flush()

    now = datetime.now(timezone.utc)
    mapping = ProductIngredientMapping(
        household_id=household.id,
        product_id=product.id,
        version=1,
        is_current=True,
        mode="DIRECT",
        ingredient_id=ingredient.id,
        verification_status="VERIFIED",
        method="Explicit synthetic test mapping",
        verified_by_user_id=user.id,
        verified_at=now,
        unknown_composition=False,
    )
    db.add(mapping)
    db.flush()
    db.add(
        ProductIngredientMappingTarget(
            household_id=household.id,
            product_id=product.id,
            mapping_version=1,
            ingredient_id=ingredient.id,
        )
    )
    db.add(
        ProductAllergenLabel(
            household_id=household.id,
            product_id=product.id,
            mapping_version=1,
            revision=1,
            is_current=True,
            product_fingerprint=product_fingerprint(product),
            declared_allergens=[],
            possible_allergens=[],
            custom_allergens=[],
            composition_known=True,
            source_reference="Explicit synthetic test label",
            reviewed_by_user_id=user.id,
            reviewed_at=now,
        )
    )

    batches = [
        InventoryBatch(
            household_id=household.id,
            product_id=product.id,
            original_quantity=Decimal("1"),
            remaining_quantity=Decimal("1"),
            expiration_date=household_today() + timedelta(days=30),
        )
        for _ in range(batch_count)
    ]
    db.add_all(batches)
    db.flush()
    return product, batches


def _shopping_state(db):
    rows = db.scalars(
        select(ShoppingListItem)
        .order_by(ShoppingListItem.household_id, ShoppingListItem.id)
        .execution_options(populate_existing=True)
    ).all()
    return {
        row.id: (
            row.household_id,
            row.product_id,
            row.ingredient_id,
            row.name,
            Decimal(str(row.quantity)),
            row.unit,
            row.is_bought,
            row.notes,
            row.origin_recipe_id,
            row.origin_recipe_revision,
            row.origin_plan_id,
            row.origin_plan_revision,
            row.updated_at,
        )
        for row in rows
    }


def _batch_state(db, household_id):
    return {
        row.id: Decimal(str(row.remaining_quantity))
        for row in db.scalars(
            select(InventoryBatch)
            .where(InventoryBatch.household_id == household_id)
            .order_by(InventoryBatch.id)
            .execution_options(populate_existing=True)
        ).all()
    }


def test_large_household_recipe_shopping_reconciles_only_the_matched_rows(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    garlic = setup_ingredient(db)
    onion = db.scalar(
        select(Ingredient).where(Ingredient.normalized_name == "onion")
    )
    assert onion is not None

    recipe = make_recipe(
        db, auth_household, auth_user, garlic, amount=50, unit="g"
    )
    garlic_product, garlic_batches = _add_reviewed_product_and_batches(
        db,
        auth_household,
        auth_user,
        garlic,
        name="Reviewed garlic for large-household fixture",
        batch_count=20,
    )
    onion_product, onion_batches = _add_reviewed_product_and_batches(
        db,
        auth_household,
        auth_user,
        onion,
        name="Reviewed onion for large-household fixture",
        batch_count=40,
    )

    matched_item = ShoppingListItem(
        household_id=auth_household.id,
        product_id=garlic_product.id,
        ingredient_id=garlic.id,
        name="My preferred garlic",
        quantity=Decimal("15"),
        unit="g",
        is_bought=False,
        notes="Keep this manual note",
    )
    unrelated_items = [
        ShoppingListItem(
            household_id=auth_household.id,
            product_id=onion_product.id,
            ingredient_id=onion.id,
            name=f"Unrelated onion row {index:03d}",
            quantity=Decimal(index % 3 + 1),
            unit="g",
            is_bought=False,
            notes=f"Unchanged note {index:03d}",
        )
        for index in range(119)
    ]
    db.add_all(unrelated_items)
    db.flush()
    db.add(matched_item)
    db.flush()
    assert matched_item.id == 120
    assert max(item.id for item in unrelated_items) < matched_item.id

    foreign_household = Household(
        name="Other Large Shopping Home",
        slug=f"other-large-shopping-{auth_user.id}",
    )
    db.add(foreign_household)
    db.flush()
    foreign_item = ShoppingListItem(
        household_id=foreign_household.id,
        ingredient_id=garlic.id,
        name="Foreign pending garlic",
        quantity=Decimal("500"),
        unit="g",
        is_bought=False,
        notes="Must remain outside the active household",
    )
    db.add(foreign_item)
    db.commit()

    assert len(garlic_batches) + len(onion_batches) == 60
    assert len(unrelated_items) + 1 == 120
    assert len(_batch_state(db, auth_household.id)) == 60
    assert len(_shopping_state(db)) == 121
    item_state_before = _shopping_state(db)
    batch_state_before = _batch_state(db, auth_household.id)
    unrelated_state_before = {
        item_id: state
        for item_id, state in item_state_before.items()
        if item_id != matched_item.id
    }
    revisions_before = db.execute(
        select(Household.shopping_revision, Household.inventory_revision).where(
            Household.id == auth_household.id
        )
    ).one()

    with local_client(db, auth_user) as client:
        preview_data = preview(client, recipe)
        assert len(preview_data["lines"]) == 1
        line = preview_data["lines"][0]
        assert line["ingredient_id"] == garlic.id
        assert line["status"] == "ready"
        assert Decimal(line["required_quantity"]) == Decimal("50")
        assert Decimal(line["pantry_quantity"]) == Decimal("20")
        assert Decimal(line["shortage"]) == Decimal("30")
        assert Decimal(line["pending_quantity"]) == Decimal("15")
        assert Decimal(line["target_quantity"]) == Decimal("30")
        assert Decimal(line["additional_quantity"]) == Decimal("15")
        assert line["pending_item_ids"] == [matched_item.id]
        assert set(line["covered_batch_ids"]) == {batch.id for batch in garlic_batches}
        assert _shopping_state(db) == item_state_before
        assert _batch_state(db, auth_household.id) == batch_state_before

        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                preview_data,
                garlic.id,
                Decimal("30"),
                key="large-household-shopping-01",
            ),
        )
        assert response.status_code == 200, response.text

    confirmation = response.json()
    assert confirmation["created"] == []
    assert len(confirmation["updated"]) == 1
    updated = confirmation["updated"][0]
    assert updated["id"] == matched_item.id
    assert updated["product_id"] == garlic_product.id
    assert updated["ingredient_id"] == garlic.id
    assert updated["name"] == "My preferred garlic"
    assert Decimal(updated["quantity"]) == Decimal("30")
    assert updated["unit"] == "g"
    assert updated["notes"] == "Keep this manual note"

    item_state_after = _shopping_state(db)
    assert set(item_state_after) == set(item_state_before)
    assert {
        item_id: state
        for item_id, state in item_state_after.items()
        if item_id != matched_item.id
    } == unrelated_state_before
    assert item_state_after[matched_item.id][:4] == item_state_before[matched_item.id][:4]
    assert item_state_after[matched_item.id][5:12] == item_state_before[matched_item.id][5:12]
    assert item_state_after[matched_item.id][4] == Decimal("30")
    assert item_state_after[foreign_item.id] == item_state_before[foreign_item.id]
    assert _batch_state(db, auth_household.id) == batch_state_before

    current_household_items = db.scalars(
        select(ShoppingListItem).where(
            ShoppingListItem.household_id == auth_household.id
        )
    ).all()
    assert len(current_household_items) == 120
    assert sum(
        item.ingredient_id == garlic.id and not item.is_bought
        for item in current_household_items
    ) == 1
    revisions_after = db.execute(
        select(Household.shopping_revision, Household.inventory_revision).where(
            Household.id == auth_household.id
        )
    ).one()
    assert revisions_after.shopping_revision == revisions_before.shopping_revision + 1
    assert revisions_after.inventory_revision == revisions_before.inventory_revision
