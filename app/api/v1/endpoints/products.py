from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import select, func, or_

from app.core.database import get_db
from app.models.product import Product
from app.models.batch import InventoryBatch
from app.schemas.product import (
    ProductCreate,
    ProductUpdate,
    ProductRead,
    ProductWithStock,
)

router = APIRouter()


def _get_product_with_stock(db: Session, product: Product) -> ProductWithStock:
    """Helper to attach aggregate stock metrics to a product."""
    stock_info = db.execute(
        select(
            func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0.0).label("total_stock"),
            func.count(InventoryBatch.id).label("batch_count"),
        ).where(
            InventoryBatch.product_id == product.id,
            InventoryBatch.remaining_quantity > 0,
        )
    ).first()

    total_stock = float(stock_info.total_stock) if stock_info else 0.0
    batch_count = int(stock_info.batch_count) if stock_info else 0

    return ProductWithStock(
        id=product.id,
        name=product.name,
        brand=product.brand,
        barcode=product.barcode,
        category=product.category,
        package_size=product.package_size,
        unit=product.unit,
        image_url=product.image_url,
        source=product.source,
        created_at=product.created_at,
        updated_at=product.updated_at,
        total_remaining_quantity=total_stock,
        active_batches_count=batch_count,
    )


@router.get("/", response_model=List[ProductWithStock])
def list_products(
    search: Optional[str] = Query(None, description="Search by product name or brand"),
    category: Optional[str] = Query(None, description="Filter by category"),
    barcode: Optional[str] = Query(None, description="Filter by exact barcode"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(Product)
    if barcode:
        stmt = stmt.where(Product.barcode == barcode)
    if category:
        stmt = stmt.where(Product.category == category)
    if search:
        search_pattern = f"%{search}%"
        stmt = stmt.where(
            or_(
                Product.name.ilike(search_pattern),
                Product.brand.ilike(search_pattern),
            )
        )
    stmt = stmt.offset(skip).limit(limit).order_by(Product.name)
    products = db.scalars(stmt).all()

    return [_get_product_with_stock(db, p) for p in products]


@router.post("/", response_model=ProductWithStock, status_code=status.HTTP_201_CREATED)
def create_product(
    product_in: ProductCreate,
    db: Session = Depends(get_db),
):
    if product_in.barcode:
        existing = db.scalar(select(Product).where(Product.barcode == product_in.barcode))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with barcode '{product_in.barcode}' already exists (ID: {existing.id})",
            )
    product = Product(
        name=product_in.name,
        brand=product_in.brand,
        barcode=product_in.barcode,
        category=product_in.category,
        package_size=product_in.package_size,
        unit=product_in.unit,
        image_url=product_in.image_url,
        source=product_in.source,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return _get_product_with_stock(db, product)


@router.get("/barcode/{barcode}", response_model=ProductWithStock)
def get_product_by_barcode(
    barcode: str,
    db: Session = Depends(get_db),
):
    product = db.scalar(select(Product).where(Product.barcode == barcode))
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{barcode}' not found",
        )
    return _get_product_with_stock(db, product)


@router.get("/{product_id}", response_model=ProductWithStock)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    return _get_product_with_stock(db, product)


@router.patch("/{product_id}", response_model=ProductWithStock)
def update_product(
    product_id: int,
    product_in: ProductUpdate,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )
    update_data = product_in.model_dump(exclude_unset=True)
    if "barcode" in update_data and update_data["barcode"] != product.barcode:
        existing = db.scalar(select(Product).where(Product.barcode == update_data["barcode"]))
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product with barcode '{update_data['barcode']}' already exists",
            )
    for field, value in update_data.items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return _get_product_with_stock(db, product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found",
        )

    batch_count = db.scalar(
        select(func.count(InventoryBatch.id)).where(InventoryBatch.product_id == product_id)
    ) or 0
    if batch_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Cannot delete product with ID {product_id}: it has {batch_count} associated inventory batch(es). Deletion blocked to preserve inventory history.",
        )

    db.delete(product)
    db.commit()
    return None
