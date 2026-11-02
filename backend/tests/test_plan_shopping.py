from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.plan_shopping import router as plan_shopping_router
from app.core.database import get_db
from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.ingredient import Ingredient, ProductIngredientMapping, ProductIngredientMappingTarget
from app.models.preferences import FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe_shopping import RecipeShoppingIdempotency
from app.models.recipe_source import RecipeSource, RecipeSourceReference
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.schemas.meal_plan import MealPlanReplaceRequest
from app.schemas.plan_shopping import (
    PlanShoppingConfirmRequest,
    PlanShoppingPreviewRequest,
)
from app.schemas.preferences import FoodPreferencesInput
from app.schemas.recipe import RecipeWrite
from app.schemas.recipe_shopping import RecipeShoppingConfirmRequest, RecipeShoppingPreviewRequest
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.services.meal_plans import replace_week
from app.services.plan_shopping import confirm_plan_shopping, preview_plan_shopping
from app.services.product_labels import product_fingerprint
from app.services.recipe_shopping import confirm_recipe_shopping, preview_recipe_shopping
from app.services.recipes import archive_recipe, write_recipe


WEEK_ONE = date(2026, 10, 26)
WEEK_TWO = date(2026, 11, 2)


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


def setup_ingredient(db):
    seed_ingredient_catalog_v1(db)
    db.commit()
    return db.scalar(select(Ingredient).where(Ingredient.normalized_name == "garlic"))


def write_test_recipe(
    db,
    household,
    user,
    ingredient,
    *,
    title,
    amounts,
    servings=Decimal("1"),
    expected_revision=None,
    recipe_id=None,
    content_permission="OWNED_OR_PERMISSION_GRANTED",
):
    ingredients = [
        {
            "ingredient_id": ingredient.id,
            "amount": amount,
            "unit": unit,
            "required": required,
        }
        for amount, unit, required in amounts
    ]
    return write_recipe(
        db,
        household.id,
        user.id,
        RecipeWrite(
            title=title,
            cuisine="Filipino",
            ph_regions=["region_unknown"],
            content_permission=content_permission,
            servings=servings,
            instructions=["Prepare and cook the ingredients."],
            expected_revision=expected_revision,
            ingredients=ingredients,
        ),
        recipe_id=recipe_id,
    )


def write_recipe_lines(db, household, user, *, title, lines, servings=Decimal("1")):
    return write_recipe(
        db,
        household.id,
        user.id,
        RecipeWrite(
            title=title,
            cuisine="Filipino",
            ph_regions=["region_unknown"],
            content_permission="OWNED_OR_PERMISSION_GRANTED",
            servings=servings,
            instructions=["Prepare and cook the ingredients."],
            ingredients=lines,
        ),
    )


def make_plan(db, household, user, entries, *, week_start=WEEK_ONE):
    return replace_week(
        db,
        household.id,
        user.id,
        week_start,
        MealPlanReplaceRequest(expected_revision=None, entries=entries),
    )


def plan_entry(recipe, *, week_date=WEEK_ONE, slot="dinner", position=0, servings="1"):
    return {
        "meal_date": week_date,
        "slot": slot,
        "position": position,
        "recipe_id": recipe.id,
        "recipe_revision": recipe.revision,
        "servings": servings,
    }


def add_pantry(db, household, user, ingredient, quantity):
    now = datetime.now(timezone.utc)
    product = Product(household_id=household.id, name="Reviewed garlic", unit="g")
    db.add(product)
    db.flush()
    mapping = ProductIngredientMapping(
        household_id=household.id,
        product_id=product.id,
        version=1,
        is_current=True,
        mode="DIRECT",
        ingredient_id=ingredient.id,
        verification_status="VERIFIED",
        method="Synthetic reviewed label",
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
            source_reference="Synthetic explicit label",
            reviewed_by_user_id=user.id,
            reviewed_at=now,
        )
    )
    db.add(
        InventoryBatch(
            household_id=household.id,
            product_id=product.id,
            original_quantity=quantity,
            remaining_quantity=quantity,
            expiration_date=household_today() + timedelta(days=10),
        )
    )
    db.commit()
    return product


