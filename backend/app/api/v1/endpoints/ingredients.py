from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.ingredient import Ingredient, ProductIngredientMapping, ProductIngredientMappingTarget, ProductPackageFactor
from app.models.product import Product
from app.models.user import User
from app.schemas.ingredients import (
    IngredientLookupRead, MappingMode, PackageFactorRead, ProductIngredientMappingRead,
    ProductIngredientMappingUpsert, RecipeAvailabilityRead, RecipeAvailabilityRequest,
)
from app.services.ingredient_matching import lookup_ingredients
from app.services.recipe_availability import calculate_availability
from app.services.units import UnitConversionError, convert_amount
from app.services.household_writes import bump_inventory_revision, lock_household_write

router = APIRouter()


def _product(db, household_id, product_id, *, lock=False):
    statement = select(Product).where(Product.household_id == household_id, Product.id == product_id)
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    product = db.scalar(statement)
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


def _current(db, household_id, product_id):
    return db.scalar(select(ProductIngredientMapping).where(
        ProductIngredientMapping.household_id == household_id,
        ProductIngredientMapping.product_id == product_id,
        ProductIngredientMapping.is_current.is_(True),
    ).execution_options(populate_existing=True))


def _read(db, mapping):
    scope = dict(household_id=mapping.household_id, product_id=mapping.product_id, mapping_version=mapping.version)
    targets = db.scalars(select(ProductIngredientMappingTarget).filter_by(**scope)
                         .order_by(ProductIngredientMappingTarget.ingredient_id)).all()
    factors = db.scalars(select(ProductPackageFactor).filter_by(**scope)
                         .order_by(ProductPackageFactor.ingredient_id)).all()
    fields = {name: getattr(mapping, name) for name in ProductIngredientMappingRead.model_fields
              if name not in {"component_ingredient_ids", "package_factors"}}
    fields["component_ingredient_ids"] = [target.ingredient_id for target in targets] if mapping.mode == "COMPOSITE" else []
    fields["package_factors"] = [PackageFactorRead.model_validate(
        {name: getattr(factor, name) for name in PackageFactorRead.model_fields}) for factor in factors]
    return ProductIngredientMappingRead(**fields)


@router.get("/", response_model=IngredientLookupRead)
def lookup(query: str | None = Query(None, max_length=180), limit: int = Query(50, ge=1, le=100),
           household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    return lookup_ingredients(db, query, limit)


@router.post("/availability", response_model=RecipeAvailabilityRead)
def availability(request: RecipeAvailabilityRequest, household_id: int = Depends(get_current_household_id),
                 db: Session = Depends(get_db)):
    return calculate_availability(db, household_id, request)


@router.get("/products/{product_id}/mapping", response_model=ProductIngredientMappingRead)
def get_mapping(product_id: int, household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    _product(db, household_id, product_id)
    mapping = _current(db, household_id, product_id)
    if mapping is None:
        raise HTTPException(404, "Mapping not recorded")
    return _read(db, mapping)


@router.put("/products/{product_id}/mapping", response_model=ProductIngredientMappingRead)
def put_mapping(product_id: int, request: ProductIngredientMappingUpsert,
                household_id: int = Depends(get_current_household_id_for_write),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    lock_household_write(db, household_id, actor_id=user.id)
    product = _product(db, household_id, product_id, lock=True)
    current = _current(db, household_id, product_id)
    if request.expected_version != (current.version if current else None):
        raise HTTPException(409, "MAPPING_VERSION_CONFLICT")
    target_ids = ([request.ingredient_id] if request.mode == MappingMode.DIRECT
                  else [item.ingredient_id for item in request.components])
    ingredients = {item.id: item for item in db.scalars(select(Ingredient).where(
        Ingredient.id.in_(target_ids), Ingredient.is_active.is_(True))).all()}
    if set(ingredients) != set(target_ids):
        raise HTTPException(422, "Mapping references an unavailable ingredient")
    for factor in request.package_factors:
        if " ".join((product.unit or "").casefold().split()) != " ".join(factor.inventory_unit.casefold().split()):
            raise HTTPException(422, "Package factor must describe the product inventory unit")
        try:
            convert_amount(factor.ingredient_amount, factor.ingredient_unit,
                           ingredients[factor.ingredient_id].default_unit or "")
        except UnitConversionError as exc:
            raise HTTPException(422, str(exc)) from exc
    now = datetime.now(timezone.utc)
    if current:
        current.is_current = False
        db.flush()
    mapping = ProductIngredientMapping(household_id=household_id, product_id=product_id,
        version=current.version + 1 if current else 1, is_current=True, mode=request.mode.value,
        ingredient_id=request.ingredient_id,
        verification_status="UNKNOWN" if request.mode == MappingMode.UNKNOWN else ("VERIFIED" if request.verified else "UNVERIFIED"),
        method=request.method, verified_by_user_id=user.id if request.verified else None,
        verified_at=now if request.verified else None, confidence=request.confidence,
        unknown_composition=request.unknown_composition)
    db.add(mapping)
    db.flush()
    for ingredient_id in target_ids:
        db.add(ProductIngredientMappingTarget(household_id=household_id, product_id=product_id,
            mapping_version=mapping.version, ingredient_id=ingredient_id))
    db.flush()
    for factor in request.package_factors:
        db.add(ProductPackageFactor(household_id=household_id, product_id=product_id,
            mapping_version=mapping.version, **factor.model_dump(), verified_by_user_id=user.id, verified_at=now))
    bump_inventory_revision(db, household_id)
    db.commit()
    db.refresh(mapping)
    return _read(db, mapping)
