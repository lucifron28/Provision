from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Event
import time
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import jwt
import pytest
from sqlalchemy import event, func, select, text, update
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.recipe_shopping import router as recipe_shopping_router
from app.api.v1.endpoints.shopping import router as shopping_router
from app.core.database import get_db
from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.ingredient import (
    Ingredient,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
    ProductPackageFactor,
)
from app.models.preferences import FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe import Recipe
from app.models.recipe_shopping import RecipeShoppingIdempotency
from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.schemas.preferences import FoodPreferencesInput
from app.schemas.recipe import RecipeWrite
from app.schemas.recipe_shopping import (
    RecipeShoppingConfirmRequest,
    RecipeShoppingPreviewRequest,
)
from app.schemas.shopping import ShoppingListItemCreate, ShoppingListItemUpdate
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.services.product_labels import product_fingerprint
from app.services.recipe_shopping import (
    _lock_curated_tables,
    confirm_recipe_shopping,
    preview_recipe_shopping,
)
from app.services.recipes import write_recipe


def recipe_payload(ingredient_id: int, amount=10, unit="g", *, optional_amount=None):
    ingredients = [dict(ingredient_id=ingredient_id, amount=amount, unit=unit)]
    if optional_amount is not None:
        ingredients.append(
            dict(
                ingredient_id=ingredient_id,
                amount=optional_amount,
                unit=unit,
                required=False,
            )
        )
    return dict(
        title="Garlic rice",
        cuisine="Filipino",
        ph_regions=["region_unknown"],
        content_permission="OWNED_OR_PERMISSION_GRANTED",
        servings=1,
        instructions=["Measure the ingredients.", "Cook the rice."],
        ingredients=ingredients,
    )


def ready_profiles(db, household, user):
    preferences = FoodPreferencesInput().model_dump(mode="json")
    db.add_all(
        [
            FoodPreference(
                household_id=household.id,
                member_user_id=user.id,
                revision=1,
                preferences=preferences,
                allergy_status="NONE_DECLARED",
            ),
            FoodPreference(
                household_id=household.id,
                member_user_id=None,
                revision=1,
                preferences=preferences,
                allergy_status="NONE_DECLARED",
            ),
        ]
    )
    db.commit()


def make_recipe(db, household, user, ingredient, *, amount=10, unit="g", optional_amount=None):
    return write_recipe(
        db,
        household.id,
        user.id,
        RecipeWrite(**recipe_payload(ingredient.id, amount, unit, optional_amount=optional_amount)),
    )


def setup_ingredient(db):
    seed_ingredient_catalog_v1(db)
    db.commit()
    return db.scalar(select(Ingredient).where(Ingredient.normalized_name == "garlic"))


def add_pantry(db, household, user, ingredient, quantity, *, unit="g", expiration_days=10):
    product = Product(household_id=household.id, name="Reviewed garlic", unit=unit)
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
        method="Reviewed test label",
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
    db.flush()
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
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=quantity,
        remaining_quantity=quantity,
        expiration_date=household_today() + timedelta(days=expiration_days),
    )
    db.add(batch)
    db.commit()
    return product, batch


def local_client(db, user, *, include_shopping=False):
    app = FastAPI()
    app.include_router(recipe_shopping_router, prefix="/recipe-shopping")
    if include_shopping:
        app.include_router(shopping_router, prefix="/shopping-list")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def preview_request(recipe):
    return dict(
        recipe_id=recipe.id,
        expected_recipe_revision=recipe.revision,
        servings="1",
        include_optional=False,
    )


def preview(client, recipe):
    response = client.post("/recipe-shopping/preview", json=preview_request(recipe))
    assert response.status_code == 200, response.text
    return response.json()


def confirm_payload(preview_json, ingredient_id, target, *, key="recipe-shopping-key-0001", consolidate=False):
    return dict(
        preview_id=preview_json["preview_id"],
        idempotency_key=key,
        expected_revision=preview_json["shopping_revision"],
        accepted_lines=[
            dict(
                ingredient_id=ingredient_id,
                target_quantity=str(target),
                consolidate_existing=consolidate,
            )
        ],
    )