def local_client(db, user):
    app = FastAPI()
    app.include_router(plan_shopping_router, prefix="/plan-shopping")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def preview(db, household, user, plan):
    return preview_plan_shopping(
        db,
        household.id,
        user.id,
        PlanShoppingPreviewRequest(
            plan_id=plan.id,
            expected_plan_revision=plan.revision,
            include_optional=False,
        ),
    )


def confirm_request(preview_read, ingredient_id, target, *, key):
    return PlanShoppingConfirmRequest(
        preview_id=preview_read.preview_id,
        idempotency_key=key,
        expected_revision=preview_read.shopping_revision,
        accepted_lines=[
            {"ingredient_id": ingredient_id, "target_quantity": str(target)}
        ],
    )


def test_aggregate_plan_shortage_subtracts_pantry_and_pending_once(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    first = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Garlic rice", amounts=[("3", "g", True)],
    )
    second = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Garlic soup", amounts=[("4", "g", True)],
    )
    plan = make_plan(
        db,
        auth_household,
        auth_user,
        [
            plan_entry(first, slot="lunch", position=0),
            plan_entry(second, slot="dinner", position=0),
        ],
    )
    add_pantry(db, auth_household, auth_user, ingredient, Decimal("2"))
    manual = ShoppingListItem(
        household_id=auth_household.id,
        ingredient_id=ingredient.id,
        name="Preferred garlic",
        quantity=Decimal("1"),
        unit="g",
        is_bought=False,
        notes="Keep my note",
    )
    db.add(manual)
    db.commit()

    calculated = preview(db, auth_household, auth_user, plan)
    line = next(item for item in calculated.lines if item.ingredient_id == ingredient.id)
    assert line.required_quantity == Decimal("7.000000")
    assert line.pantry_quantity == Decimal("2.000000")
    assert line.shortage == Decimal("5.000000")
    assert line.pending_quantity == Decimal("1.000000")
    assert line.target_quantity == Decimal("5.000000")
    assert line.additional_quantity == Decimal("4.000000")

    result = confirm_plan_shopping(
        db,
        auth_household.id,
        auth_user.id,
        confirm_request(calculated, ingredient.id, "5", key="aggregate-plan-key-01"),
    )
    assert [item.id for item in result.updated] == [manual.id]
    assert result.created == []
    db.expire_all()
    updated = db.get(ShoppingListItem, manual.id)
    assert updated.quantity == Decimal("5.000000")
    assert updated.notes == "Keep my note"
    assert updated.origin_plan_id is None
    assert auth_household.shopping_revision == 1


