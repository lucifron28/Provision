"""Aggregate a pinned weekly plan, then reuse recipe-shopping reconciliation."""

from decimal import Decimal
from fractions import Fraction
import hmac

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanRevision
from app.models.recipe import Recipe, RecipeRevision
from app.models.recipe_shopping import RecipeShoppingIdempotency
from app.models.user import User
from app.schemas.food_safety import FoodSafetyRequest
from app.schemas.ingredients import IngredientRequirementInput
from app.schemas.plan_shopping import (
    PlanShoppingConfirmRead,
    PlanShoppingConfirmRequest,
    PlanShoppingPreviewRead,
    PlanShoppingPreviewRequest,
)
from app.services.allergen_policy import evaluate_food_safety
from app.services.household_writes import bump_shopping_revision, lock_household_write
from app.services.ingredient_matching import normalize_ingredient_name, resolve_ingredient
from app.services.meal_plans import get_plan_in_session
from app.services.recipe_shopping import (
    _apply_accepted_line,
    _build_lines,
    _context_fingerprint_for_scope,
    _decode_preview,
    _encode_preview,
    _is_quantity_representable,
    _lock_curated_tables,
    _readonly_snapshot,
    _request_hash,
)
from app.services.recipe_sources import recipe_source_context
from app.services.units import UnitConversionError, convert_amount, normalize_unit
from app.schemas.recipe import RecipeRead


_PLAN_PREVIEW_PURPOSE = "plan-shopping-preview"


def _plan_entry_query(household_id: int, plan_id: int):
    return (
        select(MealPlanEntry)
        .where(
            MealPlanEntry.household_id == household_id,
            MealPlanEntry.plan_id == plan_id,
        )
        .order_by(
            MealPlanEntry.meal_date,
            MealPlanEntry.slot,
            MealPlanEntry.position,
            MealPlanEntry.id,
        )
        .execution_options(populate_existing=True)
    )


_REVIEW_UNIT = "__review_required__"
_QUANTITY_SCALE = 1_000_000


def _fraction_to_quantity(amount: Fraction) -> Decimal | None:
    scaled = amount * _QUANTITY_SCALE
    if scaled.denominator != 1:
        return None
    quantity = Decimal(scaled.numerator).scaleb(-6)
    if quantity <= 0 or not _is_quantity_representable(quantity):
        return None
    return quantity


