"""Household price estimates and recorded waste, with explicit data coverage."""
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext

from sqlalchemy import select

from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.ingredient import Ingredient, ProductIngredientMapping, ProductIngredientMappingTarget, ProductPackageFactor
from app.models.product import Product
from app.models.session import GrocerySession
from app.schemas.meal_insights import MealBudgetLine, MealBudgetRead, WasteEventRead, WastePeriodRead, WasteUnitTotal
from app.services.preferences import read_profile
from app.services.recipes import evaluate_recipe
from app.services.units import UnitConversionError, convert_amount


def _money(amount):
    return amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _price_candidates(db, household_id, ingredient_ids):
    products = {item.id: item for item in db.scalars(select(Product).where(Product.household_id == household_id)).all()}
    mappings = db.scalars(select(ProductIngredientMapping).where(
        ProductIngredientMapping.household_id == household_id, ProductIngredientMapping.is_current.is_(True),
        ProductIngredientMapping.mode == "DIRECT", ProductIngredientMapping.verification_status == "VERIFIED",
        ProductIngredientMapping.verified_at.is_not(None), ProductIngredientMapping.unknown_composition.is_(False),
        ProductIngredientMapping.ingredient_id.in_(ingredient_ids))).all()
    candidates = {}
    for mapping in mappings:
        product = products.get(mapping.product_id)
        ingredient = db.get(Ingredient, mapping.ingredient_id)
        targets = set(db.scalars(select(ProductIngredientMappingTarget.ingredient_id).where(
            ProductIngredientMappingTarget.household_id == household_id,
            ProductIngredientMappingTarget.product_id == mapping.product_id,
            ProductIngredientMappingTarget.mapping_version == mapping.version)).all())
        if product is None or ingredient is None or not ingredient.is_active or targets != {ingredient.id}:
            continue
        factor = db.scalar(select(ProductPackageFactor).where(ProductPackageFactor.household_id == household_id,
            ProductPackageFactor.product_id == product.id, ProductPackageFactor.mapping_version == mapping.version,
            ProductPackageFactor.ingredient_id == ingredient.id))
        try:
            if factor:
                if " ".join((product.unit or "").casefold().split()) != " ".join(factor.inventory_unit.casefold().split()):
                    continue
                ingredient_per_unit = convert_amount(factor.ingredient_amount, factor.ingredient_unit, ingredient.default_unit or "")
            else:
                ingredient_per_unit = convert_amount(Decimal("1"), product.unit or "", ingredient.default_unit or "")
        except UnitConversionError:
            continue
        if ingredient_per_unit <= 0:
            continue
        priced = db.scalar(select(InventoryBatch).where(InventoryBatch.household_id == household_id,
            InventoryBatch.product_id == product.id, InventoryBatch.unit_price.is_not(None),
            # Legacy batches do not store their unit at purchase. A later product
            # edit can change that unit, so do not reinterpret an older price.
            InventoryBatch.created_at >= product.updated_at,
            InventoryBatch.unit_price >= 0, InventoryBatch.purchased_at <= datetime.now(timezone.utc))
            .order_by(InventoryBatch.purchased_at.desc(), InventoryBatch.id.desc()).limit(1))
        if priced is None or not priced.unit_price.is_finite():
            continue
        previous = candidates.get(ingredient.id)
        if previous is None or (priced.purchased_at, priced.id) > (previous[0].purchased_at, previous[0].id):
            candidates[ingredient.id] = priced, product, ingredient_per_unit
    return candidates