def test_optional_plan_demand_is_allocated_after_required_stock(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Garlic noodles",
        amounts=[("3", "g", True), ("4", "g", False)],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    add_pantry(db, auth_household, auth_user, ingredient, Decimal("2"))

    required_only = preview(db, auth_household, auth_user, plan)
    required_line = required_only.lines[0]
    assert required_line.required_quantity == Decimal("3.000000")
    assert required_line.shortage == Decimal("1.000000")

    with local_client(db, auth_user) as client:
        response = client.post(
            "/plan-shopping/preview",
            json={
                "plan_id": plan.id,
                "expected_plan_revision": plan.revision,
                "include_optional": True,
            },
        )
    assert response.status_code == 200, response.text
    optional_line = response.json()["lines"][0]
    assert Decimal(optional_line["required_quantity"]) == Decimal("7")
    assert Decimal(optional_line["shortage"]) == Decimal("5")
    assert Decimal(optional_line["target_quantity"]) == Decimal("5")


def test_plan_aggregates_more_than_200_raw_lines_before_availability_limit(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_recipe_lines(
        db,
        auth_household,
        auth_user,
        title="Repeated weekly ingredient lines",
        lines=[
            {"ingredient_id": ingredient.id, "amount": "1", "unit": "g", "required": True}
            for _ in range(12)
        ],
    )
    entries = [
        plan_entry(
            recipe,
            week_date=WEEK_ONE + timedelta(days=day),
            slot=slot,
        )
        for day in range(7)
        for slot in ("breakfast", "lunch", "dinner")
    ]
    assert len(entries) * len(recipe.ingredients) == 252
    plan = make_plan(db, auth_household, auth_user, entries)

    calculated = preview(db, auth_household, auth_user, plan)

    availability = calculated.safety.availability.requirements
    assert len(availability) == 1
    assert availability[0].ingredient_id == ingredient.id
    assert availability[0].unit == "g"
    assert availability[0].required_amount == Decimal("252.000000")
    assert calculated.lines[0].required_quantity == Decimal("252.000000")


def test_plan_sums_fractional_recipe_lines_exactly_before_rounding_check(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Three exact fractional servings",
        amounts=[("1", "g", True)],
        servings=Decimal("3"),
    )
    plan = make_plan(
        db,
        auth_household,
        auth_user,
        [
            plan_entry(recipe, slot=slot, servings="1")
            for slot in ("breakfast", "lunch", "dinner")
        ],
    )

    calculated = preview(db, auth_household, auth_user, plan)

    availability = calculated.safety.availability.requirements
    assert len(availability) == 1
    assert availability[0].unit == "g"
    assert availability[0].required_amount == Decimal("1.000000")
    assert calculated.lines[0].required_quantity == Decimal("1.000000")


def test_plan_converts_units_to_curated_default_before_aggregation(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_recipe_lines(
        db,
        auth_household,
        auth_user,
        title="Mixed compatible units",
        lines=[
            {"ingredient_id": ingredient.id, "amount": "500", "unit": "g", "required": True},
            {"ingredient_id": ingredient.id, "amount": "1", "unit": "kg", "required": True},
        ],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])

    calculated = preview(db, auth_household, auth_user, plan)

    availability = calculated.safety.availability.requirements
    assert len(availability) == 1
    assert availability[0].unit == ingredient.default_unit == "g"
    assert availability[0].required_amount == Decimal("1500.000000")


def test_unresolved_plan_ingredient_remains_manual_review(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    recipe = write_recipe_lines(
        db,
        auth_household,
        auth_user,
        title="Unresolved pantry ingredient",
        lines=[
            {
                "display_name": "Uncatalogued pantry powder",
                "amount": "1",
                "unit": "g",
                "required": True,
            }
        ],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])

    with pytest.raises(HTTPException) as review:
        preview(db, auth_household, auth_user, plan)

    assert review.value.status_code == 422
    assert review.value.detail["code"] == "REVIEW_REQUIRED"


def test_plan_scaling_keeps_exact_decimal_fractions_and_rejects_rounding(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    exact_recipe = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Exact fractional scale",
        amounts=[("3", "g", True)],
        servings=Decimal("3"),
    )
    exact_plan = make_plan(
        db,
        auth_household,
        auth_user,
        [plan_entry(exact_recipe, servings="1")],
    )
    exact = preview(db, auth_household, auth_user, exact_plan)
    assert exact.lines[0].required_quantity == Decimal("1.000000")

    recurring_recipe = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Nonterminating fractional scale",
        amounts=[("1", "g", True)],
        servings=Decimal("3"),
    )
    recurring_plan = make_plan(
        db,
        auth_household,
        auth_user,
        [plan_entry(recurring_recipe, week_date=WEEK_TWO, servings="1")],
        week_start=WEEK_TWO,
    )
    with pytest.raises(HTTPException) as review:
        preview(db, auth_household, auth_user, recurring_plan)
    assert review.value.status_code == 422
    assert review.value.detail["code"] == "REVIEW_REQUIRED"
    assert review.value.detail["reason"] == "plan_serving_scale_not_exactly_representable"


def test_plan_confirmation_stales_after_move_and_replays_before_token_expiry(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Garlic toast", amounts=[("3", "g", True)],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    old_preview = preview(db, auth_household, auth_user, plan)
    moved = replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_ONE,
        MealPlanReplaceRequest(
            expected_revision=plan.revision,
            entries=[plan_entry(recipe, week_date=date(2026, 10, 27), slot="breakfast")],
        ),
    )
    with pytest.raises(HTTPException) as stale:
        confirm_plan_shopping(
            db,
            auth_household.id,
            auth_user.id,
            confirm_request(old_preview, ingredient.id, "3", key="stale-plan-key-001"),
        )
    assert stale.value.status_code == 409
    assert stale.value.detail == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(RecipeShoppingIdempotency)) == 0
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0

    fresh = preview(db, auth_household, auth_user, moved)
    request = confirm_request(fresh, ingredient.id, "3", key="replay-plan-key-001")
    first = confirm_plan_shopping(db, auth_household.id, auth_user.id, request)
    with patch(
        "app.services.plan_shopping._decode_preview",
        side_effect=HTTPException(status_code=409, detail="STALE_PREVIEW"),
    ):
        replay = confirm_plan_shopping(db, auth_household.id, auth_user.id, request)
    assert replay == first
    assert len(first.created) == 1
    assert first.created[0].origin_plan_id == plan.id
    assert first.created[0].origin_plan_revision == moved.revision
    assert first.created[0].origin_recipe_id is None
    assert first.created[0].origin_recipe_revision is None
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 1