def _scaled_requirements(
    db: Session,
    entries: list[MealPlanEntry],
    recipe_snapshots: dict[tuple[int, int], RecipeRead],
    include_optional: bool,
) -> list[IngredientRequirementInput]:
    groups: dict[tuple, dict] = {}
    resolution_cache = {}
    resolved_ingredient_ids: set[int] = set()
    for entry in entries:
        recipe = recipe_snapshots[(entry.recipe_id, entry.recipe_revision)]
        serving_ratio = Fraction(entry.servings) / Fraction(recipe.servings)
        for ingredient in recipe.ingredients:
            if not ingredient.required and not include_optional:
                continue
            if ingredient.ingredient_id is not None:
                resolution_key = ("id", ingredient.ingredient_id)
                resolution = resolution_cache.get(resolution_key)
                if resolution is None:
                    resolution = resolve_ingredient(db, ingredient_id=ingredient.ingredient_id)
                    resolution_cache[resolution_key] = resolution
            else:
                normalized_name = normalize_ingredient_name(ingredient.display_name)
                resolution_key = ("name", normalized_name)
                resolution = resolution_cache.get(resolution_key)
                if resolution is None:
                    resolution = resolve_ingredient(db, display_name=ingredient.display_name)
                    resolution_cache[resolution_key] = resolution

            if resolution.ingredient is not None:
                curated = resolution.ingredient
                key = ("canonical", curated.id, ingredient.required)
                resolved_ingredient_ids.add(curated.id)
                group = groups.setdefault(
                    key,
                    {
                        "ingredient_id": curated.id,
                        "display_name": None,
                        "unit": curated.default_unit,
                        "required": ingredient.required,
                        "amount": Fraction(0),
                        "requires_review": False,
                        "resolved": True,
                    },
                )
                try:
                    default_unit = normalize_unit(curated.default_unit or "")
                    converted = convert_amount(
                        ingredient.amount, ingredient.unit, default_unit
                    )
                except UnitConversionError:
                    group["requires_review"] = True
                    continue
                group["unit"] = default_unit
                group["amount"] += Fraction(converted) * serving_ratio
                continue

            unit_key = " ".join(ingredient.unit.casefold().split())
            try:
                unit_key = normalize_unit(ingredient.unit)
            except UnitConversionError:
                pass
            if ingredient.ingredient_id is not None:
                key = (
                    "unresolved-id",
                    ingredient.ingredient_id,
                    unit_key,
                    ingredient.required,
                )
            else:
                key = (
                    "unresolved-name",
                    normalize_ingredient_name(ingredient.display_name),
                    unit_key,
                    ingredient.required,
                )
            group = groups.setdefault(
                key,
                {
                    "ingredient_id": ingredient.ingredient_id,
                    "display_name": ingredient.display_name if ingredient.ingredient_id is None else None,
                    "unit": unit_key,
                    "required": ingredient.required,
                    "amount": Fraction(0),
                    "requires_review": False,
                    "resolved": False,
                },
            )
            group["amount"] += Fraction(ingredient.amount) * serving_ratio

    if len(resolved_ingredient_ids) > 200:
        raise HTTPException(status_code=422, detail="PLAN_REQUIREMENT_LIMIT_EXCEEDED")

    requirements: list[IngredientRequirementInput] = []
    for group in groups.values():
        amount = _fraction_to_quantity(group["amount"])
        if group["resolved"] and not group["requires_review"] and amount is None:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_REQUIRED",
                    "reason": "plan_serving_scale_not_exactly_representable",
                },
            )
        requires_review = group["requires_review"] or amount is None
        requirements.append(
            IngredientRequirementInput(
                ingredient_id=group["ingredient_id"],
                display_name=group["display_name"],
                amount=Decimal("1") if requires_review else amount,
                unit=_REVIEW_UNIT if requires_review else group["unit"],
                required=group["required"],
            )
        )
        if len(requirements) > 200:
            raise HTTPException(status_code=422, detail="PLAN_REQUIREMENT_LIMIT_EXCEEDED")
    if not requirements:
        raise HTTPException(status_code=422, detail="PLAN_HAS_NO_INCLUDED_REQUIREMENTS")
    return requirements


def _scope_snapshot(
    plan: MealPlan,
    plan_revision: MealPlanRevision,
    entries: list[MealPlanEntry],
) -> dict:
    return {
        "workflow": _PLAN_PREVIEW_PURPOSE,
        "plan": {
            "id": plan.id,
            "week_start": plan.week_start.isoformat(),
            "revision": plan.revision,
            "is_active": plan.is_active,
        },
        "plan_revision_snapshot": plan_revision.snapshot,
        "entries": [
            {
                "id": entry.id,
                "meal_date": entry.meal_date.isoformat(),
                "slot": entry.slot,
                "position": entry.position,
                "recipe_id": entry.recipe_id,
                "recipe_revision": entry.recipe_revision,
                "servings": format(entry.servings, "f"),
            }
            for entry in entries
        ],
    }