def test_preview_is_repeatable_read_only_and_computes_total_shortage(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    add_pantry(db, auth_household, auth_user, ingredient, 4)
    manual = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="My preferred garlic",
        quantity=Decimal("2"),
        unit="g",
        is_bought=False,
        notes="Keep this note",
    )
    db.add(manual)
    db.commit()
    before_items = db.scalar(
        select(func.count()).select_from(ShoppingListItem).where(
            ShoppingListItem.household_id == auth_household.id
        )
    )
    marker = Product(household_id=auth_household.id, name="Uncommitted caller row", unit="g")
    db.add(marker)

    with local_client(db, auth_user) as client:
        first = preview(client, recipe)
        second = preview(client, recipe)

    line = first["lines"][0]
    assert first["preview_id"] != second["preview_id"]
    assert Decimal(line["required_quantity"]) == Decimal("10")
    assert Decimal(line["pantry_quantity"]) == Decimal("4")
    assert Decimal(line["shortage"]) == Decimal("6")
    assert Decimal(line["pending_quantity"]) == Decimal("2")
    assert Decimal(line["target_quantity"]) == Decimal("6")
    assert Decimal(line["additional_quantity"]) == Decimal("4")
    assert marker in db.new and len(db.new) == 1
    assert db.scalar(
        select(func.count()).select_from(ShoppingListItem).where(
            ShoppingListItem.household_id == auth_household.id
        )
    ) == before_items
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0
    assert auth_household.shopping_revision == 0


def test_preview_optional_filter_uses_original_recipe_indexes(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(
        db, auth_household, auth_user, ingredient, amount=10, optional_amount=5
    )
    with local_client(db, auth_user) as client:
        required_only = client.post(
            "/recipe-shopping/preview", json=preview_request(recipe)
        )
        with_optional = client.post(
            "/recipe-shopping/preview",
            json={**preview_request(recipe), "include_optional": True},
        )
    assert required_only.status_code == 200, required_only.text
    assert required_only.json()["included_requirement_indexes"] == [0]
    assert Decimal(required_only.json()["lines"][0]["required_quantity"]) == Decimal("10")
    assert with_optional.status_code == 200, with_optional.text
    assert with_optional.json()["included_requirement_indexes"] == [0, 1]
    assert Decimal(with_optional.json()["lines"][0]["required_quantity"]) == Decimal("15")


def test_confirm_updates_single_pending_row_in_place_and_replays(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    _product, batch = add_pantry(db, auth_household, auth_user, ingredient, 8)
    manual = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Manual garlic",
        quantity=Decimal("1"),
        unit="g",
        is_bought=False,
        notes="Buy from the market",
    )
    bought = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Already purchased garlic",
        quantity=Decimal("50"),
        unit="g",
        is_bought=True,
        notes="Purchased yesterday",
    )
    db.add_all([manual, bought])
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        line = preview_json["lines"][0]
        assert Decimal(line["shortage"]) == Decimal("2")
        assert Decimal(line["pending_quantity"]) == Decimal("1")
        assert Decimal(line["target_quantity"]) == Decimal("2")
        assert Decimal(line["additional_quantity"]) == Decimal("1")
        payload = confirm_payload(preview_json, ingredient.id, "2")
        committed = client.post("/recipe-shopping/confirm", json=payload)
        assert committed.status_code == 200, committed.text
        replay = client.post("/recipe-shopping/confirm", json=payload)
        assert replay.status_code == 200, replay.text

    result = committed.json()
    assert result == replay.json()
    assert result["created"] == []
    assert len(result["updated"]) == 1
    updated = result["updated"][0]
    assert updated["id"] == manual.id
    assert updated["quantity"] == 2.0
    assert updated["origin_recipe_id"] is None
    assert updated["origin_recipe_revision"] is None
    assert result["shopping_revision"] == 1
    db.expire_all()
    assert db.get(ShoppingListItem, manual.id).name == "Manual garlic"
    assert db.get(ShoppingListItem, manual.id).notes == "Buy from the market"
    assert db.get(ShoppingListItem, manual.id).quantity == Decimal("2.000000")
    assert db.get(ShoppingListItem, bought.id).is_bought is True
    assert db.get(ShoppingListItem, bought.id).notes == "Purchased yesterday"
    assert db.get(InventoryBatch, batch.id).remaining_quantity == Decimal("8.00")
    assert auth_household.shopping_revision == 1
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 1