def test_plan_preview_and_confirmation_use_pinned_recipe_revision_after_edit(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Pinned garlic rice", amounts=[("3", "g", True)],
    )
    plan = make_plan(
        db,
        auth_household,
        auth_user,
        [plan_entry(recipe)],
    )
    calculated = preview(db, auth_household, auth_user, plan)
    current = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Pinned garlic rice updated",
        amounts=[("99", "g", True)],
        expected_revision=recipe.revision,
        recipe_id=recipe.id,
    )
    assert current.revision == recipe.revision + 1

    result = confirm_plan_shopping(
        db,
        auth_household.id,
        auth_user.id,
        confirm_request(calculated, ingredient.id, "3", key="pinned-revision-key-01"),
    )
    assert len(result.created) == 1
    assert Decimal(str(result.created[0].quantity)) == Decimal("3.000000")
    assert result.created[0].origin_plan_revision == plan.revision


@pytest.mark.parametrize("change", ["archive", "source_revocation"])
def test_archived_recipe_or_revoked_source_invalidates_plan_preview(
    db, auth_household, auth_user, change
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title=f"Gated recipe {change}", amounts=[("3", "g", True)],
    )
    if change == "source_revocation":
        host = "plan-revocation.synthetic.example.com"
        source = RecipeSource(
            canonical_host=host,
            publisher_name="Synthetic plan source",
            revision=1,
            policy={
                "review_status": "candidate",
                "tier": "filipino_priority",
                "enabled": False,
                "allowed_hosts": [host],
                "access_mode": "search_link_only",
                "disabled_reason": "Synthetic candidate",
            },
        )
        db.add(source)
        db.flush()
        db.add(
            RecipeSourceReference(
                household_id=auth_household.id,
                recipe_id=recipe.id,
                source_id=source.id,
                canonical_url=f"https://{host}/recipe",
                author=None,
                revision=1,
                is_active=True,
                broader_web_permission=True,
                linked_by_user_id=auth_user.id,
            )
        )
        db.commit()
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    calculated = preview(db, auth_household, auth_user, plan)

    if change == "archive":
        archive_recipe(db, auth_household.id, auth_user.id, recipe.id, recipe.revision)
    else:
        source.policy = {
            **source.policy,
            "review_status": "suspended",
            "enabled": False,
            "disabled_reason": "Synthetic policy revocation",
        }
        source.revision += 1
        db.commit()

    with pytest.raises(HTTPException) as stale:
        confirm_plan_shopping(
            db,
            auth_household.id,
            auth_user.id,
            confirm_request(
                calculated, ingredient.id, "3", key=f"revoked-plan-{change}-001"
            ),
        )
    assert stale.value.status_code == 409
    assert stale.value.detail == "STALE_PREVIEW"
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0

    with pytest.raises(HTTPException) as review:
        preview(db, auth_household, auth_user, plan)
    assert review.value.status_code == 422
    assert review.value.detail["code"] == "REVIEW_REQUIRED"


