from datetime import date
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.cooking import CookingSession
from app.models.event import InventoryEvent
from app.models.household import Household
from app.models.ingredient import (
    Ingredient,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
)
from app.models.preferences import FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe import Recipe, RecipeRevision
from app.models.recipe_shopping import RecipeShoppingIdempotency
from app.models.shopping import ShoppingListItem
from app.schemas.preferences import FoodPreferencesInput
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.services.product_labels import product_fingerprint
from app.services.recipe_sources import recipe_source_context


def _payload(**changes):
    body = {
        "title": "Garlic rice",
        "cuisine": "Filipino",
        "content_permission": "OWNED_OR_PERMISSION_GRANTED",
        "ph_regions": ["region_unknown"],
        "servings": 2,
        "instructions": ["Prepare the ingredients.", "Cook until done."],
        "ingredients": [
            {"display_name": "garlic", "amount": 5, "unit": "g"},
            {"display_name": "rice", "amount": 100, "unit": "g"},
        ],
    }
    body.update(changes)
    return body


def _create(client, **changes):
    response = client.post("/api/v1/recipes/", json=_payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def _ready_adaptation_stock(db, household, user):
    seed_ingredient_catalog_v1(db)
    db.flush()
    garlic = db.scalar(
        select(Ingredient).where(Ingredient.normalized_name == "garlic")
    )
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
    product = Product(household_id=household.id, name="Verified garlic", unit="g")
    db.add(product)
    db.flush()
    now = datetime.now(timezone.utc)
    db.add(
        ProductIngredientMapping(
            household_id=household.id,
            product_id=product.id,
            version=1,
            is_current=True,
            mode="DIRECT",
            ingredient_id=garlic.id,
            verification_status="VERIFIED",
            method="Synthetic adaptation test evidence",
            verified_by_user_id=user.id,
            verified_at=now,
            unknown_composition=False,
        )
    )
    db.flush()
    db.add(
        ProductIngredientMappingTarget(
            household_id=household.id,
            product_id=product.id,
            mapping_version=1,
            ingredient_id=garlic.id,
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
            source_reference="Synthetic label review for adaptation test",
            reviewed_by_user_id=user.id,
            reviewed_at=now,
        )
    )
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=Decimal("100"),
        remaining_quantity=Decimal("100"),
        expiration_date=household_today() + timedelta(days=30),
    )
    db.add(batch)
    db.commit()
    rice = db.scalar(
        select(Ingredient).where(Ingredient.normalized_name == "rice")
    )
    return garlic, rice, batch