def recipe_budget(db, household_id, actor_id, recipe_id, request):
    evaluation = evaluate_recipe(db, household_id, recipe_id, request)
    availability = evaluation.result.availability
    ingredient_ids = {line.ingredient_id for line in availability.requirements if line.ingredient_id is not None}
    candidates = _price_candidates(db, household_id, ingredient_ids)
    lines, subtotal = [], Decimal("0")
    for requirement in availability.requirements:
        line = MealBudgetLine(ingredient_id=requirement.ingredient_id,
            ingredient_name=requirement.canonical_name or " / ".join(requirement.display_names),
            amount=requirement.required_amount, unit=requirement.unit)
        if requirement.required_amount is None:
            line.missing_reason = "requirement_quantity_unknown"
        elif requirement.ingredient_id not in candidates:
            line.missing_reason = "no_verified_convertible_historical_price"
        else:
            batch, product, ingredient_per_unit = candidates[requirement.ingredient_id]
            with localcontext() as context:
                context.prec = 50
                amount = requirement.required_amount * batch.unit_price / ingredient_per_unit
            subtotal += amount
            line.estimated_cost_php = _money(amount)
            line.price_batch_id, line.price_product_id = batch.id, product.id
            line.historical_unit_price_php = batch.unit_price
            line.price_inventory_unit, line.purchased_at = product.unit, batch.purchased_at
            if batch.grocery_session_id:
                session = db.scalar(select(GrocerySession).where(GrocerySession.household_id == household_id,
                    GrocerySession.id == batch.grocery_session_id))
                line.store_name = session.store_name if session else None
        lines.append(line)
    complete = bool(lines) and all(line.missing_reason is None for line in lines)
    goal = read_profile(db, household_id, actor_id).preferences.meal_budget_php
    if goal is None:
        goal = read_profile(db, household_id, None).preferences.meal_budget_php
    total = _money(subtotal) if complete else None
    return MealBudgetRead(recipe_id=recipe_id, recipe_revision=evaluation.recipe_revision, complete=complete,
        known_cost_subtotal_php=_money(subtotal), estimated_total_php=total, budget_goal_php=goal,
        estimated_within_budget=(total <= goal if total is not None and goal is not None else None), lines=lines)


def waste_for_period(db, household_id, request):
    records = db.execute(select(InventoryEvent, InventoryBatch, Product).join(
        InventoryBatch, InventoryBatch.id == InventoryEvent.batch_id).join(Product, Product.id == InventoryBatch.product_id)
        .where(InventoryBatch.household_id == household_id, Product.household_id == household_id,
            InventoryEvent.event_type.in_([EventType.DISCARDED, EventType.EXPIRED]),
            InventoryEvent.occurred_at >= request.start, InventoryEvent.occurred_at < request.end)
        .order_by(InventoryEvent.occurred_at, InventoryEvent.id)).all()
    totals, events, subtotal, priced_count = defaultdict(lambda: Decimal("0")), [], Decimal("0"), 0
    for event, batch, product in records:
        quantity = Decimal(str(event.quantity))
        unit_history_known = product.updated_at <= batch.created_at
        usable_price = (batch.unit_price is not None and batch.unit_price.is_finite()
            and batch.unit_price >= 0 and unit_history_known)
        loss = quantity * batch.unit_price if usable_price else None
        if loss is not None:
            subtotal += loss
            priced_count += 1
        unit = " ".join(product.unit.strip().casefold().split()) if unit_history_known and product.unit and product.unit.strip() else None
        totals[unit] += quantity
        events.append(WasteEventRead(event_id=event.id, batch_id=batch.id, product_id=product.id,
            quantity=quantity, unit=unit, occurred_at=event.occurred_at, type=event.event_type.value,
            recorded_unit_price_php=batch.unit_price if batch.unit_price is None or batch.unit_price.is_finite() else None,
            estimated_loss_php=_money(loss) if loss is not None else None,
            cost_unknown_reason=(None if usable_price else "purchase_unit_history_unknown" if not unit_history_known
                else "recorded_price_unavailable")))
    return WastePeriodRead(start=request.start, end=request.end, event_count=len(events), priced_event_count=priced_count,
        unpriced_event_count=len(events)-priced_count, known_loss_subtotal_php=_money(subtotal),
        estimated_total_loss_php=_money(subtotal) if priced_count == len(events) else None,
        quantities_by_unit=[WasteUnitTotal(unit=unit, quantity=totals[unit]) for unit in sorted(totals, key=lambda value: value or "")],
        events=events)