def test_confirm_rejects_under_target_stale_revision_and_reused_key_payload(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    with local_client(db, auth_user, include_shopping=True) as client:
        preview_json = preview(client, recipe)
        too_small = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(preview_json, ingredient.id, "9"),
        )
        assert too_small.status_code == 422
        assert too_small.json()["detail"] == "TARGET_BELOW_REQUIRED_OR_PENDING_QUANTITY"

        accepted = confirm_payload(preview_json, ingredient.id, "10")
        first = client.post("/recipe-shopping/confirm", json=accepted)
        assert first.status_code == 200, first.text
        changed_payload = confirm_payload(
            preview_json, ingredient.id, "11", key=accepted["idempotency_key"]
        )
        collision = client.post("/recipe-shopping/confirm", json=changed_payload)
        assert collision.status_code == 409
        assert collision.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"

        stale_preview = preview(client, recipe)
        created_id = first.json()["created"][0]["id"]
        edit = client.patch(
            f"/shopping-list/{created_id}",
            json={"notes": "Manual edit after preview"},
        )
        assert edit.status_code == 200, edit.text
        stale = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(stale_preview, ingredient.id, "10", key="stale-key-000001"),
        )
        assert stale.status_code == 409
        assert stale.json()["detail"] == "STALE_PREVIEW"


def test_confirm_rolls_back_prior_accepted_lines_when_later_line_fails(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    garlic = setup_ingredient(db)
    rice = db.scalar(select(Ingredient).where(Ingredient.normalized_name == "rice"))
    recipe = write_recipe(
        db,
        auth_household.id,
        auth_user.id,
        RecipeWrite(
            **{
                **recipe_payload(garlic.id, amount=10),
                "ingredients": [
                    {"ingredient_id": garlic.id, "amount": 10, "unit": "g"},
                    {"ingredient_id": rice.id, "amount": 20, "unit": "g"},
                ],
            }
        ),
    )
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        lines = {line["ingredient_id"]: line for line in preview_json["lines"]}
        response = client.post(
            "/recipe-shopping/confirm",
            json={
                "preview_id": preview_json["preview_id"],
                "idempotency_key": "rollback-key-00001",
                "expected_revision": preview_json["shopping_revision"],
                "accepted_lines": [
                    {"ingredient_id": garlic.id, "target_quantity": "10"},
                    {"ingredient_id": rice.id, "target_quantity": "1"},
                ],
            },
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "TARGET_BELOW_REQUIRED_OR_PENDING_QUANTITY"
    db.expire_all()
    assert db.scalar(
        select(func.count()).select_from(ShoppingListItem).where(
            ShoppingListItem.household_id == auth_household.id
        )
    ) == 0
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0
    assert db.get(Household, auth_household.id).shopping_revision == 0
    assert Decimal(lines[garlic.id]["target_quantity"]) == Decimal("10")


def test_explicit_consolidation_keeps_primary_edits_and_persists_removed_audit(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, amount=4)
    primary = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="First manual name",
        quantity=Decimal("2"),
        unit="g",
        is_bought=False,
        notes="Primary note stays",
    )
    duplicate = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Second manual name",
        quantity=Decimal("3"),
        unit="g",
        is_bought=False,
        notes="Duplicate note retained in audit",
        origin_recipe_id=recipe.id,
        origin_recipe_revision=recipe.revision,
    )
    db.add_all([primary, duplicate])
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        payload = confirm_payload(
            preview_json, ingredient.id, "5", key="consolidate-key-0001", consolidate=True
        )
        response = client.post("/recipe-shopping/confirm", json=payload)
        assert response.status_code == 200, response.text
        replay = client.post("/recipe-shopping/confirm", json=payload)
        assert replay.status_code == 200
    result = response.json()
    assert result == replay.json()
    assert len(result["consolidated"]) == 1
    assert result["consolidated"][0]["kept_item_id"] == primary.id
    removed = result["consolidated"][0]["removed_items"][0]
    assert removed["id"] == duplicate.id
    assert removed["notes"] == "Duplicate note retained in audit"
    assert removed["origin_recipe_id"] == recipe.id
    db.expire_all()
    assert db.get(ShoppingListItem, duplicate.id) is None
    kept = db.get(ShoppingListItem, primary.id)
    assert kept.name == "First manual name"
    assert kept.notes == "Primary note stays"
    assert kept.quantity == Decimal("5.000000")


def test_multiple_pending_rows_require_explicit_consolidation(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, amount=10)
    first = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="First garlic row",
        quantity=Decimal("1"),
        unit="g",
        is_bought=False,
    )
    second = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Second garlic row",
        quantity=Decimal("2"),
        unit="g",
        is_bought=False,
    )
    db.add_all([first, second])
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                preview_json, ingredient.id, "10", key="multiple-key-00001"
            ),
        )
    assert response.status_code == 422
    assert response.json()["detail"] == "MULTIPLE_PENDING_ITEMS_REQUIRE_EXPLICIT_CONSOLIDATION"
    db.expire_all()
    assert db.get(ShoppingListItem, first.id).quantity == Decimal("1.000000")
    assert db.get(ShoppingListItem, second.id).quantity == Decimal("2.000000")
    assert db.get(Household, auth_household.id).shopping_revision == 0