def _preview_context(
    db: Session,
    household_id: int,
    actor_id: int,
    request: PlanShoppingPreviewRequest,
):
    active_membership = db.scalar(
        select(HouseholdMembership.id)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id,
            User.is_active.is_(True),
        )
    )
    if active_membership is None:
        raise HTTPException(status_code=403, detail="Active household membership is required")

    plan = db.scalar(
        select(MealPlan)
        .where(MealPlan.household_id == household_id, MealPlan.id == request.plan_id)
        .execution_options(populate_existing=True)
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    if not plan.is_active:
        raise HTTPException(status_code=409, detail="PLAN_ARCHIVED")
    if plan.revision != request.expected_plan_revision:
        raise HTTPException(status_code=409, detail="PLAN_REVISION_CONFLICT")

    entries = db.scalars(_plan_entry_query(household_id, plan.id)).all()
    if not entries:
        raise HTTPException(status_code=422, detail="PLAN_HAS_NO_MEALS")
    current_plan_revision = db.scalar(
        select(MealPlanRevision)
        .where(
            MealPlanRevision.household_id == household_id,
            MealPlanRevision.plan_id == plan.id,
            MealPlanRevision.revision == plan.revision,
        )
        .execution_options(populate_existing=True)
    )
    if current_plan_revision is None:
        raise HTTPException(status_code=409, detail="PLAN_REVISION_CONFLICT")

    recipe_ids = {entry.recipe_id for entry in entries}
    recipe_revision_keys = {(entry.recipe_id, entry.recipe_revision) for entry in entries}
    recipes = {
        recipe.id: recipe
        for recipe in db.scalars(
            select(Recipe)
            .where(Recipe.household_id == household_id, Recipe.id.in_(recipe_ids))
            .execution_options(populate_existing=True)
        ).all()
    }
    revision_rows = {
        (row.recipe_id, row.revision): row
        for row in db.scalars(
            select(RecipeRevision)
            .where(
                RecipeRevision.household_id == household_id,
                RecipeRevision.recipe_id.in_(recipe_ids),
            )
            .execution_options(populate_existing=True)
        ).all()
        if (row.recipe_id, row.revision) in recipe_revision_keys
    }
    if set(revision_rows) != recipe_revision_keys:
        raise HTTPException(status_code=409, detail="PINNED_RECIPE_REVISION_MISSING")
    snapshots = {
        key: RecipeRead.model_validate(row.snapshot) for key, row in revision_rows.items()
    }

    gate_reasons: set[str] = set()
    for recipe_id in recipe_ids:
        recipe = recipes.get(recipe_id)
        if recipe is None:
            raise HTTPException(status_code=404, detail="Household recipe not found")
        if not recipe.is_active:
            gate_reasons.add("planned_recipe_archived")
        if recipe.content.get("content_permission") != "OWNED_OR_PERMISSION_GRANTED":
            gate_reasons.add("recipe_content_permission_not_declared")
        for revision_key in (key for key in recipe_revision_keys if key[0] == recipe_id):
            if snapshots[revision_key].content_permission != "OWNED_OR_PERMISSION_GRANTED":
                gate_reasons.add("recipe_content_permission_not_declared")
        source_allowed = all(
            recipe_source_context(
                db, household_id, recipe_id, recipe_revision=revision
            )[0]
            for pinned_recipe_id, revision in recipe_revision_keys
            if pinned_recipe_id == recipe_id
        )
        if not source_allowed:
            gate_reasons.add("recipe_source_unavailable")

    requirements = _scaled_requirements(
        db, entries, snapshots, request.include_optional
    )
    safety = evaluate_food_safety(
        db,
        household_id,
        FoodSafetyRequest(
            recipe_servings=Decimal("1"),
            servings=Decimal("1"),
            diner_user_ids=request.diner_user_ids,
            requirements=requirements,
        ),
    )
    if gate_reasons:
        if safety.decision != "blocked":
            safety.decision = "review_required"
        safety.reasons = sorted(set(safety.reasons) | gate_reasons)

    household = db.get(Household, household_id)
    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")
    lines, unlinked = _build_lines(db, household_id, safety.availability)
    scope_context = _scope_snapshot(plan, current_plan_revision, entries)
    fingerprint = _context_fingerprint_for_scope(
        db,
        household_id,
        recipe_ids=recipe_ids,
        input_data=request.model_dump(mode="json"),
        safety=safety,
        lines=lines,
        unlinked=unlinked,
        scope_context=scope_context,
        pinned_revision_keys=recipe_revision_keys,
    )
    plan_read = get_plan_in_session(db, household_id, plan.id)
    return plan, entries, plan_read, safety, household, lines, unlinked, fingerprint


def preview_plan_shopping(
    db: Session,
    household_id: int,
    actor_id: int,
    request: PlanShoppingPreviewRequest,
) -> PlanShoppingPreviewRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        plan, entries, plan_read, safety, household, lines, unlinked, fingerprint = _preview_context(
            snapshot, household_id, actor_id, request
        )
        if safety.decision != "eligible":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_REQUIRED",
                    "decision": safety.decision,
                    "reasons": safety.reasons,
                },
            )
        pinned_revisions = sorted(
            {f"{entry.recipe_id}:{entry.recipe_revision}" for entry in entries}
        )
        token, expires_at = _encode_preview(
            household_id,
            actor_id,
            request,
            household.shopping_revision,
            household.inventory_revision,
            fingerprint,
            purpose=_PLAN_PREVIEW_PURPOSE,
            extra_claims={
                "plan_id": plan.id,
                "plan_revision": plan.revision,
                "pinned_recipe_revisions": pinned_revisions,
            },
        )
        return PlanShoppingPreviewRead(
            preview_id=token,
            expires_at=expires_at,
            plan_id=plan.id,
            plan_revision=plan.revision,
            week_start=plan.week_start,
            shopping_revision=household.shopping_revision,
            inventory_revision=household.inventory_revision,
            entries=plan_read.entries,
            safety=safety,
            lines=lines,
            unlinked_manual_items=unlinked,
        )


