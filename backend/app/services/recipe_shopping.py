"""Read-only recipe shopping previews and atomic household-scoped confirmation."""

from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import hmac
import json
import uuid

import jwt
from fastapi import HTTPException
from sqlalchemy import or_, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.time import household_today
from app.models.allergens import IngredientAllergen, IngredientDerivative
from app.models.batch import InventoryBatch
from app.models.household import Household, HouseholdMembership
from app.models.ingredient import (
    Ingredient,
    IngredientAlias,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
    ProductPackageFactor,
)
from app.models.preferences import FoodAllergy, FoodPreference
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.models.recipe import Recipe, RecipeIngredient, RecipeRevision
from app.models.recipe_shopping import RecipeShoppingIdempotency
from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.schemas.recipe import RecipeEvaluationInput
from app.schemas.recipe_shopping import (
    ConsolidatedShoppingItems,
    RecipeShoppingAcceptedLine,
    RecipeShoppingConfirmRead,
    RecipeShoppingConfirmRequest,
    RecipeShoppingLine,
    RecipeShoppingPreviewRead,
    RecipeShoppingPreviewRequest,
    ShoppingItemDeletionSnapshot,
    UnlinkedShoppingItemReview,
)
from app.schemas.shopping import ShoppingListItemRead
from app.services.household_writes import bump_shopping_revision, lock_household_write
from app.services.ingredient_matching import (
    normalize_ingredient_name,
    resolve_ingredient,
)
from app.services.recipes import evaluate_recipe, get_recipe, read_recipe
from app.services.units import UnitConversionError, convert_amount


_PREVIEW_PURPOSE = "recipe-shopping-preview"
_PREVIEW_TTL = timedelta(minutes=10)
_QUANTITY_STEP = Decimal("0.000001")
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
        raise RuntimeError("Recipe shopping previews require a PostgreSQL engine")
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
    if isinstance(value, set):
        return [_json_value(item) for item in sorted(value, key=str)]
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


def _possible_recipe_ingredient_matches(
    db: Session, display_name: str, ingredient_ids: set[int]
) -> set[int]:
    """Find all plausible matches, limited to the active recipe's ingredient set."""
    if not ingredient_ids:
        return set()

    tokens = {
        token
        for token in normalize_ingredient_name(display_name).split()
        if len(token) >= 3
    }
    if not tokens:
        return set()
    patterns = []
    for token in sorted(tokens):
        escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        patterns.append(f"%{escaped}%")
    canonical_match = or_(
        *(Ingredient.normalized_name.ilike(pattern, escape="\\") for pattern in patterns)
    )
    alias_match = select(IngredientAlias.ingredient_id).where(
        IngredientAlias.ingredient_id.in_(ingredient_ids),
        or_(
            *(IngredientAlias.normalized_alias.ilike(pattern, escape="\\") for pattern in patterns)
        ),
    )
    return set(
        db.scalars(
            select(Ingredient.id).where(
                Ingredient.id.in_(ingredient_ids),
                Ingredient.is_active.is_(True),
                or_(canonical_match, Ingredient.id.in_(alias_match)),
            )
        ).all()
    )


