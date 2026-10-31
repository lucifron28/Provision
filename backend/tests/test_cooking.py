from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
import time

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import pytest
from sqlalchemy import event as sqlalchemy_event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.cooking import router as cooking_router
from app.core.database import get_db
from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.cooking import CookingConsumption, CookingIdempotency, CookingSession
from app.models.event import EventType, InventoryEvent
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.ingredient import (
    Ingredient,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
    ProductPackageFactor,
)
from app.models.leftover import Leftover, LeftoverEvent, LeftoverEventType
from app.models.preferences import FoodAllergy, FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.cooking import CookingConfirmRequest, CookingPreviewRequest
from app.schemas.preferences import FoodPreferencesInput
from app.schemas.recipe import RecipeWrite
from app.services import cooking as cooking_service
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.services.product_labels import product_fingerprint
from app.services.recipes import write_recipe


def _ready_profiles(db, household, user, *, milk_allergy=False):
    preferences = FoodPreferencesInput().model_dump(mode="json")
    member_profile = FoodPreference(
        household_id=household.id,
        member_user_id=user.id,
        revision=1,
        preferences=preferences,
        allergy_status="DECLARED" if milk_allergy else "NONE_DECLARED",
    )
    household_profile = FoodPreference(
        household_id=household.id,
        member_user_id=None,
        revision=1,
        preferences=preferences,
        allergy_status="NONE_DECLARED",
    )
    db.add_all([member_profile, household_profile])
    db.flush()
    if milk_allergy:
        db.add(
            FoodAllergy(
                profile_id=member_profile.id,
                allergen_code="milk",
                severity="severe",
                cross_contact_concern=False,
            )
        )
    db.commit()


def _garlic(db):
    seed_ingredient_catalog_v1(db)
    db.commit()
    ingredient = db.scalar(
        select(Ingredient).where(Ingredient.normalized_name == "garlic")
    )
    assert ingredient is not None
    return ingredient


def _recipe(db, household, user, ingredient, *, amount="10", unit="g", servings="1"):
    return write_recipe(
        db,
        household.id,
        user.id,
        RecipeWrite(
            title="Garlic rice",
            cuisine="Filipino",
            content_permission="OWNED_OR_PERMISSION_GRANTED",
            ph_regions=["region_unknown"],
            servings=servings,
            instructions=["Measure the ingredients.", "Cook the rice."],
            ingredients=[
                {"ingredient_id": ingredient.id, "amount": amount, "unit": unit}
            ],
        ),
    )


def _product_mapping(
    db,
    household,
    user,
    ingredient,
    *,
    name="Verified garlic",
    unit="g",
    mode="DIRECT",
    factor_amount=None,
    allergens=None,
):
    product = Product(household_id=household.id, name=name, unit=unit)
    db.add(product)
    db.flush()
    now = datetime.now(timezone.utc)
    mapping = ProductIngredientMapping(
        household_id=household.id,
        product_id=product.id,
        version=1,
        is_current=True,
        mode=mode,
        ingredient_id=ingredient.id if mode == "DIRECT" else None,
        verification_status="VERIFIED",
        method="Reviewed synthetic test evidence",
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
    if factor_amount is not None:
        db.add(
            ProductPackageFactor(
                household_id=household.id,
                product_id=product.id,
                mapping_version=1,
                ingredient_id=ingredient.id,
                inventory_unit=unit,
                ingredient_amount=Decimal(str(factor_amount)),
                ingredient_unit="g",
                source_reference="Synthetic package factor test evidence",
                verified_by_user_id=user.id,
                verified_at=now,
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
            declared_allergens=allergens or [],
            possible_allergens=[],
            custom_allergens=[],
            composition_known=True,
            source_reference="Synthetic label reviewed for test use",
            reviewed_by_user_id=user.id,
            reviewed_at=now,
        )
    )
    db.flush()
    return product


def _batch(db, household, product, quantity, *, expiry=None):
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=Decimal(str(quantity)),
        remaining_quantity=Decimal(str(quantity)),
        expiration_date=expiry,
    )
    db.add(batch)
    db.commit()
    return batch


def _local_client(db, user, *, raise_server_exceptions=True):
    app = FastAPI()
    app.include_router(cooking_router, prefix="/cooking")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app, raise_server_exceptions=raise_server_exceptions)