def test_single_pending_package_factor_updates_native_unit_exactly(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, amount=1500)
    product = Product(household_id=auth_household.id, name="Garlic bag", unit="bag")
    db.add(product)
    db.flush()
    now = datetime.now(timezone.utc)
    mapping = ProductIngredientMapping(
        household_id=auth_household.id,
        product_id=product.id,
        version=1,
        is_current=True,
        mode="DIRECT",
        ingredient_id=ingredient.id,
        verification_status="VERIFIED",
        method="Label-verified bag amount",
        verified_by_user_id=auth_user.id,
        verified_at=now,
        unknown_composition=False,
    )
    db.add(mapping)
    db.flush()
    db.add_all(
        [
            ProductIngredientMappingTarget(
                household_id=auth_household.id,
                product_id=product.id,
                mapping_version=1,
                ingredient_id=ingredient.id,
            ),
            ProductPackageFactor(
                household_id=auth_household.id,
                product_id=product.id,
                mapping_version=1,
                ingredient_id=ingredient.id,
                inventory_unit="bag",
                ingredient_amount=Decimal("500"),
                ingredient_unit="g",
                source_reference="Synthetic test label: 500 g per bag",
                verified_by_user_id=auth_user.id,
                verified_at=now,
            ),
        ]
    )
    pending = ShoppingListItem(
        household_id=auth_household.id,
        product_id=product.id,
        name="Preferred garlic bag",
        quantity=Decimal("1"),
        unit="bag",
        is_bought=False,
        notes="Keep this exact package",
    )
    db.add(pending)
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                preview_json, ingredient.id, "1500", key="package-key-000001"
            ),
        )
    assert response.status_code == 200, response.text
    assert response.json()["updated"][0]["id"] == pending.id
    db.expire_all()
    updated = db.get(ShoppingListItem, pending.id)
    assert updated.quantity == Decimal("3.000000")
    assert updated.unit == "bag"
    assert updated.product_id == product.id
    assert updated.name == "Preferred garlic bag"
    assert updated.notes == "Keep this exact package"


def test_deselected_confirmation_is_idempotent_without_bumping_list_revision(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        payload = {
            "preview_id": preview_json["preview_id"],
            "idempotency_key": "deselect-key-00001",
            "expected_revision": preview_json["shopping_revision"],
            "accepted_lines": [],
        }
        first = client.post("/recipe-shopping/confirm", json=payload)
        assert first.status_code == 200, first.text
        with patch(
            "app.services.recipe_shopping.jwt.decode",
            side_effect=jwt.ExpiredSignatureError("expired preview"),
        ):
            replay = client.post("/recipe-shopping/confirm", json=payload)
        assert replay.status_code == 200, replay.text
    assert first.json() == replay.json()
    assert first.json()["created"] == []
    assert first.json()["shopping_revision"] == 0
    assert auth_household.shopping_revision == 0
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 1


def test_tampered_preview_token_is_rejected(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        claims = jwt.decode(
            preview_json["preview_id"],
            options={"verify_signature": False, "verify_exp": False},
            algorithms=["HS256"],
        )
        claims["fingerprint"] = "0" * 64
        tampered = jwt.encode(
            claims, "invalid-preview-secret-long-enough-for-tests", algorithm="HS256"
        )
        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                {**preview_json, "preview_id": tampered},
                ingredient.id,
                "10",
                key="tamper-key-000001",
            ),
        )
    assert response.status_code == 409
    assert response.json()["detail"] == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0