def _context_fingerprint(
    db: Session,
    household_id: int,
    recipe_id: int,
    request: RecipeShoppingPreviewRequest,
    safety,
    lines: list[RecipeShoppingLine],
    unlinked: list[UnlinkedShoppingItemReview],
) -> str:
    profile_ids = select(FoodPreference.id).where(FoodPreference.household_id == household_id)
    member_rows = db.execute(
        select(HouseholdMembership, User)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(HouseholdMembership.household_id == household_id)
        .order_by(HouseholdMembership.user_id)
        .execution_options(populate_existing=True)
    ).all()
    household = db.get(Household, household_id)
    reference = db.scalar(
        select(RecipeSourceReference).where(
            RecipeSourceReference.household_id == household_id,
            RecipeSourceReference.recipe_id == recipe_id,
        ).execution_options(populate_existing=True)
    )
    context = {
        "manila_date": household_today().isoformat(),
        "input": request.model_dump(mode="json"),
        "household": _model_row(household) if household else None,
        "members": [
            {
                "membership": _model_row(membership),
                "user": {"id": user.id, "is_active": user.is_active},
            }
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
        "recipe_revisions": _rows(
            db,
            RecipeRevision,
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == recipe_id,
        ),
        "source_reference": _model_row(reference) if reference else None,
        "sources": _rows(db, RecipeSource),
        "source_reviews": _rows(db, RecipeSourceReview),
        "products": _rows(db, Product, Product.household_id == household_id),
        "mappings": _rows(
            db, ProductIngredientMapping, ProductIngredientMapping.household_id == household_id
        ),
        "mapping_targets": _rows(
            db,
            ProductIngredientMappingTarget,
            ProductIngredientMappingTarget.household_id == household_id,
        ),
        "package_factors": _rows(
            db, ProductPackageFactor, ProductPackageFactor.household_id == household_id
        ),
        "product_labels": _rows(
            db, ProductAllergenLabel, ProductAllergenLabel.household_id == household_id
        ),
        "batches": _rows(db, InventoryBatch, InventoryBatch.household_id == household_id),
        "shopping_items": _rows(
            db, ShoppingListItem, ShoppingListItem.household_id == household_id
        ),
        "ingredients": _rows(db, Ingredient),
        "ingredient_aliases": _rows(db, IngredientAlias),
        "ingredient_allergens": _rows(db, IngredientAllergen),
        "ingredient_derivatives": _rows(db, IngredientDerivative),
        "safety": safety.model_dump(mode="json"),
        "lines": [line.model_dump(mode="json") for line in lines],
        "unlinked_manual_items": [item.model_dump(mode="json") for item in unlinked],
    }
    encoded = json.dumps(context, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _unit_key(value: str | None) -> str | None:
    return " ".join(value.casefold().split()) if value else None


def _is_quantity_representable(value: Decimal | None) -> bool:
    if value is None or not value.is_finite() or value < 0:
        return False
    if value > Decimal("99999999.999999"):
        return False
    try:
        with localcontext() as context:
            context.prec = 50
            return value == value.quantize(_QUANTITY_STEP)
    except InvalidOperation:
        return False


def _direct_mapping_is_verified(mapping, target_ids: list[int], ingredient_id: int) -> bool:
    return bool(
        mapping
        and mapping.mode == "DIRECT"
        and mapping.ingredient_id == ingredient_id
        and target_ids == [ingredient_id]
        and mapping.verification_status == "VERIFIED"
        and mapping.verified_at is not None
        and not mapping.unknown_composition
    )


def _convert_shopping_quantity(item, ingredient, product, mapping, target_ids, factor) -> Decimal:
    amount = Decimal(str(item.quantity))
    unit = item.unit or (product.unit if product else None)
    target_unit = ingredient.default_unit
    if not unit or not target_unit:
        raise UnitConversionError("Shopping quantity unit is missing")

    if factor is not None and _direct_mapping_is_verified(mapping, target_ids, ingredient.id):
        if (
            _unit_key(unit) == _unit_key(factor.inventory_unit)
            and product is not None
            and _unit_key(product.unit) == _unit_key(factor.inventory_unit)
        ):
            expanded = amount * Decimal(str(factor.ingredient_amount))
            return convert_amount(expanded, factor.ingredient_unit, target_unit)

    return convert_amount(amount, unit, target_unit)


def _pending_context(db: Session, household_id: int, ingredient_ids: set[int]):
    items = db.scalars(
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.is_bought.is_(False),
        )
        .order_by(ShoppingListItem.id)
        .execution_options(populate_existing=True)
    ).all()
    product_ids = {item.product_id for item in items if item.product_id is not None}
    mappings = db.scalars(
        select(ProductIngredientMapping).where(
            ProductIngredientMapping.household_id == household_id,
            ProductIngredientMapping.product_id.in_(product_ids) if product_ids else text("false"),
            ProductIngredientMapping.is_current.is_(True),
        ).execution_options(populate_existing=True)
    ).all()
    mapping_by_product = {mapping.product_id: mapping for mapping in mappings}
    target_rows = db.scalars(
        select(ProductIngredientMappingTarget).where(
            ProductIngredientMappingTarget.household_id == household_id,
            ProductIngredientMappingTarget.product_id.in_(product_ids) if product_ids else text("false"),
        ).execution_options(populate_existing=True)
    ).all()
    targets_by_mapping: dict[tuple[int, int], list[int]] = {}
    for target in target_rows:
        targets_by_mapping.setdefault((target.product_id, target.mapping_version), []).append(
            target.ingredient_id
        )
    factor_rows = db.scalars(
        select(ProductPackageFactor).where(
            ProductPackageFactor.household_id == household_id,
            ProductPackageFactor.product_id.in_(product_ids) if product_ids else text("false"),
        ).execution_options(populate_existing=True)
    ).all()
    factors = {
        (factor.product_id, factor.mapping_version, factor.ingredient_id): factor
        for factor in factor_rows
    }
    ingredients = {
        ingredient.id: ingredient
        for ingredient in db.scalars(
            select(Ingredient)
            .where(Ingredient.id.in_(ingredient_ids))
            .execution_options(populate_existing=True)
        ).all()
    }

    amounts: dict[int, Decimal] = {ingredient_id: Decimal("0") for ingredient_id in ingredient_ids}
    item_ids: dict[int, list[int]] = {ingredient_id: [] for ingredient_id in ingredient_ids}
    reasons: dict[int, set[str]] = {ingredient_id: set() for ingredient_id in ingredient_ids}
    unlinked_reviews: list[UnlinkedShoppingItemReview] = []

    for item in items:
        candidate_ids: set[int] = set()
        identity_conflict = False
        mapping = mapping_by_product.get(item.product_id) if item.product_id is not None else None
        target_ids = sorted(
            set(targets_by_mapping.get((mapping.product_id, mapping.version), []))
        ) if mapping else []

        if item.ingredient_id is not None:
            if item.ingredient_id in ingredient_ids:
                candidate_ids.add(item.ingredient_id)
                if mapping is not None and (
                    mapping.mode != "DIRECT"
                    or mapping.ingredient_id != item.ingredient_id
                    or target_ids != [item.ingredient_id]
                ):
                    identity_conflict = True
                    item_ids[item.ingredient_id].append(item.id)
                    reasons[item.ingredient_id].add(
                        "product_identity_conflicts_with_explicit_ingredient"
                    )
        elif mapping and mapping.mode == "DIRECT" and mapping.ingredient_id in ingredient_ids:
            candidate_ids.add(mapping.ingredient_id)
        elif mapping and mapping.mode == "COMPOSITE":
            related = set(target_ids) & ingredient_ids
            for ingredient_id in related:
                item_ids[ingredient_id].append(item.id)
                reasons[ingredient_id].add("composite_shopping_product_requires_review")
        elif item.product_id is None:
            resolution = resolve_ingredient(db, display_name=item.name)
            possible_ids = set(resolution.candidate_ids)
            if not possible_ids:
                possible_ids = _possible_recipe_ingredient_matches(
                    db, item.name, ingredient_ids
                )
            related = possible_ids & ingredient_ids
            if related:
                for ingredient_id in related:
                    item_ids[ingredient_id].append(item.id)
                    reasons[ingredient_id].add("unlinked_alias_match_requires_review")
                unlinked_reviews.append(
                    UnlinkedShoppingItemReview(
                        item_id=item.id,
                        name=item.name,
                        quantity=float(item.quantity),
                        unit=item.unit,
                        candidate_ingredient_ids=sorted(related),
                        reason=(
                            "ambiguous_curated_alias"
                            if resolution.ambiguous
                            else "exact_curated_alias_requires_explicit_link"
                            if resolution.ingredient is not None
                            else "possible_alias_match_requires_review"
                        ),
                    )
                )

        for ingredient_id in candidate_ids:
            if item.id not in item_ids[ingredient_id]:
                item_ids[ingredient_id].append(item.id)
            if identity_conflict:
                continue
            if item.ingredient_id is None and not _direct_mapping_is_verified(
                mapping, target_ids, ingredient_id
            ):
                reasons[ingredient_id].add("product_mapping_not_verified_direct")
                continue
            factor = factors.get(
                (mapping.product_id, mapping.version, ingredient_id)
            ) if mapping else None
            native_unit = item.unit or (item.product.unit if item.product else None)
            package_factor_matches = bool(
                factor
                and _direct_mapping_is_verified(mapping, target_ids, ingredient_id)
                and item.product is not None
                and _unit_key(native_unit) == _unit_key(factor.inventory_unit)
                and _unit_key(item.product.unit) == _unit_key(factor.inventory_unit)
            )
            if (
                item.unit
                and item.product is not None
                and item.product.unit
                and _unit_key(item.unit) != _unit_key(item.product.unit)
            ):
                try:
                    convert_amount(Decimal("1"), item.product.unit, item.unit)
                except UnitConversionError:
                    if not package_factor_matches:
                        reasons[ingredient_id].add(
                            "shopping_product_unit_conflict_requires_review"
                        )
                        continue
            try:
                amount = _convert_shopping_quantity(
                    item,
                    ingredients[ingredient_id],
                    item.product,
                    mapping,
                    target_ids,
                    factor,
                )
                if not amount.is_finite() or amount < 0:
                    raise UnitConversionError("Shopping quantity must be finite and nonnegative")
                amounts[ingredient_id] += amount
            except (UnitConversionError, InvalidOperation, KeyError):
                reasons[ingredient_id].add("pending_shopping_unit_requires_review")

    return amounts, item_ids, reasons, unlinked_reviews


def _build_lines(db: Session, household_id: int, availability):
    ingredient_ids = {
        line.ingredient_id
        for line in availability.requirements
        if line.ingredient_id is not None
    }
    pending, pending_ids, pending_reasons, unlinked = _pending_context(
        db, household_id, ingredient_ids
    )
    grouped: dict[int, dict] = {}
    unresolved: list[RecipeShoppingLine] = []

    for requirement in availability.requirements:
        if requirement.ingredient_id is None:
            unresolved.append(
                RecipeShoppingLine(
                    ingredient_id=None,
                    canonical_name=None,
                    display_name=" / ".join(requirement.display_names) or "Unresolved ingredient",
                    unit=requirement.unit,
                    required_quantity=requirement.required_amount,
                    pantry_quantity=requirement.available_amount,
                    shortage=requirement.shortfall,
                    pending_quantity=None,
                    target_quantity=None,
                    additional_quantity=None,
                    covered_batch_ids=requirement.covered_batch_ids,
                    status="review_required",
                    review_reasons=requirement.unknown_reasons or ["ingredient_identity_requires_review"],
                )
            )
            continue

        group = grouped.setdefault(
            requirement.ingredient_id,
            {
                "canonical_name": requirement.canonical_name or "",
                "display_names": [],
                "unit": requirement.unit,
                "required": Decimal("0"),
                "shortage": Decimal("0"),
                "pantry": None,
                "covered": set(),
                "reasons": set(),
            },
        )
        group["display_names"].extend(
            name for name in requirement.display_names if name not in group["display_names"]
        )
        group["covered"].update(requirement.covered_batch_ids)
        group["reasons"].update(requirement.unknown_reasons)
        if requirement.unit != group["unit"]:
            group["reasons"].add("incompatible_requirement_units")
        if requirement.required_amount is None or requirement.shortfall is None:
            group["reasons"].add("required_quantity_requires_review")
            if requirement.shortfall is None:
                group["shortage"] = None
            if requirement.required_amount is None:
                group["required"] = None
        else:
            if group["required"] is not None:
                group["required"] += requirement.required_amount
            if group["shortage"] is not None:
                group["shortage"] += requirement.shortfall
        if requirement.required or group["pantry"] is None:
            group["pantry"] = requirement.available_amount

    lines: list[RecipeShoppingLine] = []
    for ingredient_id, group in sorted(
        grouped.items(), key=lambda entry: (entry[1]["canonical_name"].casefold(), entry[0])
    ):
        reasons = set(group["reasons"]) | pending_reasons[ingredient_id]
        pending_quantity = pending[ingredient_id] if not pending_reasons[ingredient_id] else None
        required_quantity = group["required"]
        shortage = group["shortage"]
        if group["unit"] is None or group["pantry"] is None:
            reasons.add("availability_quantity_requires_review")
        if pending_quantity is not None and shortage is not None:
            target = max(pending_quantity, shortage)
            additional = max(target - pending_quantity, Decimal("0"))
        else:
            target = additional = None
        for value in (required_quantity, group["pantry"], shortage, pending_quantity, target, additional):
            if value is not None and not _is_quantity_representable(value):
                reasons.add("quantity_precision_requires_review")

        lines.append(
            RecipeShoppingLine(
                ingredient_id=ingredient_id,
                canonical_name=group["canonical_name"],
                display_name=" / ".join(group["display_names"]) or group["canonical_name"],
                unit=group["unit"],
                required_quantity=required_quantity,
                pantry_quantity=group["pantry"],
                shortage=shortage,
                pending_quantity=pending_quantity,
                target_quantity=target,
                additional_quantity=additional,
                pending_item_ids=sorted(set(pending_ids[ingredient_id])),
                covered_batch_ids=sorted(group["covered"]),
                status="review_required" if reasons else "ready",
                review_reasons=sorted(reasons),
            )
        )

    lines.extend(unresolved)
    return lines, unlinked


def _preview_context(
    db: Session,
    household_id: int,
    actor_id: int,
    request: RecipeShoppingPreviewRequest,
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

    recipe = get_recipe(db, household_id, request.recipe_id)
    if recipe.revision != request.expected_recipe_revision or not recipe.is_active:
        raise HTTPException(status_code=409, detail="RECIPE_REVISION_CONFLICT")
    record = read_recipe(db, recipe)
    evaluation = evaluate_recipe(
        db,
        household_id,
        recipe.id,
        RecipeEvaluationInput(
            expected_recipe_revision=request.expected_recipe_revision,
            servings=request.servings,
            diner_user_ids=request.diner_user_ids,
            include_optional=request.include_optional,
        ),
    )
    household = db.get(Household, household_id)
    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")
    lines, unlinked = _build_lines(db, household_id, evaluation.result.availability)
    fingerprint = _context_fingerprint(
        db, household_id, recipe.id, request, evaluation.result, lines, unlinked
    )
    return recipe, record, evaluation, household, lines, unlinked, fingerprint


def _encode_preview(
    household_id: int,
    actor_id: int,
    request: RecipeShoppingPreviewRequest,
    shopping_revision: int,
    inventory_revision: int,
    fingerprint: str,
) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(int(now.timestamp()) + int(_PREVIEW_TTL.total_seconds()), timezone.utc)
    claims = {
        "purpose": _PREVIEW_PURPOSE,
        "jti": uuid.uuid4().hex,
        "household_id": household_id,
        "actor_user_id": actor_id,
        "input": request.model_dump(mode="json"),
        "shopping_revision": shopping_revision,
        "inventory_revision": inventory_revision,
        "fingerprint": fingerprint,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    return jwt.encode(claims, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM), expires_at


def preview_recipe_shopping(
    db: Session,
    household_id: int,
    actor_id: int,
    request: RecipeShoppingPreviewRequest,
) -> RecipeShoppingPreviewRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        recipe, _record, evaluation, household, lines, unlinked, fingerprint = _preview_context(
            snapshot, household_id, actor_id, request
        )
        if evaluation.result.decision != "eligible":
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "REVIEW_REQUIRED",
                    "decision": evaluation.result.decision,
                    "reasons": evaluation.result.reasons,
                },
            )
        token, expires_at = _encode_preview(
            household_id,
            actor_id,
            request,
            household.shopping_revision,
            household.inventory_revision,
            fingerprint,
        )
        return RecipeShoppingPreviewRead(
            preview_id=token,
            expires_at=expires_at,
            recipe_id=recipe.id,
            recipe_revision=recipe.revision,
            servings=request.servings,
            include_optional=request.include_optional,
            shopping_revision=household.shopping_revision,
            inventory_revision=household.inventory_revision,
            included_requirement_indexes=evaluation.included_requirement_indexes,
            safety=evaluation.result,
            lines=lines,
            unlinked_manual_items=unlinked,
        )


def _request_hash(actor_id: int, household_id: int, request: RecipeShoppingConfirmRequest) -> str:
    payload = {
        "actor_user_id": actor_id,
        "household_id": household_id,
        "body": request.model_dump(mode="json", exclude={"idempotency_key"}),
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _decode_preview(token: str) -> dict:
    try:
        claims = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "iat", "jti", "purpose"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
    if claims.get("purpose") != _PREVIEW_PURPOSE:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    return claims


def _lock_curated_tables(db: Session) -> None:
    table_names = ", ".join(_GLOBAL_TABLES)
    db.execute(text(f"LOCK TABLE {table_names} IN SHARE MODE"))


def _snapshot_deleted_item(item: ShoppingListItem) -> ShoppingItemDeletionSnapshot:
    return ShoppingItemDeletionSnapshot(
        id=item.id,
        name=item.name,
        quantity=float(item.quantity),
        unit=item.unit,
        product_id=item.product_id,
        ingredient_id=item.ingredient_id,
        is_bought=item.is_bought,
        notes=item.notes,
        origin_recipe_id=item.origin_recipe_id,
        origin_recipe_revision=item.origin_recipe_revision,
    )


def _read_item(db: Session, household_id: int, item_id: int) -> ShoppingListItemRead:
    item = db.scalar(
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.id == item_id,
        ).execution_options(populate_existing=True)
    )
    if item is None:
        raise RuntimeError("Shopping item disappeared during the household write")
    return ShoppingListItemRead.model_validate(item)


def _create_recipe_item(db: Session, household_id: int, recipe, line, quantity: Decimal):
    item = ShoppingListItem(
        household_id=household_id,
        ingredient_id=line.ingredient_id,
        origin_recipe_id=recipe.id,
        origin_recipe_revision=recipe.revision,
        name=line.canonical_name,
        quantity=quantity,
        unit=line.unit,
        is_bought=False,
        notes=None,
    )
    db.add(item)
    db.flush()
    return item


def _native_quantity_for_item(
    db: Session,
    household_id: int,
    item: ShoppingListItem,
    ingredient_id: int,
    ingredient_quantity: Decimal,
) -> Decimal:
    ingredient = db.scalar(
        select(Ingredient).where(
            Ingredient.id == ingredient_id,
            Ingredient.is_active.is_(True),
        ).execution_options(populate_existing=True)
    )
    if ingredient is None or not ingredient.default_unit:
        raise UnitConversionError("Canonical ingredient unit is unavailable")

    native_unit = item.unit or (item.product.unit if item.product else None)
    if not native_unit:
        raise UnitConversionError("Pending shopping unit is missing")

    mapping = None
    targets: list[int] = []
    factor = None
    if item.product_id is not None:
        mapping = db.scalar(
            select(ProductIngredientMapping).where(
                ProductIngredientMapping.household_id == household_id,
                ProductIngredientMapping.product_id == item.product_id,
                ProductIngredientMapping.is_current.is_(True),
            ).execution_options(populate_existing=True)
        )
        if mapping is not None:
            targets = sorted(
                set(
                    db.scalars(
                        select(ProductIngredientMappingTarget.ingredient_id).where(
                            ProductIngredientMappingTarget.household_id == household_id,
                            ProductIngredientMappingTarget.product_id == item.product_id,
                            ProductIngredientMappingTarget.mapping_version == mapping.version,
                        ).execution_options(populate_existing=True)
                    ).all()
                )
            )
            factor = db.scalar(
                select(ProductPackageFactor).where(
                    ProductPackageFactor.household_id == household_id,
                    ProductPackageFactor.product_id == item.product_id,
                    ProductPackageFactor.mapping_version == mapping.version,
                    ProductPackageFactor.ingredient_id == ingredient_id,
                ).execution_options(populate_existing=True)
            )

    if factor is not None and _direct_mapping_is_verified(mapping, targets, ingredient_id):
        if (
            item.product is None
            or _unit_key(native_unit) != _unit_key(factor.inventory_unit)
            or _unit_key(item.product.unit) != _unit_key(factor.inventory_unit)
        ):
            raise UnitConversionError("Verified package factor does not match the pending row unit")
        in_factor_unit = convert_amount(
            ingredient_quantity,
            ingredient.default_unit,
            factor.ingredient_unit,
        )
        native_quantity = in_factor_unit / Decimal(str(factor.ingredient_amount))
    else:
        native_quantity = convert_amount(
            ingredient_quantity,
            ingredient.default_unit,
            native_unit,
        )

    if not _is_quantity_representable(native_quantity):
        raise UnitConversionError("Target cannot be represented exactly in the pending row unit")
    return native_quantity


def _apply_accepted_line(
    db: Session,
    household_id: int,
    recipe,
    line: RecipeShoppingLine,
    accepted: RecipeShoppingAcceptedLine,
    response: RecipeShoppingConfirmRead,
) -> bool:
    if line.status != "ready" or line.target_quantity is None or line.pending_quantity is None:
        raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
    minimum = max(line.shortage or Decimal("0"), line.pending_quantity)
    if accepted.target_quantity < minimum:
        raise HTTPException(status_code=422, detail="TARGET_BELOW_REQUIRED_OR_PENDING_QUANTITY")
    if not _is_quantity_representable(accepted.target_quantity):
        raise HTTPException(status_code=422, detail="QUANTITY_PRECISION_REQUIRES_REVIEW")

    pending_items = db.scalars(
        select(ShoppingListItem)
        .where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.id.in_(line.pending_item_ids),
            ShoppingListItem.is_bought.is_(False),
        )
        .order_by(ShoppingListItem.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all() if line.pending_item_ids else []
    current_ids = {item.id for item in pending_items}
    if current_ids != set(line.pending_item_ids):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    if accepted.consolidate_existing and pending_items:
        primary = pending_items[0]
        removed = pending_items[1:]
        if any(duplicate.is_bought for duplicate in removed):
            raise HTTPException(status_code=409, detail="STALE_PREVIEW")
        try:
            native_quantity = _native_quantity_for_item(
                db, household_id, primary, line.ingredient_id, accepted.target_quantity
            )
        except UnitConversionError as exc:
            raise HTTPException(
                status_code=422, detail="PENDING_ITEM_QUANTITY_REQUIRES_REVIEW"
            ) from exc
        changed_primary = (
            Decimal(str(primary.quantity)) != native_quantity
            or (primary.ingredient_id is None and line.ingredient_id is not None)
        )
        primary.quantity = native_quantity
        if primary.ingredient_id is None:
            primary.ingredient_id = line.ingredient_id
        if removed:
            response.consolidated.append(
                ConsolidatedShoppingItems(
                    kept_item_id=primary.id,
                    removed_items=[_snapshot_deleted_item(item) for item in removed],
                )
            )
        if changed_primary or removed:
            db.flush()
            response.updated.append(_read_item(db, household_id, primary.id))
        else:
            response.unchanged.append(_read_item(db, household_id, primary.id))
        for duplicate in removed:
            db.delete(duplicate)
        return changed_primary or bool(removed)

    delta = accepted.target_quantity - line.pending_quantity
    if delta <= 0:
        response.unchanged.extend(
            _read_item(db, household_id, item.id) for item in pending_items
        )
        return False

    if len(pending_items) > 1:
        raise HTTPException(
            status_code=422,
            detail="MULTIPLE_PENDING_ITEMS_REQUIRE_EXPLICIT_CONSOLIDATION",
        )
    if len(pending_items) == 1:
        item = pending_items[0]
        try:
            native_quantity = _native_quantity_for_item(
                db, household_id, item, line.ingredient_id, accepted.target_quantity
            )
        except UnitConversionError as exc:
            raise HTTPException(
                status_code=422, detail="PENDING_ITEM_QUANTITY_REQUIRES_REVIEW"
            ) from exc
        item.quantity = native_quantity
        if item.ingredient_id is None:
            item.ingredient_id = line.ingredient_id
        db.flush()
        response.updated.append(_read_item(db, household_id, item.id))
        return True

    created = _create_recipe_item(db, household_id, recipe, line, delta)
    response.created.append(_read_item(db, household_id, created.id))
    return True


def confirm_recipe_shopping(
    db: Session,
    household_id: int,
    actor_id: int,
    request: RecipeShoppingConfirmRequest,
) -> RecipeShoppingConfirmRead:
    """Confirm all accepted lines in the caller's transaction.

    Any exception aborts this transaction. Callers that catch an exception must
    roll the session back before reusing it.
    """
    household = lock_household_write(db, household_id, actor_id=actor_id)
    request_hash = _request_hash(actor_id, household_id, request)
    existing = db.scalar(
        select(RecipeShoppingIdempotency).where(
            RecipeShoppingIdempotency.household_id == household_id,
            RecipeShoppingIdempotency.idempotency_key == request.idempotency_key,
        )
    )
    if existing is not None:
        if existing.actor_user_id != actor_id or not hmac.compare_digest(
            existing.request_hash, request_hash
        ):
            raise HTTPException(status_code=409, detail="IDEMPOTENCY_KEY_REUSED")
        return RecipeShoppingConfirmRead.model_validate(existing.response_snapshot)

    if request.expected_revision != household.shopping_revision:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    claims = _decode_preview(request.preview_id)
    if (
        claims.get("household_id") != household_id
        or claims.get("actor_user_id") != actor_id
        or claims.get("shopping_revision") != household.shopping_revision
        or claims.get("inventory_revision") != household.inventory_revision
        or claims.get("shopping_revision") != request.expected_revision
    ):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    try:
        preview_request = RecipeShoppingPreviewRequest.model_validate(claims["input"])
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc

    _lock_curated_tables(db)
    try:
        recipe, _record, evaluation, current_household, lines, unlinked, fingerprint = _preview_context(
            db, household_id, actor_id, preview_request
        )
    except HTTPException as exc:
        if exc.status_code in {403, 404, 409, 422}:
            raise HTTPException(status_code=409, detail="STALE_PREVIEW") from exc
        raise

    if (
        current_household.shopping_revision != claims.get("shopping_revision")
        or current_household.inventory_revision != claims.get("inventory_revision")
        or not hmac.compare_digest(fingerprint, str(claims.get("fingerprint", "")))
    ):
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")
    if evaluation.result.decision != "eligible":
        raise HTTPException(status_code=409, detail="STALE_PREVIEW")

    lines_by_id = {
        line.ingredient_id: line for line in lines if line.ingredient_id is not None
    }
    response = RecipeShoppingConfirmRead(
        preview_id=request.preview_id,
        shopping_revision=household.shopping_revision,
    )
    for accepted in request.accepted_lines:
        line = lines_by_id.get(accepted.ingredient_id)
        if line is None:
            raise HTTPException(status_code=422, detail="REVIEW_REQUIRED")
        changed = _apply_accepted_line(
            db, household_id, recipe, line, accepted, response
        )
        if changed:
            response.shopping_revision = household.shopping_revision + 1

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