def _preview_request(recipe):
    return {
        "recipe_id": recipe.id,
        "expected_recipe_revision": recipe.revision,
        "servings": "1",
        "include_optional": False,
    }


def _preview(client, recipe):
    response = client.post("/cooking/preview", json=_preview_request(recipe))
    assert response.status_code == 200, response.text
    return response.json()


def _confirm_payload(preview, *, key="cooking-confirm-0001", leftovers=None):
    return {
        "preview_id": preview["preview_id"],
        "idempotency_key": key,
        "confirmation": "RECORD COOKING",
        "record_history": True,
        "acknowledged_missing_expiry_batch_ids": preview[
            "missing_expiry_batch_ids"
        ],
        "leftovers": leftovers or [],
    }


def _count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_preview_is_read_only_uses_fefo_and_excludes_expired_batches(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    expired = _batch(db, auth_household, product, "30", expiry=household_today() - timedelta(days=1))
    first = _batch(db, auth_household, product, "4", expiry=household_today() + timedelta(days=1))
    unknown_expiry = _batch(db, auth_household, product, "6")
    before = {
        "sessions": _count(db, CookingSession),
        "events": _count(db, InventoryEvent),
        "revision": auth_household.inventory_revision,
    }

    with _local_client(db, auth_user) as client:
        result = _preview(client, recipe)

    requirement = result["requirements"][0]
    assert Decimal(requirement["requested_quantity"]) == Decimal("10")
    assert [item["batch_id"] for item in requirement["allocations"]] == [first.id, unknown_expiry.id]
    assert Decimal(requirement["allocations"][0]["ingredient_quantity"]) == Decimal("4")
    assert result["missing_expiry_batch_ids"] == [unknown_expiry.id]
    assert expired.id not in [item["batch_id"] for item in requirement["allocations"]]
    assert _count(db, CookingSession) == before["sessions"]
    assert _count(db, InventoryEvent) == before["events"]
    assert auth_household.inventory_revision == before["revision"]


def test_confirm_consumes_fefo_batches_once_and_exact_retry_replays_after_expiry(
    db, auth_household, auth_user, monkeypatch
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    first = _batch(db, auth_household, product, "4", expiry=household_today() + timedelta(days=1))
    second = _batch(db, auth_household, product, "6")
    monkeypatch.setattr(cooking_service, "_PREVIEW_TTL", timedelta(seconds=2))

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        payload = _confirm_payload(preview)
        confirmed = client.post("/cooking/confirm", json=payload)
        assert confirmed.status_code == 200, confirmed.text
        first_response = confirmed.json()
        assert [item["batch_id"] for item in first_response["session"]["consumptions"]] == [
            first.id,
            second.id,
        ]
        assert first_response["session"]["recipe_revision"] == recipe.revision
        assert first_response["session"]["inventory_revision"] == 1
        assert _count(db, CookingSession) == 1
        assert _count(db, CookingIdempotency) == 1
        assert _count(db, CookingConsumption) == 2
        assert _count(db, InventoryEvent) == 2
        assert auth_household.inventory_revision == 1

        time.sleep(2.1)
        monkeypatch.setattr(
            cooking_service,
            "_decode_preview",
            lambda _token: (_ for _ in ()).throw(AssertionError("retry decoded expired preview")),
        )
        replay = client.post("/cooking/confirm", json=payload)
        assert replay.status_code == 200, replay.text
        assert replay.json() == first_response
        assert _count(db, CookingSession) == 1
        assert _count(db, CookingConsumption) == 2
        assert _count(db, InventoryEvent) == 2
        assert auth_household.inventory_revision == 1


def test_same_idempotency_key_with_changed_payload_is_rejected(db, auth_household, auth_user):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    _batch(db, auth_household, product, "10")

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        payload = _confirm_payload(preview)
        assert client.post("/cooking/confirm", json=payload).status_code == 200
        changed = {
            **payload,
            "leftovers": [{"name": "Changed result", "quantity": "1", "unit": "portion"}],
        }
        response = client.post("/cooking/confirm", json=changed)
    assert response.status_code == 409
    assert response.json()["detail"] == "IDEMPOTENCY_KEY_REUSED"


def test_missing_expiry_acknowledgement_does_not_consume_stock(db, auth_household, auth_user):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    batch = _batch(db, auth_household, product, "10")

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        payload = _confirm_payload(preview)
        payload["acknowledged_missing_expiry_batch_ids"] = []
        response = client.post("/cooking/confirm", json=payload)

    assert response.status_code == 422
    assert response.json()["detail"] == "MISSING_EXPIRY_ACKNOWLEDGEMENT_REQUIRED"
    db.refresh(batch)
    assert Decimal(str(batch.remaining_quantity)) == Decimal("10")
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_confirm_idempotency_hash_ignores_generated_prepared_at_for_exact_body_retry(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    _batch(db, auth_household, product, "10")
    payload_leftover = {"name": "Garlic rice", "quantity": "2", "unit": "portion"}

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        payload = _confirm_payload(preview, leftovers=[payload_leftover])
        first = client.post("/cooking/confirm", json=payload)
        assert first.status_code == 200, first.text
        first_json = first.json()
        replay = client.post("/cooking/confirm", json=payload)

    assert replay.status_code == 200, replay.text
    assert replay.json() == first_json
    assert len(first_json["session"]["leftovers"]) == 1
    assert _count(db, CookingSession) == 1
    assert _count(db, CookingConsumption) == 1
    assert _count(db, InventoryEvent) == 1
    assert _count(db, CookingIdempotency) == 1
    assert _count(db, Leftover) == 1


def test_confirmation_rolls_back_stock_when_leftover_validation_fails(db, auth_household, auth_user):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    batch = _batch(db, auth_household, product, "10")

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        payload = _confirm_payload(
            preview,
            leftovers=[
                {
                    "name": "Invalid location leftover",
                    "storage_location_id": 999999,
                    "quantity": "1",
                    "unit": "portion",
                }
            ],
        )
        response = client.post("/cooking/confirm", json=payload)

    assert response.status_code == 404
    db.refresh(batch)
    assert Decimal(str(batch.remaining_quantity)) == Decimal("10")
    assert _count(db, CookingSession) == 0
    assert _count(db, CookingConsumption) == 0
    assert _count(db, InventoryEvent) == 0
    assert _count(db, CookingIdempotency) == 0


def test_non_hundredth_package_inverse_requires_review_without_partial_writes(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient, amount="1")
    product = _product_mapping(
        db,
        auth_household,
        auth_user,
        ingredient,
        unit="pack",
        factor_amount="3",
    )
    batch = _batch(db, auth_household, product, "3")

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        assert Decimal(preview["requirements"][0]["allocations"][0]["native_quantity"]) == Decimal(
            "0.33333333333333333333333333333333333333333333333333"
        )
        response = client.post("/cooking/confirm", json=_confirm_payload(preview))

    assert response.status_code == 422
    db.refresh(batch)
    assert Decimal(str(batch.remaining_quantity)) == Decimal("3")
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_actual_amount_override_is_used_without_serving_rescaling(db, auth_household, auth_user):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient, amount="10")
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    _batch(db, auth_household, product, "4")

    with _local_client(db, auth_user) as client:
        response = client.post(
            "/cooking/preview",
            json={
                **_preview_request(recipe),
                "servings": "5",
                "actual_amount_overrides": [
                    {"requirement_index": 0, "amount": "4", "unit": "g"}
                ],
            },
        )

    assert response.status_code == 200, response.text
    requirement = response.json()["requirements"][0]
    assert Decimal(requirement["requested_quantity"]) == Decimal("4")
    assert Decimal(requirement["allocations"][0]["native_quantity"]) == Decimal("4")


def test_preview_returns_review_for_nonrepresentable_scaled_requirement(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(
        db, auth_household, auth_user, ingredient, amount="1", servings="3"
    )

    with _local_client(db, auth_user, raise_server_exceptions=False) as client:
        response = client.post(
            "/cooking/preview",
            json={**_preview_request(recipe), "servings": "1"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "REVIEW_REQUIRED"
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_preview_returns_review_when_scaled_requirement_exceeds_supported_amount(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        amount="99999999.999999",
    )

    with _local_client(db, auth_user, raise_server_exceptions=False) as client:
        response = client.post(
            "/cooking/preview",
            json={**_preview_request(recipe), "servings": "2"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "REVIEW_REQUIRED"
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_cooking_session_get_reads_linked_leftover_from_one_snapshot(
    db, engine, auth_household, auth_user
):
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    session = CookingSession(
        household_id=auth_household.id,
        recipe_id=recipe.id,
        recipe_revision=recipe.revision,
        actor_user_id=auth_user.id,
        servings=1,
        inventory_revision=auth_household.inventory_revision,
    )
    db.add(session)
    db.flush()
    leftover = Leftover(
        household_id=auth_household.id,
        name="Rice for session read",
        cooking_session_id=session.id,
        prepared_at=datetime.now(timezone.utc),
        quantity=Decimal("2"),
        remaining_quantity=Decimal("2"),
        unit="g",
        revision=1,
    )
    db.add(leftover)
    db.commit()

    with _local_client(db, auth_user) as client:
        parent_reads = 0
        interleaved = False

        def commit_event_after_parent_read(_conn, _cursor, statement, _params, _context, _many):
            nonlocal parent_reads, interleaved
            normalized = statement.casefold()
            if not normalized.lstrip().startswith("select") or "from leftovers" not in normalized:
                return
            parent_reads += 1
            if parent_reads != 2 or interleaved:
                return
            interleaved = True
            with Session(engine, autoflush=False) as writer:
                row = writer.scalar(
                    select(Leftover)
                    .where(Leftover.household_id == auth_household.id, Leftover.id == leftover.id)
                    .with_for_update()
                )
                row.remaining_quantity = Decimal("1")
                row.revision = 2
                writer.add(
                    LeftoverEvent(
                        household_id=auth_household.id,
                        leftover_id=leftover.id,
                        cooking_session_id=session.id,
                        event_type=LeftoverEventType.CONSUMED.value,
                        quantity=Decimal("1"),
                        unit="g",
                        occurred_at=datetime.now(timezone.utc),
                        reason="Concurrent consumption",
                    )
                )
                writer.commit()

        sqlalchemy_event.listen(engine, "after_cursor_execute", commit_event_after_parent_read)
        try:
            response = client.get(f"/cooking/sessions/{session.id}")
        finally:
            sqlalchemy_event.remove(engine, "after_cursor_execute", commit_event_after_parent_read)

    assert interleaved is True
    assert response.status_code == 200, response.text
    response_leftover = response.json()["leftovers"][0]
    assert response_leftover["revision"] == 1
    assert Decimal(response_leftover["remaining_quantity"]) == Decimal("2")
    assert response_leftover["events"] == []
    db.rollback()
    current = db.scalar(select(Leftover).where(Leftover.id == leftover.id))
    assert current.revision == 2
    assert Decimal(str(current.remaining_quantity)) == Decimal("1")
    assert _count(db, LeftoverEvent) == 1


def test_unknown_product_unit_is_not_treated_as_package_conversion(db, auth_household, auth_user):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(
        db, auth_household, auth_user, ingredient, unit="scoop", name="Unconverted scoop"
    )
    _batch(db, auth_household, product, "10")

    with _local_client(db, auth_user) as client:
        response = client.post("/cooking/preview", json=_preview_request(recipe))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "REVIEW_REQUIRED"
    assert response.json()["detail"]["reason"] == "INSUFFICIENT_VERIFIED_DIRECT_STOCK"
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_recipe_revision_change_makes_preview_stale_without_consumption(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    batch = _batch(db, auth_household, product, "10")

    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)
        write_recipe(
            db,
            auth_household.id,
            auth_user.id,
            RecipeWrite(
                title="Garlic rice changed",
                cuisine="Filipino",
                content_permission="OWNED_OR_PERMISSION_GRANTED",
                ph_regions=["region_unknown"],
                servings="1",
                instructions=["Measure the ingredients.", "Cook the rice."],
                ingredients=[{"ingredient_id": ingredient.id, "amount": "10", "unit": "g"}],
                expected_revision=recipe.revision,
            ),
            recipe_id=recipe.id,
        )
        response = client.post("/cooking/confirm", json=_confirm_payload(preview))

    assert response.status_code == 409
    assert response.json()["detail"] == "STALE_PREVIEW"
    db.refresh(batch)
    assert Decimal(str(batch.remaining_quantity)) == Decimal("10")
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0


def test_foreign_household_recipe_and_batch_are_not_visible_to_cooking(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    local_recipe = _recipe(db, auth_household, auth_user, ingredient)
    foreign = Household(name="Other cooking home", slug=f"other-cooking-{auth_user.id}")
    db.add(foreign)
    db.flush()
    db.add(
        HouseholdMembership(
            household_id=foreign.id,
            user_id=auth_user.id,
            role=HouseholdRole.MEMBER.value,
            is_default=False,
        )
    )
    foreign_recipe = Recipe(
        household_id=foreign.id,
        title="Private foreign recipe",
        cuisine="Filipino",
        content={},
        revision=1,
        is_active=True,
        created_by_user_id=auth_user.id,
    )
    db.add(foreign_recipe)
    foreign_product = _product_mapping(db, foreign, auth_user, ingredient, name="Foreign garlic")
    foreign_batch = _batch(db, foreign, foreign_product, "20")
    db.commit()

    with _local_client(db, auth_user) as client:
        foreign_recipe_response = client.post(
            "/cooking/preview",
            json={"recipe_id": foreign_recipe.id, "expected_recipe_revision": 1, "servings": "1"},
        )
        foreign_stock_response = client.post(
            "/cooking/preview", json=_preview_request(local_recipe)
        )

    assert foreign_recipe_response.status_code == 404
    assert foreign_stock_response.status_code == 422
    assert foreign_stock_response.json()["detail"]["reason"] == "INSUFFICIENT_VERIFIED_DIRECT_STOCK"
    assert foreign_batch.household_id != auth_household.id
    assert _count(db, CookingSession) == 0


def test_cooking_refuses_a_direct_batch_absent_from_safety_coverage(
    db, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user, milk_allergy=True)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    composite = _product_mapping(
        db,
        auth_household,
        auth_user,
        ingredient,
        name="Reviewed composite garlic meal kit",
        mode="COMPOSITE",
        factor_amount="1",
    )
    safe_composite_batch = _batch(
        db, auth_household, composite, "10", expiry=household_today() + timedelta(days=1)
    )
    direct = _product_mapping(
        db,
        auth_household,
        auth_user,
        ingredient,
        name="Direct garlic with milk label",
        allergens=["milk"],
    )
    unsafe_direct_batch = _batch(db, auth_household, direct, "10")

    with _local_client(db, auth_user) as client:
        response = client.post("/cooking/preview", json=_preview_request(recipe))

    assert response.status_code == 422
    assert "COOKING_STOCK_NOT_FULLY_SAFETY_EVALUATED" in response.text
    assert _count(db, CookingSession) == 0
    assert _count(db, InventoryEvent) == 0
    assert safe_composite_batch.id != unsafe_direct_batch.id


def test_two_competing_confirms_cannot_overspend_the_same_preview(
    db, engine, auth_household, auth_user
):
    _ready_profiles(db, auth_household, auth_user)
    ingredient = _garlic(db)
    recipe = _recipe(db, auth_household, auth_user, ingredient)
    product = _product_mapping(db, auth_household, auth_user, ingredient)
    _batch(db, auth_household, product, "10")
    with _local_client(db, auth_user) as client:
        preview = _preview(client, recipe)

    barrier = Barrier(2)
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def attempt(key):
        session = factory()
        try:
            request = CookingConfirmRequest(**_confirm_payload(preview, key=key))
            barrier.wait(timeout=10)
            cooking_service.confirm_cooking(session, auth_household.id, auth_user.id, request)
            return "confirmed"
        except HTTPException as exc:
            session.rollback()
            return exc.status_code
        finally:
            session.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(attempt, ["cooking-race-key-a", "cooking-race-key-b"])
        )

    assert sorted(str(result) for result in results) == ["409", "confirmed"]
    assert _count(db, CookingSession) == 1
    assert _count(db, InventoryEvent) == 1
    db.refresh(auth_household)
    assert auth_household.inventory_revision == 1


def test_cooking_requests_reject_nonfinite_servings_and_missing_record_authorization():
    with pytest.raises(ValidationError):
        CookingPreviewRequest(
            recipe_id=1,
            expected_recipe_revision=1,
            servings="Infinity",
        )
    valid_fields = {
        "preview_id": "signed-preview",
        "idempotency_key": "cooking-schema-key",
        "confirmation": "RECORD COOKING",
        "record_history": True,
    }
    with pytest.raises(ValidationError):
        CookingConfirmRequest(**{**valid_fields, "confirmation": "Cook"})
    with pytest.raises(ValidationError):
        CookingConfirmRequest(**{**valid_fields, "record_history": False})
    with pytest.raises(ValidationError):
        CookingConfirmRequest(**{**valid_fields, "idempotency_key": "  short  "})