@pytest.mark.parametrize("changed_context", ["profile", "product", "source"])
def test_changed_profile_product_or_source_invalidates_preview(
    db, auth_household, auth_user, changed_context
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    product = None
    source = None
    if changed_context == "product":
        product, _batch = add_pantry(db, auth_household, auth_user, ingredient, 10)
    elif changed_context == "source":
        host = "synthetic.example.com"
        policy = {
            "review_status": "candidate",
            "tier": "filipino_priority",
            "enabled": False,
            "allowed_hosts": [host],
            "access_mode": "search_link_only",
            "disabled_reason": "Synthetic test candidate",
        }
        source = RecipeSource(
            canonical_host=host,
            publisher_name="Synthetic test source",
            revision=1,
            policy=policy,
        )
        db.add(source)
        db.flush()
        db.add(
            RecipeSourceReference(
                household_id=auth_household.id,
                recipe_id=recipe.id,
                source_id=source.id,
                canonical_url=f"https://{host}/recipes/garlic-rice",
                author=None,
                revision=1,
                is_active=True,
                broader_web_permission=True,
                linked_by_user_id=auth_user.id,
            )
        )
        db.commit()

    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        if changed_context == "profile":
            profile = db.scalar(
                select(FoodPreference).where(
                    FoodPreference.household_id == auth_household.id,
                    FoodPreference.member_user_id == auth_user.id,
                )
            )
            profile.revision += 1
            profile.preferences = {
                **profile.preferences,
                "preferred_cuisines": ["Filipino", "Bicolano"],
            }
            db.commit()
        elif changed_context == "product":
            product.name = "Changed garlic product identity"
            db.commit()
        else:
            source.policy = {
                **source.policy,
                "review_status": "rejected",
                "disabled_reason": "Synthetic revocation test",
            }
            source.revision += 1
            db.commit()

        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                preview_json,
                ingredient.id,
                str(max(Decimal("1"), Decimal(str(preview_json["lines"][0]["target_quantity"] or "0")))),
                key=f"changed-{changed_context}-0001",
            ),
        )

    assert response.status_code == 409
    assert response.json()["detail"] == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0
    assert db.get(Household, auth_household.id).shopping_revision == 0


