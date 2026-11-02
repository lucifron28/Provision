"""Read-only cooking previews and atomic, explicitly authorized confirmations."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, DecimalException, InvalidOperation, localcontext
import hashlib
import hmac
import json
import uuid

import jwt
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import household_today
from app.models.allergens import IngredientAllergen, IngredientDerivative
from app.models.batch import InventoryBatch
from app.models.cooking import CookingConsumption, CookingIdempotency, CookingSession
from app.models.event import InventoryEvent
from app.models.household import Household, HouseholdMembership
from app.models.ingredient import (
    Ingredient,
    IngredientAlias,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
    ProductPackageFactor,
)
from app.models.leftover import Leftover
from app.models.preferences import FoodAllergy, FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe import Recipe, RecipeIngredient, RecipeRevision
from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.models.location import StorageLocation
from app.models.user import User
from app.schemas.cooking import (
    CookingBatchAllocationRead,
    CookingConfirmRead,
    CookingConfirmRequest,
    CookingConsumptionRead,
    CookingPreviewRead,
    CookingPreviewRequest,
    CookingRequirementRead,
    CookingSessionRead,
)
from app.schemas.food_safety import FoodSafetyRequest
from app.schemas.ingredients import IngredientRequirementInput
from app.schemas.leftover import LeftoverCreate
from app.services.allergen_policy import evaluate_food_safety
from app.services.household_writes import bump_inventory_revision, lock_household_write
from app.services.ingredient_matching import resolve_ingredient
from app.services.inventory import consume_batch_no_commit
from app.services.leftovers import create_leftover_no_commit, read_leftover
from app.services.recipe_sources import recipe_source_context
from app.services.recipes import get_recipe
from app.services.units import UnitConversionError, convert_amount, normalize_unit


_PREVIEW_PURPOSE = "cooking-preview"
_PREVIEW_TTL = timedelta(minutes=10)
_GLOBAL_TABLES = (
    "ingredients",
    "ingredient_allergens",
    "ingredient_aliases",
    "ingredient_derivatives",
    "recipe_sources",
    "recipe_source_reviews",
)


@contextmanager
def _readonly_snapshot(bind):
    if not isinstance(bind, Engine) or bind.dialect.name != "postgresql":
        raise RuntimeError("Cooking previews require PostgreSQL")
    snapshot_bind = bind.execution_options(isolation_level="REPEATABLE READ")
    with Session(bind=snapshot_bind, autoflush=False, expire_on_commit=False) as snapshot:
        with snapshot.begin():
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
            yield snapshot


def _json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return value


def _model_row(row) -> dict:
    return {
        column.name: _json_value(getattr(row, column.name))
        for column in row.__table__.columns
    }


def _rows(db: Session, model, *conditions) -> list[dict]:
    statement = select(model)
    if conditions:
        statement = statement.where(*conditions)
    return [
        _model_row(row)
        for row in db.scalars(
            statement.order_by(model.id).execution_options(populate_existing=True)
        ).all()
    ]


def _requirement_fingerprint(requirements: list[CookingRequirementRead]) -> list[dict]:
    return [item.model_dump(mode="json") for item in requirements]


def _context_fingerprint(
    db: Session,
    household_id: int,
    actor_id: int,
    request: CookingPreviewRequest,
    recipe_id: int,
    recipe_revision: int,
    safety,
    requirements: list[CookingRequirementRead],
) -> str:
    profile_ids = select(FoodPreference.id).where(
        FoodPreference.household_id == household_id
    )
    member_rows = db.execute(
        select(HouseholdMembership, User)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(HouseholdMembership.household_id == household_id)
        .order_by(HouseholdMembership.user_id)
        .execution_options(populate_existing=True)
    ).all()
    context = {
        "manila_date": household_today().isoformat(),
        "actor_id": actor_id,
        "request": request.model_dump(mode="json"),
        "household": _rows(db, Household, Household.id == household_id),
        "members": [
            {"membership": _model_row(membership), "user": {"id": user.id, "is_active": user.is_active}}
            for membership, user in member_rows
        ],
        "profiles": _rows(db, FoodPreference, FoodPreference.household_id == household_id),
        "allergies": _rows(db, FoodAllergy, FoodAllergy.profile_id.in_(profile_ids)),
        "recipe": _rows(db, Recipe, Recipe.household_id == household_id, Recipe.id == recipe_id),
        "recipe_ingredients": _rows(
            db,
            RecipeIngredient,
            RecipeIngredient.household_id == household_id,
            RecipeIngredient.recipe_id == recipe_id,
        ),
        "recipe_revision": _rows(
            db,
            RecipeRevision,
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == recipe_id,
            RecipeRevision.revision == recipe_revision,
        ),
        "source_reference": _rows(
            db,
            RecipeSourceReference,
            RecipeSourceReference.household_id == household_id,
            RecipeSourceReference.recipe_id == recipe_id,
        ),
        "sources": _rows(db, RecipeSource),
        "source_reviews": _rows(db, RecipeSourceReview),
        "ingredients": _rows(db, Ingredient),
        "ingredient_aliases": _rows(db, IngredientAlias),
        "ingredient_allergens": _rows(db, IngredientAllergen),
        "ingredient_derivatives": _rows(db, IngredientDerivative),
        "products": _rows(db, Product, Product.household_id == household_id),
        "batches": _rows(db, InventoryBatch, InventoryBatch.household_id == household_id),
        "mappings": _rows(
            db,
            ProductIngredientMapping,
            ProductIngredientMapping.household_id == household_id,
        ),
        "mapping_targets": _rows(
            db,
            ProductIngredientMappingTarget,
            ProductIngredientMappingTarget.household_id == household_id,
        ),
        "package_factors": _rows(
            db,
            ProductPackageFactor,
            ProductPackageFactor.household_id == household_id,
        ),
        "labels": _rows(db, ProductAllergenLabel, ProductAllergenLabel.household_id == household_id),
        "locations": _rows(db, StorageLocation, StorageLocation.household_id == household_id),
        "safety": safety.model_dump(mode="json"),
        "requirements": _requirement_fingerprint(requirements),
    }
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_active_member(db: Session, household_id: int, actor_id: int) -> None:
    authorized = db.scalar(
        select(HouseholdMembership.id)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id,
            User.is_active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if authorized is None:
        raise HTTPException(status_code=403, detail="Active household membership is required")


def _recipe_snapshot(db: Session, household_id: int, request: CookingPreviewRequest):
    recipe = get_recipe(db, household_id, request.recipe_id)
    if not recipe.is_active or recipe.revision != request.expected_recipe_revision:
        raise HTTPException(status_code=409, detail="RECIPE_REVISION_CONFLICT")
    revision = db.scalar(
        select(RecipeRevision)
        .where(
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == request.recipe_id,
            RecipeRevision.revision == request.expected_recipe_revision,
        )
        .execution_options(populate_existing=True)
    )
    if revision is None:
        raise HTTPException(status_code=409, detail="RECIPE_REVISION_CONFLICT")
    return recipe, revision.snapshot


def _source_allowed(
    db: Session, household_id: int, recipe_id: int, recipe_revision: int
):
    allowed, _priority, reference = recipe_source_context(
        db, household_id, recipe_id, recipe_revision=recipe_revision
    )
    return allowed, reference


def _scale(amount: Decimal, servings: Decimal, recipe_servings: Decimal) -> Decimal:
    with localcontext() as context:
        context.prec = 50
        return amount * servings / recipe_servings


def _build_requirements(db: Session, recipe_read: dict, request: CookingPreviewRequest):
    ingredients = recipe_read.get("ingredients", [])
    if not ingredients:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    overrides = {item.requirement_index: item for item in request.actual_amount_overrides}
    if any(index >= len(ingredients) for index in overrides):
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")

    grouped: dict[int, dict] = {}
    safety_requirements: list[IngredientRequirementInput] = []
    included_indexes: set[int] = set()
    recipe_servings = Decimal(str(recipe_read["servings"]))
    for index, line in enumerate(ingredients):
        required = bool(line.get("required", True))
        if not required and not request.include_optional:
            if index in overrides:
                raise HTTPException(status_code=422, detail="Override targets an excluded optional ingredient")
            continue

        ingredient_id = line.get("ingredient_id")
        display_name = line.get("display_name")
        resolution = resolve_ingredient(db, ingredient_id=ingredient_id, display_name=display_name)
        ingredient = resolution.ingredient
        if ingredient is None or not ingredient.is_active or not ingredient.default_unit:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
        try:
            unit = normalize_unit(ingredient.default_unit)
            override = overrides.get(index)
            if override is None:
                scaled = _scale(Decimal(str(line["amount"])), request.servings, recipe_servings)
                amount = convert_amount(scaled, line["unit"], unit)
            else:
                amount = convert_amount(override.amount, override.unit, unit)
        except (KeyError, UnitConversionError, InvalidOperation, ArithmeticError) as exc:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED") from exc
        if not amount.is_finite() or amount <= 0:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")

        included_indexes.add(index)
        try:
            safety_requirement = IngredientRequirementInput(
                ingredient_id=ingredient.id,
                amount=amount,
                unit=unit,
                required=required,
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED") from exc
        safety_requirements.append(safety_requirement)
        group = grouped.setdefault(
            ingredient.id,
            {
                "ingredient": ingredient,
                "amount": Decimal("0"),
                "indexes": [],
                "optional": True,
            },
        )
        group["amount"] += amount
        group["indexes"].append(index)
        group["optional"] = group["optional"] and not required

    if not included_indexes or set(overrides) - included_indexes:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    for group in grouped.values():
        try:
            IngredientRequirementInput(
                ingredient_id=group["ingredient"].id,
                amount=group["amount"],
                unit=group["ingredient"].default_unit,
                required=not group["optional"],
            )
        except ValidationError as exc:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED") from exc
    return list(grouped.values()), safety_requirements, included_indexes


def _factor_amount_in_unit(factor: ProductPackageFactor, ingredient_unit: str) -> Decimal:
    try:
        return convert_amount(
            Decimal(str(factor.ingredient_amount)), factor.ingredient_unit, ingredient_unit
        )
    except UnitConversionError as exc:
        raise UnitConversionError("Package factor unit is incompatible with the ingredient") from exc


def _stock_for_ingredient(
    db: Session,
    household_id: int,
    ingredient_id: int,
    ingredient_unit: str,
    batches: list[InventoryBatch],
    products: dict[int, Product],
    mappings: dict[int, ProductIngredientMapping],
    targets: dict[tuple[int, int], set[int]],
    factors: dict[tuple[int, int, int], ProductPackageFactor],
):
    result = []
    today = household_today()
    for batch in batches:
        if batch.expiration_date is not None and batch.expiration_date < today:
            continue
        product = products.get(batch.product_id)
        mapping = mappings.get(batch.product_id)
        if product is None or mapping is None:
            continue
        if (
            mapping.mode != "DIRECT"
            or mapping.verification_status != "VERIFIED"
            or mapping.verified_at is None
            or not mapping.method.strip()
            or mapping.unknown_composition
            or mapping.ingredient_id != ingredient_id
            or targets.get((mapping.product_id, mapping.version)) != {ingredient_id}
        ):
            continue
        native_unit = product.unit
        if not native_unit:
            continue
        factor = factors.get((mapping.product_id, mapping.version, ingredient_id))
        if factor is not None and (
            factor.verified_at is None or not factor.source_reference.strip()
        ):
            continue
        native_quantity = Decimal(str(batch.remaining_quantity))
        try:
            if factor is not None:
                if factor.inventory_unit.strip().casefold() != native_unit.strip().casefold():
                    continue
                per_native = _factor_amount_in_unit(factor, ingredient_unit)
                with localcontext() as context:
                    context.prec = 50
                    capacity = native_quantity * per_native
            else:
                capacity = convert_amount(native_quantity, native_unit, ingredient_unit)
        except (UnitConversionError, InvalidOperation, ArithmeticError):
            continue
        if capacity > 0:
            result.append((batch, product, mapping, factor, capacity))
    return result


def _native_for_take(
    amount: Decimal,
    ingredient_unit: str,
    product: Product,
    factor: ProductPackageFactor | None,
) -> Decimal:
    try:
        with localcontext() as context:
            context.prec = 50
            if factor is None:
                native = convert_amount(amount, ingredient_unit, product.unit)
            else:
                if factor.inventory_unit.strip().casefold() != product.unit.strip().casefold():
                    raise UnitConversionError("Package factor does not match the product unit")
                in_factor_unit = convert_amount(amount, ingredient_unit, factor.ingredient_unit)
                native = in_factor_unit / Decimal(str(factor.ingredient_amount))
    except (UnitConversionError, InvalidOperation, ArithmeticError) as exc:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED") from exc
    if not native.is_finite() or native <= 0:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    return native


def _allocate_stock(db: Session, household_id: int, grouped: list[dict]):
    batches = db.scalars(
        select(InventoryBatch)
        .where(InventoryBatch.household_id == household_id, InventoryBatch.remaining_quantity > 0)
        .order_by(
            InventoryBatch.expiration_date.asc().nulls_last(),
            InventoryBatch.purchased_at.asc(),
            InventoryBatch.id.asc(),
        )
        .execution_options(populate_existing=True)
    ).all()
    product_ids = {batch.product_id for batch in batches}
    products = {
        product.id: product
        for product in db.scalars(
            select(Product)
            .where(Product.household_id == household_id, Product.id.in_(product_ids))
            .execution_options(populate_existing=True)
        ).all()
    } if product_ids else {}
    current_mappings = db.scalars(
        select(ProductIngredientMapping)
        .where(
            ProductIngredientMapping.household_id == household_id,
            ProductIngredientMapping.product_id.in_(product_ids),
            ProductIngredientMapping.is_current.is_(True),
        )
        .execution_options(populate_existing=True)
    ).all() if product_ids else []
    mappings = {mapping.product_id: mapping for mapping in current_mappings}
    mapping_keys = {(mapping.product_id, mapping.version) for mapping in current_mappings}
    targets: dict[tuple[int, int], set[int]] = {}
    if mapping_keys:
        target_rows = db.scalars(
            select(ProductIngredientMappingTarget)
            .where(
                ProductIngredientMappingTarget.household_id == household_id,
                ProductIngredientMappingTarget.product_id.in_(product_ids),
            )
            .execution_options(populate_existing=True)
        ).all()
        for target in target_rows:
            key = (target.product_id, target.mapping_version)
            if key in mapping_keys:
                targets.setdefault(key, set()).add(target.ingredient_id)
    factors = {
        (factor.product_id, factor.mapping_version, factor.ingredient_id): factor
        for factor in db.scalars(
            select(ProductPackageFactor)
            .where(ProductPackageFactor.household_id == household_id)
            .execution_options(populate_existing=True)
        ).all()
    }
    location_ids = {batch.storage_location_id for batch in batches if batch.storage_location_id}
    locations = {
        location.id: location.name
        for location in db.scalars(
            select(StorageLocation)
            .where(
                StorageLocation.household_id == household_id,
                StorageLocation.id.in_(location_ids),
            )
            .execution_options(populate_existing=True)
        ).all()
    } if location_ids else {}

    results = []
    missing_expiry_ids: set[int] = set()
    for group in grouped:
        ingredient = group["ingredient"]
        remaining = group["amount"]
        allocations: list[CookingBatchAllocationRead] = []
        candidates = _stock_for_ingredient(
            db,
            household_id,
            ingredient.id,
            normalize_unit(ingredient.default_unit),
            batches,
            products,
            mappings,
            targets,
            factors,
        )
        for batch, product, mapping, factor, capacity in candidates:
            if remaining <= 0:
                break
            take = min(remaining, capacity)
            native_quantity = _native_for_take(
                take, normalize_unit(ingredient.default_unit), product, factor
            )
            allocations.append(
                CookingBatchAllocationRead(
                    batch_id=batch.id,
                    product_id=product.id,
                    product_name=product.name,
                    native_quantity=native_quantity,
                    native_unit=product.unit,
                    ingredient_quantity=take,
                    ingredient_unit=normalize_unit(ingredient.default_unit),
                    storage_location_id=batch.storage_location_id,
                    storage_location_name=locations.get(batch.storage_location_id),
                    expiration_date=batch.expiration_date,
                    expiration_unknown=batch.expiration_date is None,
                )
            )
            if batch.expiration_date is None:
                missing_expiry_ids.add(batch.id)
            remaining -= take
        if remaining > 0:
            raise HTTPException(
                status_code=422,
                detail={"code": "REVIEW_REQUIRED", "reason": "INSUFFICIENT_VERIFIED_DIRECT_STOCK", "ingredient_id": ingredient.id},
            )
        results.append(
            CookingRequirementRead(
                requirement_indexes=group["indexes"],
                ingredient_id=ingredient.id,
                canonical_name=ingredient.canonical_name,
                requested_quantity=group["amount"],
                unit=normalize_unit(ingredient.default_unit),
                optional=group["optional"],
                allocations=allocations,
            )
        )
    return results, sorted(missing_expiry_ids)


def _require_safety_coverage(safety, requirements: list[CookingRequirementRead]) -> None:
    """Only consume batches whose products participated in the safety evaluation."""
    coverage: dict[int, set[int]] = {}
    evaluated_amounts: dict[int, Decimal] = {}
    for line in safety.availability.requirements:
        if line.ingredient_id is None or line.required_amount is None or line.unit is None:
            continue
        ingredient_id = line.ingredient_id
        coverage.setdefault(ingredient_id, set()).update(line.covered_batch_ids)
        try:
            amount = Decimal(str(line.required_amount))
            evaluated_amounts[ingredient_id] = evaluated_amounts.get(
                ingredient_id, Decimal("0")
            ) + amount
        except (InvalidOperation, ArithmeticError):
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")

    for requirement in requirements:
        actual_amount = sum(
            (allocation.ingredient_quantity for allocation in requirement.allocations),
            Decimal("0"),
        )
        if evaluated_amounts.get(requirement.ingredient_id) != requirement.requested_quantity:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_REQUIRED",
                    "reason": "SAFETY_DEMAND_DIFFERS_FROM_COOKING_DEMAND",
                    "ingredient_id": requirement.ingredient_id,
                },
            )
        allocation_ids = {allocation.batch_id for allocation in requirement.allocations}
        if actual_amount != requirement.requested_quantity or not allocation_ids <= coverage.get(
            requirement.ingredient_id, set()
        ):
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_REQUIRED",
                    "reason": "COOKING_STOCK_NOT_FULLY_SAFETY_EVALUATED",
                    "ingredient_id": requirement.ingredient_id,
                },
            )


def _build_preview_context(
    db: Session,
    household_id: int,
    actor_id: int,
    request: CookingPreviewRequest,
):
    _require_active_member(db, household_id, actor_id)
    recipe, recipe_read = _recipe_snapshot(db, household_id, request)
    if recipe_read.get("content_permission") != "OWNED_OR_PERMISSION_GRANTED":
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    source_allowed, _reference = _source_allowed(
        db, household_id, recipe.id, request.expected_recipe_revision
    )
    if not source_allowed:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")

    grouped, safety_requirements, _included = _build_requirements(db, recipe_read, request)
    safety_request = FoodSafetyRequest(
        recipe_servings=request.servings,
        servings=request.servings,
        diner_user_ids=request.diner_user_ids,
        requirements=safety_requirements,
    )
    safety = evaluate_food_safety(db, household_id, safety_request)
    if safety.decision != "eligible":
        raise HTTPException(
            status_code=422,
            detail={"code": "REVIEW_REQUIRED", "decision": safety.decision, "reasons": safety.reasons},
        )

    requirements, missing_expiry_ids = _allocate_stock(db, household_id, grouped)
    _require_safety_coverage(safety, requirements)
    fingerprint = _context_fingerprint(
        db,
        household_id,
        actor_id,
        request,
        recipe.id,
        recipe.revision,
        safety,
        requirements,
    )
    return recipe, recipe_read, safety, requirements, missing_expiry_ids, fingerprint


def _encode_preview(
    household_id: int,
    actor_id: int,
    request: CookingPreviewRequest,
    inventory_revision: int,
    fingerprint: str,
    missing_expiry_ids: list[int],
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + _PREVIEW_TTL
    claims = {
        "purpose": _PREVIEW_PURPOSE,
        "household_id": household_id,
        "actor_user_id": actor_id,
        "input": request.model_dump(mode="json"),
        "inventory_revision": inventory_revision,
        "fingerprint": fingerprint,
        "missing_expiry_batch_ids": missing_expiry_ids,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), expires_at


def _decode_preview(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "jti", "purpose"]},
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
    if claims.get("purpose") != _PREVIEW_PURPOSE:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    return claims


def preview_cooking(
    db: Session,
    household_id: int,
    actor_id: int,
    request: CookingPreviewRequest,
) -> CookingPreviewRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        household = snapshot.scalar(
            select(Household).where(Household.id == household_id).execution_options(populate_existing=True)
        )
        if household is None:
            raise HTTPException(status_code=404, detail="Household not found")
        recipe, recipe_read, safety, requirements, missing_expiry_ids, fingerprint = _build_preview_context(
            snapshot, household_id, actor_id, request
        )
        token, expires_at = _encode_preview(
            household_id,
            actor_id,
            request,
            household.inventory_revision,
            fingerprint,
            missing_expiry_ids,
        )
        return CookingPreviewRead(
            preview_id=token,
            expires_at=expires_at,
            recipe_id=recipe.id,
            recipe_revision=recipe.revision,
            recipe_title=recipe_read["title"],
            servings=request.servings,
            inventory_revision=household.inventory_revision,
            safety=safety,
            requirements=requirements,
            missing_expiry_batch_ids=missing_expiry_ids,
        )


def _request_hash(actor_id: int, household_id: int, request: CookingConfirmRequest) -> str:
    body = request.model_dump(mode="json", exclude={"idempotency_key"})
    for index, leftover in enumerate(request.leftovers):
        if "prepared_at" not in leftover.model_fields_set:
            body["leftovers"][index].pop("prepared_at", None)
    payload = {
        "actor_user_id": actor_id,
        "household_id": household_id,
        "body": body,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _lock_curated_tables(db: Session) -> None:
    db.execute(text(f"LOCK TABLE {', '.join(_GLOBAL_TABLES)} IN SHARE MODE"))


def _same_fingerprint(expected: str, actual: str) -> bool:
    return hmac.compare_digest(str(expected), str(actual))


def _native_is_hundredths(value: Decimal) -> bool:
    try:
        return value == value.quantize(Decimal("0.01"))
    except (InvalidOperation, DecimalException):
        return False


def _lock_allocated_batches(db: Session, household_id: int, requirements: list[CookingRequirementRead]):
    ids = sorted(
        {
            allocation.batch_id
            for requirement in requirements
            for allocation in requirement.allocations
        }
    )
    if not ids:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    batches = db.scalars(
        select(InventoryBatch)
        .where(InventoryBatch.household_id == household_id, InventoryBatch.id.in_(ids))
        .order_by(InventoryBatch.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    by_id = {batch.id: batch for batch in batches}
    if set(by_id) != set(ids):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    return by_id


def _read_cooking_session(db: Session, session: CookingSession) -> CookingSessionRead:
    current = db.scalar(
        select(CookingSession)
        .where(
            CookingSession.household_id == session.household_id,
            CookingSession.id == session.id,
        )
        .execution_options(populate_existing=True)
    )
    if current is None:
        raise HTTPException(status_code=404, detail="Cooking session not found")
    session = current
    consumptions = db.scalars(
        select(CookingConsumption)
        .where(
            CookingConsumption.household_id == session.household_id,
            CookingConsumption.cooking_session_id == session.id,
        )
        .order_by(CookingConsumption.id)
        .execution_options(populate_existing=True)
    ).all()
    leftovers = db.scalars(
        select(Leftover)
        .where(
            Leftover.household_id == session.household_id,
            Leftover.cooking_session_id == session.id,
        )
        .order_by(Leftover.id)
        .execution_options(populate_existing=True)
    ).all()
    return CookingSessionRead(
        id=session.id,
        recipe_id=session.recipe_id,
        recipe_revision=session.recipe_revision,
        servings=session.servings,
        recorded_at=session.recorded_at,
        inventory_revision=session.inventory_revision,
        consumptions=[
            CookingConsumptionRead(
                batch_id=item.batch_id,
                inventory_event_id=item.inventory_event_id,
                ingredient_id=item.ingredient_id,
                ingredient_quantity=item.ingredient_quantity,
                ingredient_unit=item.ingredient_unit,
            )
            for item in consumptions
        ],
        leftovers=[read_leftover(db, item) for item in leftovers],
    )


def read_cooking_session(db: Session, session: CookingSession) -> CookingSessionRead:
    """Hydrate one household session model for API and account-export callers."""
    with _readonly_snapshot(db.get_bind()) as snapshot:
        current = snapshot.scalar(
            select(CookingSession)
            .where(
                CookingSession.household_id == session.household_id,
                CookingSession.id == session.id,
            )
            .execution_options(populate_existing=True)
        )
        if current is None:
            raise HTTPException(status_code=404, detail="Cooking session not found")
        return _read_cooking_session(snapshot, current)


def get_cooking_session_read(
    db: Session, household_id: int, cooking_session_id: int
) -> CookingSessionRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        session = snapshot.scalar(
            select(CookingSession)
            .where(
                CookingSession.household_id == household_id,
                CookingSession.id == cooking_session_id,
            )
            .execution_options(populate_existing=True)
        )
        if session is None:
            raise HTTPException(status_code=404, detail="Cooking session not found")
        return _read_cooking_session(snapshot, session)


def list_cooking_sessions(db: Session, household_id: int) -> list[CookingSessionRead]:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        sessions = snapshot.scalars(
            select(CookingSession)
            .where(CookingSession.household_id == household_id)
            .order_by(CookingSession.recorded_at.desc(), CookingSession.id.desc())
            .execution_options(populate_existing=True)
        ).all()
        return [_read_cooking_session(snapshot, session) for session in sessions]


def confirm_cooking(
    db: Session,
    household_id: int,
    actor_id: int,
    request: CookingConfirmRequest,
) -> CookingConfirmRead:
    request_hash = _request_hash(actor_id, household_id, request)
    try:
        household = lock_household_write(db, household_id, actor_id=actor_id)
        existing = db.scalar(
            select(CookingIdempotency)
            .where(
                CookingIdempotency.household_id == household_id,
                CookingIdempotency.idempotency_key == request.idempotency_key,
            )
            .execution_options(populate_existing=True)
        )
        if existing is not None:
            if existing.actor_user_id != actor_id or not hmac.compare_digest(
                existing.request_hash, request_hash
            ):
                raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
            return CookingConfirmRead.model_validate(existing.response_snapshot)

        claims = _decode_preview(request.preview_id)
        if (
            claims.get("household_id") != household_id
            or claims.get("actor_user_id") != actor_id
            or claims.get("inventory_revision") != household.inventory_revision
        ):
            raise HTTPException(status_code=409, detail="STALE_PREVIEW")
        try:
            preview_request = CookingPreviewRequest.model_validate(claims["input"])
            claimed_missing_expiry = sorted(set(claims["missing_expiry_batch_ids"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
        if sorted(request.acknowledged_missing_expiry_batch_ids) != claimed_missing_expiry:
            raise HTTPException(status_code=422, detail="MISSING_EXPIRY_ACKNOWLEDGEMENT_REQUIRED")

        _lock_curated_tables(db)
        try:
            recipe, recipe_read, safety, requirements, missing_expiry_ids, fingerprint = (
                _build_preview_context(db, household_id, actor_id, preview_request)
            )
        except HTTPException as exc:
            if exc.status_code in {403, 404, 409, 422}:
                raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
            raise
        if (
            recipe.id != claims["input"]["recipe_id"]
            or recipe.revision != claims["input"]["expected_recipe_revision"]
            or missing_expiry_ids != claimed_missing_expiry
            or not _same_fingerprint(claims.get("fingerprint", ""), fingerprint)
        ):
            raise HTTPException(status_code=409, detail="STALE_PREVIEW")

        batch_by_id = _lock_allocated_batches(db, household_id, requirements)
        # Recompute after row locks as a guard against writers that bypassed the
        # household lock and changed a cached batch between preview and locking.
        recipe, recipe_read, safety, requirements, missing_expiry_ids, fingerprint = (
            _build_preview_context(db, household_id, actor_id, preview_request)
        )
        if (
            missing_expiry_ids != claimed_missing_expiry
            or not _same_fingerprint(claims.get("fingerprint", ""), fingerprint)
        ):
            raise HTTPException(status_code=409, detail="STALE_PREVIEW")
        if any(
            allocation.batch_id not in batch_by_id
            or not _native_is_hundredths(allocation.native_quantity)
            for requirement_line in requirements
            for allocation in requirement_line.allocations
        ):
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")

        session = CookingSession(
            household_id=household_id,
            recipe_id=recipe.id,
            recipe_revision=recipe.revision,
            actor_user_id=actor_id,
            servings=preview_request.servings,
            inventory_revision=household.inventory_revision,
            source_reference_id=None,
            source_reference_revision=None,
            source_id=None,
            source_revision=None,
        )
        source_ref = db.scalar(
            select(RecipeSourceReference)
            .where(
                RecipeSourceReference.household_id == household_id,
                RecipeSourceReference.recipe_id == recipe.id,
            )
            .execution_options(populate_existing=True)
        )
        if source_ref is not None and source_ref.is_active:
            session.source_reference_id = source_ref.id
            session.source_reference_revision = source_ref.revision
            session.source_id = source_ref.source_id
            source = db.scalar(
                select(RecipeSource)
                .where(RecipeSource.id == source_ref.source_id)
                .execution_options(populate_existing=True)
            ) if source_ref.source_id else None
            session.source_revision = source.revision if source else None
        db.add(session)
        db.flush()

        for requirement_line in requirements:
            for allocation in requirement_line.allocations:
                batch = batch_by_id[allocation.batch_id]
                if allocation.native_quantity > Decimal(str(batch.remaining_quantity)):
                    raise HTTPException(status_code=409, detail="STALE_PREVIEW")
                try:
                    event: InventoryEvent = consume_batch_no_commit(
                        db,
                        batch,
                        allocation.native_quantity,
                        reason="Recorded cooking",
                        require_hundredths=True,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail="REVIEW_REQUIRED") from exc
                db.add(
                    CookingConsumption(
                        household_id=household_id,
                        cooking_session_id=session.id,
                        batch_id=batch.id,
                        inventory_event_id=event.id,
                        ingredient_id=requirement_line.ingredient_id,
                        ingredient_quantity=allocation.ingredient_quantity,
                        ingredient_unit=requirement_line.unit,
                    )
                )

        for leftover_request in request.leftovers:
            create_leftover_no_commit(
                db,
                household_id,
                actor_id,
                leftover_request,
                cooking_session=session,
            )

        session.inventory_revision = bump_inventory_revision(db, household_id)
        db.flush()
        response = CookingConfirmRead(session=_read_cooking_session(db, session))
        db.add(
            CookingIdempotency(
                household_id=household_id,
                cooking_session_id=session.id,
                actor_user_id=actor_id,
                idempotency_key=request.idempotency_key,
                request_hash=request_hash,
                response_snapshot=response.model_dump(mode="json"),
            )
        )
        db.commit()
        return response
    except Exception:
        db.rollback()
        raise
