from datetime import datetime, timezone
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.ingredient import ProductIngredientMapping
from app.models.product import Product
from app.models.product_label import ProductAllergenLabel
from app.schemas.product_label import ProductLabelInput, ProductLabelRead


def product_fingerprint(product: Product) -> str:
    fields = {name: getattr(product, name) for name in ("name", "brand", "barcode", "category", "unit")}
    fields["package_size"] = str(product.package_size) if product.package_size is not None else None
    fields["updated_at"] = product.updated_at.isoformat()
    return hashlib.sha256(json.dumps(fields, sort_keys=True, ensure_ascii=True).encode()).hexdigest()


def _product(db, household_id, product_id, *, lock=False):
    statement = select(Product).where(Product.household_id == household_id, Product.id == product_id)
    if lock:
        statement = statement.with_for_update()
    product = db.scalar(statement.execution_options(populate_existing=True))
    if product is None:
        raise HTTPException(404, "Product not found")
    return product


def _current(db, household_id, product_id):
    return db.scalar(select(ProductAllergenLabel).where(ProductAllergenLabel.household_id == household_id,
        ProductAllergenLabel.product_id == product_id, ProductAllergenLabel.is_current.is_(True))
        .execution_options(populate_existing=True))


def _mapping(db, household_id, product_id):
    return db.scalar(select(ProductIngredientMapping).where(ProductIngredientMapping.household_id == household_id,
        ProductIngredientMapping.product_id == product_id, ProductIngredientMapping.is_current.is_(True))
        .execution_options(populate_existing=True))


def _latest(db, household_id, product_id):
    return db.scalar(select(ProductAllergenLabel).where(ProductAllergenLabel.household_id == household_id,
        ProductAllergenLabel.product_id == product_id).order_by(ProductAllergenLabel.revision.desc()).limit(1)
        .execution_options(populate_existing=True))


def current_label_context(db, household_id, product):
    label = _current(db, household_id, product.id)
    mapping = _mapping(db, household_id, product.id)
    usable = bool(label and mapping and mapping.version == label.mapping_version
        and mapping.verification_status == "VERIFIED" and mapping.verified_at is not None
        and not mapping.unknown_composition and mapping.mode in {"DIRECT", "COMPOSITE"}
        and product_fingerprint(product) == label.product_fingerprint)
    return label, mapping, usable


def _read(db, household_id, product):
    _, _, usable = current_label_context(db, household_id, product)
    label = _latest(db, household_id, product.id)
    if label is None:
        raise HTTPException(404, "Product label review not recorded")
    fields = {name: getattr(label, name) for name in ProductLabelRead.model_fields if name not in {"current_for_product", "revoked"}}
    return ProductLabelRead(**fields, current_for_product=usable and label.is_current, revoked=label.revoked_at is not None)


def read_label(db: Session, household_id: int, product_id: int):
    return _read(db, household_id, _product(db, household_id, product_id))


def _lock_writer(db, household_id, product_id, actor_id):
    db.scalar(select(Household.id).where(Household.id == household_id).with_for_update())
    if db.scalar(select(HouseholdMembership.id).where(HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id)) is None:
        raise HTTPException(403, "Household membership is required")
    return _product(db, household_id, product_id, lock=True)


def write_label(db: Session, household_id: int, product_id: int, actor_id: int, request: ProductLabelInput):
    product = _lock_writer(db, household_id, product_id, actor_id)
    if request.expected_product_updated_at != product.updated_at:
        raise HTTPException(409, "PRODUCT_CHANGED")
    current = _current(db, household_id, product_id)
    latest = _latest(db, household_id, product_id)
    if request.expected_revision != (latest.revision if latest else None):
        raise HTTPException(409, "PRODUCT_LABEL_REVISION_CONFLICT")
    mapping = _mapping(db, household_id, product_id)
    if mapping is None or mapping.version != request.expected_mapping_version:
        raise HTTPException(409, "MAPPING_VERSION_CONFLICT")
    if mapping.verification_status != "VERIFIED" or mapping.verified_at is None or mapping.unknown_composition or mapping.mode == "UNKNOWN":
        raise HTTPException(422, "A reviewed mapping with known composition is required")
    last_revision = db.scalar(select(func.max(ProductAllergenLabel.revision)).where(
        ProductAllergenLabel.household_id == household_id, ProductAllergenLabel.product_id == product_id)) or 0
    if current:
        current.is_current = False
        db.flush()
    db.add(ProductAllergenLabel(household_id=household_id, product_id=product_id, mapping_version=mapping.version,
        revision=last_revision + 1, is_current=True, product_fingerprint=product_fingerprint(product),
        declared_allergens=sorted(request.declared_allergens), possible_allergens=sorted(request.possible_allergens),
        custom_allergens=sorted(request.custom_allergens), composition_known=request.composition_known,
        source_reference=request.source_reference, reviewed_by_user_id=actor_id, reviewed_at=datetime.now(timezone.utc)))
    db.commit()
    return _read(db, household_id, product)


def revoke_label(db: Session, household_id: int, product_id: int, actor_id: int, expected_revision: int):
    _lock_writer(db, household_id, product_id, actor_id)
    label = _current(db, household_id, product_id)
    if label is None or label.revision != expected_revision:
        raise HTTPException(409, "PRODUCT_LABEL_REVISION_CONFLICT")
    label.is_current = False
    fields = {name: getattr(label, name) for name in ("household_id", "product_id", "mapping_version",
        "product_fingerprint", "declared_allergens", "possible_allergens", "custom_allergens",
        "composition_known", "source_reference", "reviewed_by_user_id", "reviewed_at")}
    db.add(ProductAllergenLabel(**fields, revision=label.revision + 1, is_current=False,
        revoked_by_user_id=actor_id, revoked_at=datetime.now(timezone.utc)))
    db.commit()