def test_plan_preview_rechecks_current_recipe_permission_after_revision_edit(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Pinned permission revision",
        amounts=[("3", "g", True)],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    write_test_recipe(
        db,
        auth_household,
        auth_user,
        ingredient,
        title="Permission withdrawn",
        amounts=[("3", "g", True)],
        expected_revision=recipe.revision,
        recipe_id=recipe.id,
        content_permission="NOT_DECLARED",
    )

    with pytest.raises(HTTPException) as review:
        preview(db, auth_household, auth_user, plan)

    assert review.value.status_code == 422
    assert review.value.detail["code"] == "REVIEW_REQUIRED"
    assert "recipe_content_permission_not_declared" in review.value.detail["reasons"]


def test_plan_preview_is_household_scoped(db, auth_household, auth_user):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Scoped plan recipe", amounts=[("3", "g", True)],
    )
    local_plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    foreign_user = User(
        email="foreign-plan-shopping@example.test",
        hashed_password="not-used",
        is_active=True,
    )
    db.add(foreign_user)
    db.flush()
    foreign_household = Household(name="Foreign plan home", slug="foreign-plan-shopping-home")
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
    foreign_recipe = write_test_recipe(
        db,
        foreign_household,
        foreign_user,
        ingredient,
        title="Foreign scoped recipe",
        amounts=[("3", "g", True)],
    )
    foreign_plan = make_plan(
        db, foreign_household, foreign_user, [plan_entry(foreign_recipe)]
    )
    assert local_plan.id != foreign_plan.id
    with pytest.raises(HTTPException) as hidden:
        preview_plan_shopping(
            db,
            auth_household.id,
            auth_user.id,
            PlanShoppingPreviewRequest(
                plan_id=foreign_plan.id,
                expected_plan_revision=foreign_plan.revision,
            ),
        )
    assert hidden.value.status_code == 404


def test_recipe_and_plan_confirmations_cannot_reuse_each_others_key(
    db, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Cross workflow recipe", amounts=[("3", "g", True)],
    )
    plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    recipe_preview = preview_recipe_shopping(
        db,
        auth_household.id,
        auth_user.id,
        RecipeShoppingPreviewRequest(
            recipe_id=recipe.id,
            expected_recipe_revision=recipe.revision,
            servings=Decimal("1"),
            include_optional=False,
        ),
    )
    key = "shared-household-key-01"
    confirm_recipe_shopping(
        db,
        auth_household.id,
        auth_user.id,
        RecipeShoppingConfirmRequest(
            preview_id=recipe_preview.preview_id,
            idempotency_key=key,
            expected_revision=recipe_preview.shopping_revision,
            accepted_lines=[],
        ),
    )
    plan_preview = preview(db, auth_household, auth_user, plan)
    with pytest.raises(HTTPException) as collision:
        confirm_plan_shopping(
            db,
            auth_household.id,
            auth_user.id,
            PlanShoppingConfirmRequest(
                preview_id=plan_preview.preview_id,
                idempotency_key=key,
                expected_revision=plan_preview.shopping_revision,
                accepted_lines=[],
            ),
        )
    assert collision.value.status_code == 409
    assert collision.value.detail == "IDEMPOTENCY_KEY_REUSED"


def test_concurrent_plan_confirms_reconcile_pending_purchase_once(
    db, engine, auth_household, auth_user
):
    ready_profiles(db, auth_household, auth_user)
    ingredient = setup_ingredient(db)
    recipe = write_test_recipe(
        db, auth_household, auth_user, ingredient,
        title="Concurrent plan rice", amounts=[("5", "g", True)],
    )
    first_plan = make_plan(db, auth_household, auth_user, [plan_entry(recipe)])
    second_plan = make_plan(
        db, auth_household, auth_user, [plan_entry(recipe, week_date=WEEK_TWO)],
        week_start=WEEK_TWO,
    )
    first_preview = preview(db, auth_household, auth_user, first_plan)
    second_preview = preview(db, auth_household, auth_user, second_plan)
    first_request = confirm_request(
        first_preview, ingredient.id, "5", key="concurrent-plan-first-001"
    )
    second_request = confirm_request(
        second_preview, ingredient.id, "5", key="concurrent-plan-second-001"
    )
    household_id, actor_id = auth_household.id, auth_user.id
    db.rollback()
    barrier = Barrier(2)

    def confirm_once(args):
        plan_request, = args
        with Session(engine, autoflush=False, expire_on_commit=False) as independent:
            barrier.wait(timeout=8)
            try:
                result = confirm_plan_shopping(
                    independent, household_id, actor_id, plan_request
                )
                return ("ok", result.model_dump(mode="json"))
            except HTTPException as exc:
                independent.rollback()
                return ("http", exc.status_code, exc.detail)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(confirm_once, [(first_request,), (second_request,)]))
    assert sum(result[0] == "ok" for result in results) == 1
    stale = next(result for result in results if result[0] == "http")
    assert stale[1:] == (409, "STALE_PREVIEW")
    db.expire_all()
    items = db.scalars(
        select(ShoppingListItem).where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.is_bought.is_(False),
        )
    ).all()
    assert len(items) == 1
    assert items[0].quantity == Decimal("5.000000")