def test_foreign_household_recipe_and_preview_token_are_rejected(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    foreign_user = User(
        email="other-household@example.test",
        hashed_password="not-used-by-test",
        is_active=True,
    )
    db.add(foreign_user)
    db.flush()
    foreign_household = Household(name="Other home", slug="other-home-shopping")
    db.add(foreign_household)
    db.flush()
    db.add(
        HouseholdMembership(
            household_id=foreign_household.id,
            user_id=foreign_user.id,
            role=HouseholdRole.OWNER.value,
            is_default=True,
        )
    )
    db.commit()

    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        guessed = client.post(
            "/recipe-shopping/preview",
            json={**preview_request(recipe), "recipe_id": 999999},
        )
        assert guessed.status_code == 404
        cross_household = client.post(
            "/recipe-shopping/confirm",
            headers={"X-Household-ID": str(foreign_household.id)},
            json=confirm_payload(
                preview_json, ingredient.id, "10", key="foreign-key-000001"
            ),
        )
        assert cross_household.status_code == 403


def test_unlinked_alias_and_incompatible_pending_units_require_review(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    db.add(
        ShoppingListItem(
            household_id=auth_household.id,
            name="fresh garlic bulb",
            quantity=Decimal("1"),
            unit="bundle",
            is_bought=False,
        )
    )
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        line = preview_json["lines"][0]
        assert line["status"] == "review_required"
        assert "unlinked_alias_match_requires_review" in line["review_reasons"]
        assert preview_json["unlinked_manual_items"][0]["candidate_ingredient_ids"] == [ingredient.id]
        assert preview_json["unlinked_manual_items"][0]["reason"] == "possible_alias_match_requires_review"
        rejected = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(preview_json, ingredient.id, "10", key="review-key-000001"),
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"] == "REVIEW_REQUIRED"


def test_pending_product_identity_conflicts_require_review(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    garlic = setup_ingredient(db)
    rice = db.scalar(select(Ingredient).where(Ingredient.normalized_name == "rice"))
    recipe = make_recipe(db, auth_household, auth_user, garlic)
    now = datetime.now(timezone.utc)
    mismatched_product = Product(
        household_id=auth_household.id, name="Rice sold as garlic", unit="g"
    )
    odd_unit_product = Product(
        household_id=auth_household.id, name="Garlic bag", unit="bag"
    )
    db.add_all([mismatched_product, odd_unit_product])
    db.flush()
    db.add_all(
        [
            ProductIngredientMapping(
                household_id=auth_household.id,
                product_id=mismatched_product.id,
                version=1,
                mode="DIRECT",
                ingredient_id=rice.id,
                verification_status="VERIFIED",
                method="Synthetic test mapping",
                verified_by_user_id=auth_user.id,
                verified_at=now,
                unknown_composition=False,
            ),
            ProductIngredientMapping(
                household_id=auth_household.id,
                product_id=odd_unit_product.id,
                version=1,
                mode="DIRECT",
                ingredient_id=garlic.id,
                verification_status="VERIFIED",
                method="Synthetic test mapping",
                verified_by_user_id=auth_user.id,
                verified_at=now,
                unknown_composition=False,
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            ProductIngredientMappingTarget(
                household_id=auth_household.id,
                product_id=mismatched_product.id,
                mapping_version=1,
                ingredient_id=rice.id,
            ),
            ProductIngredientMappingTarget(
                household_id=auth_household.id,
                product_id=odd_unit_product.id,
                mapping_version=1,
                ingredient_id=garlic.id,
            ),
            ShoppingListItem(
                household_id=auth_household.id,
                product_id=mismatched_product.id,
                ingredient_id=garlic.id,
                name="Explicit garlic on a rice product",
                quantity=Decimal("1"),
                unit="g",
                is_bought=False,
            ),
            ShoppingListItem(
                household_id=auth_household.id,
                product_id=odd_unit_product.id,
                ingredient_id=garlic.id,
                name="Garlic bag with gram quantity",
                quantity=Decimal("1"),
                unit="g",
                is_bought=False,
            ),
        ]
    )
    db.commit()
    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
    line = preview_json["lines"][0]
    assert line["status"] == "review_required"
    assert "product_identity_conflicts_with_explicit_ingredient" in line["review_reasons"]
    assert "shopping_product_unit_conflict_requires_review" in line["review_reasons"]


@pytest.mark.parametrize("actor_state", ["foreign", "inactive"])
def test_preview_rechecks_active_membership_before_recipe_or_pantry_reads(
    db, engine, auth_household, auth_user, actor_state
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    if actor_state == "foreign":
        actor = User(
            email="nonmember-shopping@example.test",
            hashed_password="test-only",
            is_active=True,
        )
        db.add(actor)
        db.commit()
    else:
        actor = auth_user
        actor.is_active = False
        db.commit()

    statements = []

    def capture_sql(_connection, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.casefold())

    event.listen(engine, "before_cursor_execute", capture_sql)
    try:
        with pytest.raises(HTTPException) as error:
            preview_recipe_shopping(
                db,
                auth_household.id,
                actor.id,
                RecipeShoppingPreviewRequest(**preview_request(recipe)),
            )
    finally:
        event.remove(engine, "before_cursor_execute", capture_sql)

    assert error.value.status_code == 403
    assert not any("inventory_batches" in statement for statement in statements)
    assert not any(" from recipes " in statement for statement in statements)


def test_manual_shopping_api_accepts_valid_identity_and_rejects_foreign_or_inactive_source(
    db, auth_household, auth_user
):
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    foreign = Household(name="Foreign source", slug="foreign-shopping-source")
    db.add(foreign)
    db.flush()
    foreign_recipe = Recipe(
        household_id=foreign.id,
        title="Foreign recipe",
        cuisine="Filipino",
        content={},
        revision=1,
        is_active=True,
    )
    db.add(foreign_recipe)
    db.commit()
    with local_client(db, auth_user, include_shopping=True) as client:
        created = client.post(
            "/shopping-list/",
            json={
                "name": "Garlic for later",
                "quantity": "0.125000",
                "unit": "kg",
                "ingredient_id": ingredient.id,
                "origin_recipe_id": recipe.id,
            },
        )
        assert created.status_code == 201, created.text
        assert created.json()["ingredient_id"] == ingredient.id
        assert created.json()["origin_recipe_id"] == recipe.id
        assert client.post(
            "/shopping-list/",
            json={"name": "Foreign source", "origin_recipe_id": foreign_recipe.id},
        ).status_code == 404
        ingredient.is_active = False
        db.commit()
        assert client.post(
            "/shopping-list/",
            json={"name": "Inactive identity", "ingredient_id": ingredient.id},
        ).status_code == 422
        assert client.post(
            "/shopping-list/",
            json={"name": "Bad quantity", "quantity": "NaN"},
        ).status_code == 422
        assert client.post(
            "/shopping-list/",
            json={"name": "Too precise", "quantity": "0.0000001"},
        ).status_code == 422
        created = client.post(
            "/shopping-list/", json={"name": "Patch validation", "quantity": "1"}
        )
        assert created.status_code == 201
        for invalid_patch in ({"name": None}, {"quantity": None}, {"is_bought": None}):
            assert client.patch(
                f"/shopping-list/{created.json()['id']}", json=invalid_patch
            ).status_code == 422
    assert ShoppingListItemCreate.model_validate(
        {"name": "Valid", "quantity": "0.125000"}
    ).quantity == Decimal("0.125000")
    assert ShoppingListItemUpdate.model_validate({"quantity": "0.5"}).quantity == Decimal("0.5")


def test_toggle_refreshes_cached_item_after_household_guard(db, engine, auth_household, auth_user):
    item = ShoppingListItem(
        household_id=auth_household.id,
        name="Cached toggle item",
        quantity=Decimal("1"),
        is_bought=False,
    )
    db.add(item)
    db.commit()
    cached = db.get(ShoppingListItem, item.id)
    assert cached.is_bought is False
    with Session(engine) as independent:
        independent.execute(
            update(ShoppingListItem)
            .where(ShoppingListItem.id == item.id)
            .values(is_bought=True)
        )
        independent.commit()

    with local_client(db, auth_user, include_shopping=True) as client:
        response = client.post(f"/shopping-list/{item.id}/toggle")
    assert response.status_code == 200, response.text
    assert response.json()["is_bought"] is False


def test_concurrent_identical_confirmations_are_exactly_once(db, engine, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    preview_json = preview_recipe_shopping(
        db,
        auth_household.id,
        auth_user.id,
        RecipeShoppingPreviewRequest(**preview_request(recipe)),
    ).model_dump(mode="json")
    payload = RecipeShoppingConfirmRequest(
        **confirm_payload(preview_json, ingredient.id, "10", key="concurrent-key-0001")
    )
    household_id, actor_id = auth_household.id, auth_user.id
    db.rollback()
    barrier = Barrier(2)

    def confirm_once(_):
        with Session(engine, autoflush=False, expire_on_commit=False) as independent:
            barrier.wait(timeout=10)
            return confirm_recipe_shopping(independent, household_id, actor_id, payload).model_dump(
                mode="json"
            )

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(confirm_once, range(2)))

    assert results[0] == results[1]
    db.expire_all()
    assert db.scalar(
        select(func.count()).select_from(RecipeShoppingIdempotency).where(
            RecipeShoppingIdempotency.household_id == household_id
        )
    ) == 1
    assert db.scalar(
        select(func.count()).select_from(ShoppingListItem).where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.origin_recipe_id == recipe.id,
        )
    ) == 1
    assert db.get(Household, household_id).shopping_revision == 1


def test_unlinked_generic_name_checks_every_recipe_ingredient_candidate(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    setup_ingredient(db)
    ingredients = [
        Ingredient(
            canonical_name=f"Sauce ingredient {index:02d}",
            normalized_name=f"sauce ingredient {index:02d}",
            family="allium",
            default_dimension="mass",
            default_unit="g",
            is_active=True,
        )
        for index in range(11)
    ]
    db.add_all(ingredients)
    db.flush()
    payload = recipe_payload(ingredients[0].id)
    payload["ingredients"] = [
        dict(ingredient_id=ingredient.id, amount=1, unit="g")
        for ingredient in ingredients
    ]
    recipe = write_recipe(db, auth_household.id, auth_user.id, RecipeWrite(**payload))
    db.add(
        ShoppingListItem(
            household_id=auth_household.id,
            name="sauce",
            quantity=Decimal("1"),
            unit="g",
            is_bought=False,
        )
    )
    db.commit()

    with local_client(db, auth_user) as client:
        preview_json = preview(client, recipe)
        candidate_ids = sorted(ingredient.id for ingredient in ingredients)
        lines_by_id = {line["ingredient_id"]: line for line in preview_json["lines"]}
        assert set(lines_by_id) == set(candidate_ids)
        assert all(lines_by_id[ingredient_id]["status"] == "review_required" for ingredient_id in candidate_ids)
        assert preview_json["unlinked_manual_items"][0]["candidate_ingredient_ids"] == candidate_ids
        response = client.post(
            "/recipe-shopping/confirm",
            json=confirm_payload(
                preview_json,
                candidate_ids[-1],
                "1",
                key="all-sauce-candidates-0001",
            ),
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "REVIEW_REQUIRED"
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 1
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0


def test_password_hash_changes_do_not_change_preview_ingredient_fingerprint(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    request = RecipeShoppingPreviewRequest(**preview_request(recipe))

    first = preview_recipe_shopping(db, auth_household.id, auth_user.id, request)
    first_claims = jwt.decode(
        first.preview_id,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )
    old_password_hash = auth_user.hashed_password
    auth_user.hashed_password = "new unrelated password hash"
    db.commit()
    second = preview_recipe_shopping(db, auth_household.id, auth_user.id, request)
    second_claims = jwt.decode(
        second.preview_id,
        options={"verify_signature": False, "verify_exp": False},
        algorithms=["HS256"],
    )

    assert first_claims["fingerprint"] == second_claims["fingerprint"]
    assert old_password_hash not in first.preview_id
    assert "hashed_password" not in repr(first_claims)


def test_reused_session_refreshes_pending_item_before_confirm(
    db, engine, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient)
    pending = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Preferred garlic",
        quantity=Decimal("1"),
        unit="g",
        is_bought=False,
        notes="Original note",
    )
    db.add(pending)
    db.commit()
    cached = db.get(ShoppingListItem, pending.id)
    assert cached.notes == "Original note"

    with Session(engine, autoflush=False, expire_on_commit=False) as external:
        with external.begin():
            current_item = external.scalar(
                select(ShoppingListItem)
                .where(ShoppingListItem.id == pending.id)
                .with_for_update()
            )
            current_item.notes = "Updated in another session"
            current_household = external.scalar(
                select(Household)
                .where(Household.id == auth_household.id)
                .with_for_update()
            )
            current_household.shopping_revision += 1

    preview_data = preview_recipe_shopping(
        db,
        auth_household.id,
        auth_user.id,
        RecipeShoppingPreviewRequest(**preview_request(recipe)),
    ).model_dump(mode="json")
    result = confirm_recipe_shopping(
        db,
        auth_household.id,
        auth_user.id,
        RecipeShoppingConfirmRequest(
            **confirm_payload(
                preview_data,
                ingredient.id,
                "10",
                key="cached-pending-refresh-0001",
            )
        ),
    )

    assert [item.id for item in result.updated] == [pending.id]
    assert result.created == []
    refreshed = db.get(ShoppingListItem, pending.id)
    assert refreshed.quantity == Decimal("10.000000")
    assert refreshed.notes == "Updated in another session"
    assert db.get(Household, auth_household.id).shopping_revision == 2
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 1


def test_curated_table_lock_order_does_not_deadlock_source_review_writer(db, engine):
    host = "lock-order.example.com"
    source = RecipeSource(
        canonical_host=host,
        publisher_name="Synthetic lock order source",
        revision=1,
        policy={"review_status": "candidate", "enabled": False},
    )
    db.add(source)
    db.commit()
    source_id = source.id
    db.rollback()

    source_updated = Event()
    allow_review_insert = Event()
    confirmer_pid_ready = Event()
    confirmer_pid = {}

    def update_source_then_review():
        with Session(engine, autoflush=False) as writer:
            with writer.begin():
                current = writer.scalar(
                    select(RecipeSource)
                    .where(RecipeSource.id == source_id)
                    .with_for_update()
                )
                current.revision = 2
                current.policy = {"review_status": "approved", "enabled": True}
                writer.flush()
                source_updated.set()
                if not allow_review_insert.wait(timeout=10):
                    raise TimeoutError("Timed out waiting to insert the synthetic source review")
                writer.add(
                    RecipeSourceReview(
                        source_id=source_id,
                        revision=2,
                        reviewed_by="Synthetic maintainer",
                        recorded_at=datetime.now(timezone.utc),
                        snapshot={"review_status": "approved", "revision": 2},
                    )
                )

    def acquire_curated_locks():
        if not source_updated.wait(timeout=8):
            raise TimeoutError("Source update did not acquire its row lock")
        with Session(engine, autoflush=False) as confirmer:
            with confirmer.begin():
                confirmer_pid["pid"] = confirmer.scalar(text("SELECT pg_backend_pid()"))
                confirmer_pid_ready.set()
                _lock_curated_tables(confirmer)

    blocked_on_table_lock = False
    with ThreadPoolExecutor(max_workers=2) as workers:
        writer_future = workers.submit(update_source_then_review)
        confirmer_future = workers.submit(acquire_curated_locks)
        try:
            assert source_updated.wait(timeout=8)
            assert confirmer_pid_ready.wait(timeout=8)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with engine.connect() as observer:
                    wait_type = observer.scalar(
                        text(
                            "SELECT wait_event_type FROM pg_stat_activity "
                            "WHERE pid = :pid"
                        ),
                        {"pid": confirmer_pid["pid"]},
                    )
                if wait_type == "Lock":
                    blocked_on_table_lock = True
                    break
                time.sleep(0.02)
        finally:
            allow_review_insert.set()

        writer_future.result(timeout=10)
        confirmer_future.result(timeout=10)

    assert blocked_on_table_lock, "Confirmer did not wait behind the source update"
    assert db.scalar(
        select(func.count()).select_from(RecipeSourceReview).where(
            RecipeSourceReview.source_id == source_id,
            RecipeSourceReview.revision == 2,
        )
    ) == 1