def confirm_plan_shopping(
    db: Session,
    household_id: int,
    actor_id: int,
    request: PlanShoppingConfirmRequest,
) -> PlanShoppingConfirmRead:
    household = lock_household_write(db, household_id, actor_id=actor_id)
    request_hash = _request_hash(
        actor_id, household_id, request, workflow="plan-shopping-v1"
    )
    existing = db.scalar(
        select(RecipeShoppingIdempotency)
        .where(
            RecipeShoppingIdempotency.household_id == household_id,
            RecipeShoppingIdempotency.idempotency_key == request.idempotency_key,
        )
        .execution_options(populate_existing=True)
    )
    if existing is not None:
        if existing.actor_user_id != actor_id or not hmac.compare_digest(
            existing.request_hash, request_hash
        ):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
        return PlanShoppingConfirmRead.model_validate(existing.response_snapshot)

    if request.expected_revision != household.shopping_revision:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    claims = _decode_preview(request.preview_id, purpose=_PLAN_PREVIEW_PURPOSE)
    plan_id = claims.get("plan_id")
    plan_revision = claims.get("plan_revision")
    if (
        claims.get("household_id") != household_id
        or claims.get("actor_user_id") != actor_id
        or claims.get("shopping_revision") != household.shopping_revision
        or claims.get("inventory_revision") != household.inventory_revision
        or claims.get("shopping_revision") != request.expected_revision
        or not isinstance(plan_id, int)
        or not isinstance(plan_revision, int)
    ):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    try:
        preview_request = PlanShoppingPreviewRequest.model_validate(claims["input"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
    if preview_request.plan_id != plan_id or preview_request.expected_plan_revision != plan_revision:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    _lock_curated_tables(db)
    try:
        plan, entries, _plan_read, safety, current_household, lines, unlinked, fingerprint = (
            _preview_context(db, household_id, actor_id, preview_request)
        )
    except HTTPException as exc:
        if exc.status_code in {403, 404, 409, 422}:
            raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
        raise
    if (
        plan.id != plan_id
        or plan.revision != plan_revision
        or current_household.shopping_revision != claims.get("shopping_revision")
        or current_household.inventory_revision != claims.get("inventory_revision")
        or not hmac.compare_digest(fingerprint, str(claims.get("fingerprint", "")))
        or safety.decision != "eligible"
    ):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    lines_by_id = {
        line.ingredient_id: line for line in lines if line.ingredient_id is not None
    }
    response = PlanShoppingConfirmRead(
        preview_id=request.preview_id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        shopping_revision=household.shopping_revision,
    )
    for accepted in request.accepted_lines:
        line = lines_by_id.get(accepted.ingredient_id)
        if line is None:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
        _apply_accepted_line(
            db,
            household_id,
            None,
            line,
            accepted,
            response,
            origin_plan=(plan.id, plan.revision),
        )

    changed_any = bool(response.created or response.updated or response.consolidated)
    if changed_any:
        bump_shopping_revision(db, household_id)
        response.shopping_revision = household.shopping_revision

    db.add(
        RecipeShoppingIdempotency(
            household_id=household_id,
            actor_user_id=actor_id,
            idempotency_key=request.idempotency_key,
            request_hash=request_hash,
            response_snapshot=response.model_dump(mode="json"),
        )
    )
    db.commit()
    return response
