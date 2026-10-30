"""Read-only, household-scoped recipe requirement coverage."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, localcontext

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.time import household_today
from app.models.batch import InventoryBatch
from app.models.ingredient import (
    Ingredient,
    ProductIngredientMapping,
    ProductIngredientMappingTarget,
    ProductPackageFactor,
)
from app.models.product import Product
from app.schemas.ingredients import (
    AvailabilityStatus,
    IngredientAvailabilityLine,
    IngredientRequirementInput,
    RecipeAvailabilityRead,
    RecipeAvailabilityRequest,
)
from app.services.ingredient_matching import resolve_ingredient
from app.services.units import UnitConversionError, convert_amount, normalize_unit


@dataclass
class _RequirementGroup:
    ingredient: Ingredient | None
    required: bool
    display_names: list[str] = field(default_factory=list)
    required_amount: Decimal | None = Decimal("0")
    unit: str | None = None
    unknown_reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _StockEntry:
    batch_id: int
    expiration_date: date | None
    purchased_at: datetime
    amount: Decimal


def _normalized_unit(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.casefold().split())


def _scale_amount(amount: Decimal, request: RecipeAvailabilityRequest) -> Decimal:
    # Multiply before dividing so an exact result such as 3 * 1 / 3 stays exact.
    # Fifty digits cover the bounded request fields, unit factors and line sums.
    with localcontext() as context:
        context.prec = 50
        return amount * request.servings / request.recipe_servings


def _group_requirements(
    db: Session,
    request: RecipeAvailabilityRequest,
) -> tuple[dict[tuple[int, bool], _RequirementGroup], list[_RequirementGroup]]:
    groups: dict[tuple[int, bool], _RequirementGroup] = {}
    unresolved: list[_RequirementGroup] = []

    for requirement in request.requirements:
        resolution = resolve_ingredient(
            db,
            ingredient_id=requirement.ingredient_id,
            display_name=requirement.display_name,
        )
        display = requirement.display_name or (
            resolution.ingredient.canonical_name if resolution.ingredient else ""
        )
        if resolution.ingredient is None:
            try:
                normalized = normalize_unit(requirement.unit)
                amount = _scale_amount(requirement.amount, request)
            except UnitConversionError:
                normalized = None
                amount = None
            unresolved_group = _RequirementGroup(
                ingredient=None,
                required=requirement.required,
                display_names=[display],
                required_amount=amount,
                unit=normalized,
                unknown_reasons=[resolution.reason or "ingredient_not_resolved"],
            )
            if resolution.ambiguous:
                unresolved_group.unknown_reasons = ["ambiguous_ingredient_name"]
            if normalized is None:
                unresolved_group.unknown_reasons.append("unsupported_requirement_unit")
            unresolved.append(unresolved_group)
            continue

        ingredient = resolution.ingredient
        key = (ingredient.id, requirement.required)
        group = groups.get(key)
        if group is None:
            group = _RequirementGroup(ingredient=ingredient, required=requirement.required)
            try:
                group.unit = normalize_unit(ingredient.default_unit or requirement.unit)
            except UnitConversionError:
                group.required_amount = None
                group.unknown_reasons.append("unsupported_ingredient_default_unit")
            groups[key] = group
        if display and display not in group.display_names:
            group.display_names.append(display)

        if group.unit is None or group.required_amount is None:
            if "unsupported_ingredient_default_unit" not in group.unknown_reasons:
                group.unknown_reasons.append("unsupported_requirement_unit")
            continue
        try:
            converted = convert_amount(requirement.amount, requirement.unit, group.unit)
            group.required_amount += converted
        except UnitConversionError:
            group.required_amount = None
            group.unknown_reasons.append("unsupported_or_incompatible_requirement_unit")

    for group in groups.values():
        if group.required_amount is not None:
            group.required_amount = _scale_amount(group.required_amount, request)
    return groups, unresolved


def _consume_entries(
    entries: list[_StockEntry], demand: Decimal
) -> tuple[list[int], list[_StockEntry], Decimal]:
    remaining = demand
    covered: list[int] = []
    leftovers: list[_StockEntry] = []
    for entry in entries:
        used = min(entry.amount, remaining)
        if used > 0:
            covered.append(entry.batch_id)
            remaining -= used
        left = entry.amount - used
        if left > 0:
            leftovers.append(
                _StockEntry(
                    batch_id=entry.batch_id,
                    expiration_date=entry.expiration_date,
                    purchased_at=entry.purchased_at,
                    amount=left,
                )
            )
    return covered, leftovers, demand - remaining


def _line_status(required: Decimal, available: Decimal) -> tuple[AvailabilityStatus, Decimal]:
    shortfall = max(required - available, Decimal("0"))
    if shortfall == 0:
        return "full", shortfall
    if available > 0:
        return "partial", shortfall
    return "missing", shortfall


def _load_scoped_stock(
    db: Session,
    household_id: int,
    ingredient_ids: set[int],
) -> tuple[dict[int, list[_StockEntry]], dict[int, set[str]], dict[int, set[int]]]:
    stock: dict[int, list[_StockEntry]] = defaultdict(list)
    uncertain: dict[int, set[str]] = defaultdict(set)
    missing_expiry: dict[int, set[int]] = defaultdict(set)
    if not ingredient_ids:
        return stock, uncertain, missing_expiry

    mappings = db.scalars(
        select(ProductIngredientMapping)
        .where(
            ProductIngredientMapping.household_id == household_id,
            ProductIngredientMapping.is_current.is_(True),
        )
        .order_by(ProductIngredientMapping.product_id)
    ).all()
    if not mappings:
        return stock, uncertain, missing_expiry

    product_ids = {mapping.product_id for mapping in mappings}
    products = {
        product.id: product
        for product in db.scalars(
            select(Product).where(
                Product.household_id == household_id,
                Product.id.in_(product_ids),
            )
        ).all()
    }
    today = household_today()
    batches = db.scalars(
        select(InventoryBatch)
        .where(
            InventoryBatch.household_id == household_id,
            InventoryBatch.product_id.in_(product_ids),
            InventoryBatch.remaining_quantity > 0,
            or_(InventoryBatch.expiration_date.is_(None), InventoryBatch.expiration_date >= today),
        )
        .order_by(
            InventoryBatch.expiration_date.asc().nulls_last(),
            InventoryBatch.purchased_at.asc(),
            InventoryBatch.id.asc(),
        )
    ).all()
    batches_by_product: dict[int, list[InventoryBatch]] = defaultdict(list)
    for batch in batches:
        batches_by_product[batch.product_id].append(batch)

    targets = db.scalars(
        select(ProductIngredientMappingTarget).where(
            ProductIngredientMappingTarget.household_id == household_id,
            ProductIngredientMappingTarget.product_id.in_(product_ids),
        )
    ).all()
    targets_by_mapping: dict[tuple[int, int], list[int]] = defaultdict(list)
    for target in targets:
        targets_by_mapping[(target.product_id, target.mapping_version)].append(target.ingredient_id)

    factors = db.scalars(
        select(ProductPackageFactor).where(
            ProductPackageFactor.household_id == household_id,
            ProductPackageFactor.product_id.in_(product_ids),
        )
    ).all()
    factors_by_mapping = {
        (factor.product_id, factor.mapping_version, factor.ingredient_id): factor
        for factor in factors
    }

    for mapping in mappings:
        product_batches = batches_by_product.get(mapping.product_id, [])
        if not product_batches:
            continue
        product = products.get(mapping.product_id)
        if product is None:
            continue

        target_ids = sorted(
            set(targets_by_mapping.get((mapping.product_id, mapping.version), []))
        )
        if mapping.mode == "DIRECT":
            ingredient_id = mapping.ingredient_id
            if ingredient_id is None:
                continue
            if target_ids != [ingredient_id]:
                uncertain[ingredient_id].add("mapping_target_inconsistent")
                continue
            target_ids = [ingredient_id]
        elif mapping.mode == "COMPOSITE":
            if not target_ids:
                for ingredient_id in ingredient_ids:
                    uncertain[ingredient_id].add("composite_components_missing")
                continue
        else:
            continue

        for ingredient_id in target_ids:
            if ingredient_id not in ingredient_ids:
                continue
            if mapping.verification_status != "VERIFIED" or mapping.verified_at is None:
                uncertain[ingredient_id].add("mapping_unverified")
                for batch in product_batches:
                    if batch.expiration_date is None:
                        missing_expiry[ingredient_id].add(batch.id)
                continue
            if mapping.unknown_composition:
                uncertain[ingredient_id].add("composition_unknown")
                for batch in product_batches:
                    if batch.expiration_date is None:
                        missing_expiry[ingredient_id].add(batch.id)
                continue

            factor = factors_by_mapping.get(
                (mapping.product_id, mapping.version, ingredient_id)
            )
            if mapping.mode == "COMPOSITE" and factor is None:
                uncertain[ingredient_id].add("verified_component_quantity_missing")
                continue

            for batch in product_batches:
                if batch.expiration_date is None:
                    missing_expiry[ingredient_id].add(batch.id)
                batch_quantity = Decimal(str(batch.remaining_quantity))
                try:
                    if factor is not None:
                        if _normalized_unit(product.unit) != _normalized_unit(factor.inventory_unit):
                            raise UnitConversionError("Package factor inventory unit does not match product unit")
                        ingredient_amount = batch_quantity * Decimal(str(factor.ingredient_amount))
                        converted = convert_amount(
                            ingredient_amount,
                            factor.ingredient_unit,
                            db.get(Ingredient, ingredient_id).default_unit or "",
                        )
                        stock[ingredient_id].append(
                            _StockEntry(
                                batch_id=batch.id,
                                expiration_date=batch.expiration_date,
                                purchased_at=batch.purchased_at,
                                amount=converted,
                            )
                        )
                    else:
                        source_unit = normalize_unit(product.unit or "")
                        # Stock is kept in the ingredient's curated default unit.
                        ingredient = db.get(Ingredient, ingredient_id)
                        target_unit = normalize_unit(ingredient.default_unit or "") if ingredient else ""
                        converted = convert_amount(batch_quantity, source_unit, target_unit)
                        stock[ingredient_id].append(
                            _StockEntry(
                                batch_id=batch.id,
                                expiration_date=batch.expiration_date,
                                purchased_at=batch.purchased_at,
                                amount=converted,
                            )
                        )
                except UnitConversionError:
                    uncertain[ingredient_id].add("unknown_or_incompatible_product_unit")

    for ingredient_id, entries in stock.items():
        entries.sort(
            key=lambda item: (
                item.expiration_date is None,
                item.expiration_date or date.max,
                item.purchased_at,
                item.batch_id,
            )
        )
    return stock, uncertain, missing_expiry


def _render_group(
    group: _RequirementGroup,
    stock: list[_StockEntry],
    mapping_unknown: set[str],
    missing_expiry: set[int],
    required_demand_for_optional: Decimal | None = None,
) -> tuple[IngredientAvailabilityLine, list[_StockEntry]]:
    if group.required_amount is None or group.unit is None:
        reasons = list(dict.fromkeys(group.unknown_reasons + sorted(mapping_unknown)))
        return (
            IngredientAvailabilityLine(
                ingredient_id=group.ingredient.id if group.ingredient else None,
                canonical_name=group.ingredient.canonical_name if group.ingredient else None,
                display_names=group.display_names,
                required=group.required,
                required_amount=None,
                available_amount=None,
                shortfall=None,
                unit=group.unit,
                status="unknown",
                covered_batch_ids=[],
                missing_expiry_batch_ids=sorted(missing_expiry),
                unknown_reasons=reasons or ["requirement_quantity_unknown"],
            ),
            stock,
        )

    available_entries = stock
    prior_covered: list[int] = []
    if not group.required and required_demand_for_optional is not None:
        prior_covered, available_entries, _ = _consume_entries(stock, required_demand_for_optional)

    available_amount = sum((entry.amount for entry in available_entries), Decimal("0"))
    covered, _leftovers, _allocated = _consume_entries(available_entries, group.required_amount)
    all_unknown = list(dict.fromkeys(group.unknown_reasons + sorted(mapping_unknown)))
    if not group.required and required_demand_for_optional is None and mapping_unknown:
        all_unknown.append("required_demand_unknown_for_optional_coverage")

    if all_unknown:
        status: AvailabilityStatus = "unknown"
        shortfall = None
    else:
        status, shortfall = _line_status(group.required_amount, available_amount)

    return (
        IngredientAvailabilityLine(
            ingredient_id=group.ingredient.id if group.ingredient else None,
            canonical_name=group.ingredient.canonical_name if group.ingredient else None,
            display_names=group.display_names,
            required=group.required,
            required_amount=group.required_amount,
            available_amount=available_amount,
            shortfall=shortfall,
            unit=group.unit,
            status=status,
            covered_batch_ids=covered,
            missing_expiry_batch_ids=sorted(missing_expiry),
            unknown_reasons=all_unknown,
        ),
        available_entries,
    )


def calculate_availability(
    db: Session,
    household_id: int,
    request: RecipeAvailabilityRequest,
) -> RecipeAvailabilityRead:
    """Compare requested requirements with usable stock without writing to the database."""
    groups, unresolved = _group_requirements(db, request)
    ingredient_ids = {ingredient_id for ingredient_id, _required in groups}
    stock, uncertain, missing_expiry = _load_scoped_stock(db, household_id, ingredient_ids)

    by_ingredient: dict[int, dict[bool, _RequirementGroup]] = defaultdict(dict)
    for (ingredient_id, required), group in groups.items():
        by_ingredient[ingredient_id][required] = group

    rendered: list[IngredientAvailabilityLine] = []
    for ingredient_id in sorted(
        by_ingredient,
        key=lambda item: by_ingredient[item][True].ingredient.canonical_name.casefold()
        if True in by_ingredient[item]
        else by_ingredient[item][False].ingredient.canonical_name.casefold(),
    ):
        entry_groups = by_ingredient[ingredient_id]
        entries = stock.get(ingredient_id, [])
        required_group = entry_groups.get(True)
        required_demand: Decimal | None = None
        if required_group is not None and required_group.required_amount is not None:
            required_demand = required_group.required_amount
            line, _ = _render_group(
                required_group,
                entries,
                uncertain.get(ingredient_id, set()),
                missing_expiry.get(ingredient_id, set()),
            )
            rendered.append(line)
        optional_group = entry_groups.get(False)
        if optional_group is not None:
            optional_unknown = set(uncertain.get(ingredient_id, set()))
            if required_group is not None and required_demand is None:
                optional_unknown.add("required_demand_unknown_for_optional_coverage")
            line, _ = _render_group(
                optional_group,
                entries,
                optional_unknown,
                missing_expiry.get(ingredient_id, set()),
                required_demand_for_optional=required_demand,
            )
            rendered.append(line)

    for group in unresolved:
        if group.required_amount is None or group.unit is None:
            rendered.append(
                IngredientAvailabilityLine(
                    ingredient_id=None,
                    canonical_name=None,
                    display_names=group.display_names,
                    required=group.required,
                    required_amount=group.required_amount,
                    available_amount=None,
                    shortfall=None,
                    unit=group.unit,
                    status="unknown",
                    covered_batch_ids=[],
                    missing_expiry_batch_ids=[],
                    unknown_reasons=list(dict.fromkeys(group.unknown_reasons)),
                )
            )
            continue
        rendered.append(
            IngredientAvailabilityLine(
                ingredient_id=None,
                canonical_name=None,
                display_names=group.display_names,
                required=group.required,
                required_amount=group.required_amount,
                available_amount=None,
                shortfall=None,
                unit=group.unit,
                status="unknown",
                covered_batch_ids=[],
                missing_expiry_batch_ids=[],
                unknown_reasons=list(dict.fromkeys(group.unknown_reasons)),
            )
        )

    required_lines = [line for line in rendered if line.required]
    if not required_lines or all(line.status == "full" for line in required_lines):
        overall_status: AvailabilityStatus = "full"
    elif any(line.status == "unknown" for line in required_lines):
        overall_status = "unknown"
    elif any(line.available_amount and line.available_amount > 0 for line in required_lines):
        overall_status = "partial"
    else:
        overall_status = "missing"

    return RecipeAvailabilityRead(
        recipe_servings=request.recipe_servings,
        servings=request.servings,
        overall_status=overall_status,
        requirements=rendered,
    )