def test_adaptation_pins_same_household_parent_and_cannot_lose_lineage(client, db):
    parent = _create(client)
    child = _create(
        client,
        title="My garlic rice variation",
        adapted_from_recipe_id=parent["id"],
        adapted_from_recipe_revision=1,
    )
    updated_parent = client.put(
        f"/api/v1/recipes/{parent['id']}",
        json=_payload(expected_revision=1, title="Updated parent"),
    )
    assert updated_parent.status_code == 200, updated_parent.text
    assert child["provenance"] == "USER_ENTERED"
    assert child["adapted_from_recipe_id"] == parent["id"]
    assert child["adapted_from_recipe_revision"] == 1

    history = client.get(f"/api/v1/recipes/{child['id']}/versions/1")
    assert history.status_code == 200
    assert history.json()["adapted_from_recipe_revision"] == 1

    revised = client.put(
        f"/api/v1/recipes/{child['id']}",
        json=_payload(expected_revision=1, title="Renamed variation"),
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["revision"] == 2
    assert revised.json()["adapted_from_recipe_id"] == parent["id"]
    assert revised.json()["adapted_from_recipe_revision"] == 1

    exported = client.get("/api/v1/privacy/export")
    assert exported.status_code == 200, exported.text
    exported_child = next(
        item for item in exported.json()["recipes"] if item["id"] == child["id"]
    )
    assert exported_child["adapted_from_recipe_id"] == parent["id"]
    assert exported_child["adapted_from_recipe_revision"] == 1

    cleared = client.put(
        f"/api/v1/recipes/{child['id']}",
        json=_payload(
            expected_revision=2,
            adapted_from_recipe_id=None,
            adapted_from_recipe_revision=None,
        ),
    )
    assert cleared.status_code == 409
    assert cleared.json()["detail"] == "RECIPE_ORIGIN_IMMUTABLE"
    assert db.scalar(
        select(func.count()).select_from(RecipeRevision).where(
            RecipeRevision.recipe_id == child["id"]
        )
    ) == 2


def test_adaptation_requires_local_existing_parent_and_permission(client, db, auth_household):
    parent = _create(client)
    unpaired = client.post(
        "/api/v1/recipes/",
        json=_payload(adapted_from_recipe_id=parent["id"]),
    )
    assert unpaired.status_code == 422
    before = db.scalar(select(func.count()).select_from(Recipe))

    foreign_household = Household(name="Foreign recipe home", slug="foreign-adaptation-home")
    db.add(foreign_household)
    db.flush()
    foreign_parent = Recipe(
        household_id=foreign_household.id,
        title="Foreign parent",
        cuisine="Filipino",
        content={"content_permission": "OWNED_OR_PERMISSION_GRANTED"},
        revision=1,
        is_active=True,
    )
    db.add(foreign_parent)
    db.flush()
    db.add(
        RecipeRevision(
            household_id=foreign_household.id,
            recipe_id=foreign_parent.id,
            revision=1,
            snapshot={
                "content_permission": "OWNED_OR_PERMISSION_GRANTED",
                "provenance": "USER_ENTERED",
            },
        )
    )
    db.commit()

    foreign = client.post(
        "/api/v1/recipes/",
        json=_payload(
            adapted_from_recipe_id=foreign_parent.id,
            adapted_from_recipe_revision=1,
        ),
    )
    assert foreign.status_code == 404
    missing_revision = client.post(
        "/api/v1/recipes/",
        json=_payload(
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=999,
        ),
    )
    assert missing_revision.status_code == 404
    undeclared = client.post(
        "/api/v1/recipes/",
        json=_payload(
            content_permission="NOT_DECLARED",
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=1,
        ),
    )
    assert undeclared.status_code == 422
    assert db.scalar(select(func.count()).select_from(Recipe)) == before + 1
    assert auth_household.id != foreign_household.id


def test_adaptation_chain_is_bounded_and_cycles_fail_closed(client, db, auth_household):
    root = _create(client, title="Root recipe")
    parent = root
    first_child = None
    for depth in range(1, 5):
        parent = _create(
            client,
            title=f"Adaptation {depth}",
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=1,
        )
        if depth == 1:
            first_child = parent

    too_deep = client.post(
        "/api/v1/recipes/",
        json=_payload(
            title="Too deep",
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=1,
        ),
    )
    assert too_deep.status_code == 422
    assert too_deep.json()["detail"] == "ADAPTATION_PARENT_UNAVAILABLE"

    child = db.scalar(select(Recipe).where(Recipe.id == first_child["id"]))
    root_row = db.scalar(select(Recipe).where(Recipe.id == root["id"]))
    root_revision = db.scalar(
        select(RecipeRevision).where(
            RecipeRevision.recipe_id == root["id"], RecipeRevision.revision == 1
        )
    )
    root_row.content = {
        **root_row.content,
        "adapted_from_recipe_id": child.id,
        "adapted_from_recipe_revision": 1,
    }
    root_revision.snapshot = {
        **root_revision.snapshot,
        "adapted_from_recipe_id": child.id,
        "adapted_from_recipe_revision": 1,
    }
    db.flush()
    assert recipe_source_context(db, auth_household.id, root["id"], 1)[0] is False


def test_current_parent_permission_withdrawal_blocks_child_evaluation(client):
    parent = _create(client)
    child = _create(
        client,
        title="Permission-bound variation",
        adapted_from_recipe_id=parent["id"],
        adapted_from_recipe_revision=1,
    )
    updated = client.put(
        f"/api/v1/recipes/{parent['id']}",
        json=_payload(
            expected_revision=1,
            content_permission="NOT_DECLARED",
        ),
    )
    assert updated.status_code == 200, updated.text

    evaluation = client.post(
        f"/api/v1/recipes/{child['id']}/evaluate",
        json={"expected_recipe_revision": 1, "servings": 2},
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["result"]["decision"] == "review_required"
    assert "recipe_source_unavailable" in evaluation.json()["result"]["reasons"]


def test_adaptation_cannot_pin_undeclared_revision_after_parent_permission_is_granted(
    client,
):
    parent = _create(client, content_permission="NOT_DECLARED")
    current = client.put(
        f"/api/v1/recipes/{parent['id']}",
        json=_payload(
            expected_revision=1,
            content_permission="OWNED_OR_PERMISSION_GRANTED",
        ),
    )
    assert current.status_code == 200, current.text

    child = client.post(
        "/api/v1/recipes/",
        json=_payload(
            title="Cannot reuse undeclared history",
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=1,
        ),
    )
    assert child.status_code == 422
    assert child.json()["detail"] == "ADAPTATION_PARENT_UNAVAILABLE"


def test_user_adaptation_evaluates_shops_and_cooks_until_parent_permission_withdrawn(
    client, db, auth_household, auth_user
):
    garlic, rice, batch = _ready_adaptation_stock(db, auth_household, auth_user)
    parent = _create(
        client,
        title="Parent garlic recipe",
        servings=1,
        ingredients=[{"ingredient_id": garlic.id, "amount": 10, "unit": "g"}],
    )
    child = _create(
        client,
        title="User-authored garlic variation",
        servings=1,
        ingredients=[
            {"ingredient_id": garlic.id, "amount": 10, "unit": "g"},
            {
                "ingredient_id": rice.id,
                "amount": 50,
                "unit": "g",
                "required": False,
            },
        ],
        adapted_from_recipe_id=parent["id"],
        adapted_from_recipe_revision=1,
    )

    evaluation = client.post(
        f"/api/v1/recipes/{child['id']}/evaluate",
        json={"expected_recipe_revision": 1, "servings": 1},
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["result"]["decision"] == "eligible"

    plan = client.put(
        "/api/v1/meal-plans/weeks/2026-10-26",
        json={
            "expected_revision": None,
            "entries": [
                {
                    "meal_date": "2026-10-26",
                    "slot": "dinner",
                    "position": 0,
                    "recipe_id": child["id"],
                    "recipe_revision": child["revision"],
                    "servings": 1,
                }
            ],
        },
    )
    assert plan.status_code == 200, plan.text
    shopping = client.post(
        "/api/v1/plan-shopping/preview",
        json={
            "plan_id": plan.json()["id"],
            "expected_plan_revision": 1,
            "include_optional": True,
        },
    )
    assert shopping.status_code == 200, shopping.text
    assert shopping.json()["safety"]["decision"] == "eligible"
    assert shopping.json()["lines"]

    preview = client.post(
        "/api/v1/cooking/preview",
        json={
            "recipe_id": child["id"],
            "expected_recipe_revision": child["revision"],
            "servings": 1,
        },
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["requirements"][0]["allocations"]
    first_confirm = client.post(
        "/api/v1/cooking/confirm",
        json={
            "preview_id": preview.json()["preview_id"],
            "idempotency_key": "adaptation-confirm-0001",
            "confirmation": "RECORD COOKING",
            "record_history": True,
            "acknowledged_missing_expiry_batch_ids": preview.json()[
                "missing_expiry_batch_ids"
            ],
            "leftovers": [],
        },
    )
    assert first_confirm.status_code == 200, first_confirm.text
    assert db.scalar(select(func.count()).select_from(CookingSession)) == 1
    assert db.scalar(select(func.count()).select_from(InventoryEvent)) == 1

    stale_shopping = client.post(
        "/api/v1/plan-shopping/preview",
        json={
            "plan_id": plan.json()["id"],
            "expected_plan_revision": 1,
            "include_optional": True,
        },
    )
    assert stale_shopping.status_code == 200, stale_shopping.text
    accepted_line = stale_shopping.json()["lines"][0]

    stale_preview = client.post(
        "/api/v1/cooking/preview",
        json={
            "recipe_id": child["id"],
            "expected_recipe_revision": child["revision"],
            "servings": 1,
        },
    )
    assert stale_preview.status_code == 200, stale_preview.text

    revoked = client.put(
        f"/api/v1/recipes/{parent['id']}",
        json=_payload(
            expected_revision=1,
            content_permission="NOT_DECLARED",
            servings=1,
            ingredients=[{"ingredient_id": garlic.id, "amount": 10, "unit": "g"}],
        ),
    )
    assert revoked.status_code == 200, revoked.text
    confirmation = client.post(
        "/api/v1/cooking/confirm",
        json={
            "preview_id": stale_preview.json()["preview_id"],
            "idempotency_key": "adaptation-confirm-0002",
            "confirmation": "RECORD COOKING",
            "record_history": True,
            "acknowledged_missing_expiry_batch_ids": stale_preview.json()[
                "missing_expiry_batch_ids"
            ],
            "leftovers": [],
        },
    )
    assert confirmation.status_code == 409, confirmation.text
    assert confirmation.json()["detail"] == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(CookingSession)) == 1
    assert db.scalar(select(func.count()).select_from(InventoryEvent)) == 1
    shopping_confirmation = client.post(
        "/api/v1/plan-shopping/confirm",
        json={
            "preview_id": stale_shopping.json()["preview_id"],
            "idempotency_key": "adaptation-shop-confirm-01",
            "expected_revision": stale_shopping.json()["shopping_revision"],
            "accepted_lines": [
                {
                    "ingredient_id": accepted_line["ingredient_id"],
                    "target_quantity": "1",
                }
            ],
        },
    )
    assert shopping_confirmation.status_code == 409, shopping_confirmation.text
    assert shopping_confirmation.json()["detail"] == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0
    assert db.scalar(
        select(Household.shopping_revision).where(Household.id == auth_household.id)
    ) == 0
    assert db.scalar(
        select(InventoryBatch.remaining_quantity).where(InventoryBatch.id == batch.id)
    ) == Decimal("90.000000")


def test_ancestor_reference_linkage_and_tombstone_block_dependent_flows(
    client, db, auth_household
):
    parent = _create(client)
    child = _create(
        client,
        title="User variation",
        adapted_from_recipe_id=parent["id"],
        adapted_from_recipe_revision=1,
    )
    plan = client.put(
        "/api/v1/meal-plans/weeks/2026-10-26",
        json={
            "expected_revision": None,
            "entries": [
                {
                    "meal_date": date(2026, 10, 26).isoformat(),
                    "slot": "dinner",
                    "position": 0,
                    "recipe_id": child["id"],
                    "recipe_revision": child["revision"],
                    "servings": 2,
                }
            ],
        },
    )
    assert plan.status_code == 200, plan.text

    linked = client.put(
        f"/api/v1/recipe-sources/recipes/{parent['id']}/reference",
        json={
            "expected_revision": None,
            "expected_recipe_revision": parent["revision"],
            "url": "https://recipes.example.com/garlic-rice",
            "allow_broader_web": True,
        },
    )
    assert linked.status_code == 200, linked.text

    new_fork = client.post(
        "/api/v1/recipes/",
        json=_payload(
            title="Fork from external parent",
            adapted_from_recipe_id=parent["id"],
            adapted_from_recipe_revision=parent["revision"],
        ),
    )
    assert new_fork.status_code == 422

    evaluation = client.post(
        f"/api/v1/recipes/{child['id']}/evaluate",
        json={"expected_recipe_revision": 1, "servings": 2},
    )
    assert evaluation.status_code == 200, evaluation.text
    assert evaluation.json()["result"]["decision"] == "review_required"
    assert "recipe_source_unavailable" in evaluation.json()["result"]["reasons"]

    cooking = client.post(
        "/api/v1/cooking/preview",
        json={
            "recipe_id": child["id"],
            "expected_recipe_revision": child["revision"],
            "servings": 2,
        },
    )
    assert cooking.status_code == 422
    assert cooking.json()["detail"] == "REVIEW_REQUIRED"

    shopping = client.post(
        "/api/v1/plan-shopping/preview",
        json={"plan_id": plan.json()["id"], "expected_plan_revision": 1},
    )
    assert shopping.status_code == 422, shopping.text
    assert shopping.json()["detail"]["decision"] == "review_required"
    assert "recipe_source_unavailable" in shopping.json()["detail"]["reasons"]

    replacement = client.put(
        "/api/v1/meal-plans/weeks/2026-10-26",
        json={
            "expected_revision": 1,
            "entries": [
                {
                    "meal_date": date(2026, 10, 26).isoformat(),
                    "slot": "dinner",
                    "position": 0,
                    "recipe_id": child["id"],
                    "recipe_revision": child["revision"],
                    "servings": 2,
                }
            ],
        },
    )
    assert replacement.status_code == 409
    assert replacement.json()["detail"] == "SOURCE_NOT_AVAILABLE"

    removed = client.delete(
        f"/api/v1/recipe-sources/recipes/{parent['id']}/reference",
        params={"expected_revision": 1},
    )
    assert removed.status_code == 204
    assert recipe_source_context(db, auth_household.id, child["id"], 1)[0] is False
