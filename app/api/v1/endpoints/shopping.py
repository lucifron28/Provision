from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.models.shopping import ShoppingListItem
from app.models.product import Product
from app.models.batch import InventoryBatch
from app.schemas.shopping import (
    ShoppingListItemCreate,
    ShoppingListItemUpdate,
    ShoppingListItemRead,
    AutoGenerateShoppingRequest,
)

router = APIRouter()


@router.get("/", response_model=List[ShoppingListItemRead])
def list_shopping_items(
    is_bought: Optional[bool] = Query(None, description="Filter by bought/unbought status"),
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(ShoppingListItem).options(joinedload(ShoppingListItem.product))
    if is_bought is not None:
        stmt = stmt.where(ShoppingListItem.is_bought == is_bought)
    stmt = (
        stmt.order_by(ShoppingListItem.is_bought.asc(), ShoppingListItem.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return db.scalars(stmt).all()


@router.post("/", response_model=ShoppingListItemRead, status_code=status.HTTP_201_CREATED)
def add_shopping_item(
    item_in: ShoppingListItemCreate,
    db: Session = Depends(get_db),
):
    product = None
    item_name = item_in.name
    unit = item_in.unit

    if item_in.product_id:
        product = db.get(Product, item_in.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {item_in.product_id} not found",
            )
        if not item_name:
            item_name = product.name
        if not unit and product.unit:
            unit = product.unit

    if not item_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Item name is required when product_id is not provided",
        )

    item = ShoppingListItem(
        product_id=item_in.product_id,
        name=item_name,
        quantity=item_in.quantity,
        unit=unit,
        notes=item_in.notes,
        is_bought=False,
    )
    db.add(item)
    db.commit()
    db.refresh(item)

    stmt = select(ShoppingListItem).options(joinedload(ShoppingListItem.product)).where(ShoppingListItem.id == item.id)
    return db.scalar(stmt)


@router.get("/{item_id}", response_model=ShoppingListItemRead)
def get_shopping_item(
    item_id: int,
    db: Session = Depends(get_db),
):
    stmt = select(ShoppingListItem).options(joinedload(ShoppingListItem.product)).where(ShoppingListItem.id == item_id)
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )
    return item


@router.patch("/{item_id}", response_model=ShoppingListItemRead)
def update_shopping_item(
    item_id: int,
    item_in: ShoppingListItemUpdate,
    db: Session = Depends(get_db),
):
    stmt = select(ShoppingListItem).options(joinedload(ShoppingListItem.product)).where(ShoppingListItem.id == item_id)
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )

    update_data = item_in.model_dump(exclude_unset=True)
    if "product_id" in update_data and update_data["product_id"] is not None:
        product = db.get(Product, update_data["product_id"])
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {update_data['product_id']} not found",
            )

    for field, value in update_data.items():
        setattr(item, field, value)

    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/toggle", response_model=ShoppingListItemRead)
def toggle_item_bought_status(
    item_id: int,
    db: Session = Depends(get_db),
):
    stmt = select(ShoppingListItem).options(joinedload(ShoppingListItem.product)).where(ShoppingListItem.id == item_id)
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )
    item.is_bought = not item.is_bought
    db.commit()
    db.refresh(item)
    return item


@router.post("/generate-from-low-stock", response_model=List[ShoppingListItemRead])
def generate_from_low_stock(
    req: AutoGenerateShoppingRequest = AutoGenerateShoppingRequest(),
    db: Session = Depends(get_db),
):
    """
    Scans internal product catalog and automatically generates shopping list items
    for any product whose current total on-hand stock is at or below the threshold,
    unless an unbought entry already exists on the list.
    """
    # 1. Query all products with their aggregate remaining stock
    stock_subq = (
        select(
            InventoryBatch.product_id,
            func.coalesce(func.sum(InventoryBatch.remaining_quantity), 0.0).label("total_stock"),
        )
        .where(InventoryBatch.remaining_quantity > 0)
        .group_by(InventoryBatch.product_id)
        .subquery()
    )

    stmt = (
        select(
            Product,
            func.coalesce(stock_subq.c.total_stock, 0.0).label("stock"),
        )
        .outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
    )

    results = db.execute(stmt).all()
    created_items: List[ShoppingListItem] = []

    for product, current_stock in results:
        if float(current_stock) <= req.threshold:
            # Check if active unbought item already exists for this product
            already_listed = db.scalar(
                select(ShoppingListItem).where(
                    ShoppingListItem.product_id == product.id,
                    ShoppingListItem.is_bought.is_(False),
                )
            )
            if not already_listed:
                new_item = ShoppingListItem(
                    product_id=product.id,
                    name=product.name,
                    quantity=1.0,
                    unit=product.unit,
                    is_bought=False,
                    notes=f"Auto-generated: stock is {float(current_stock):.1f} {product.unit or 'units'} (threshold: {req.threshold})",
                )
                db.add(new_item)
                created_items.append(new_item)

    if created_items:
        db.commit()
        for item in created_items:
            db.refresh(item)

    # Return full loaded items
    if not created_items:
        return []

    item_ids = [i.id for i in created_items]
    return db.scalars(
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(ShoppingListItem.id.in_(item_ids))
    ).all()


@router.delete("/completed/clear", status_code=status.HTTP_200_OK)
def clear_completed_items(db: Session = Depends(get_db)):
    items = db.scalars(select(ShoppingListItem).where(ShoppingListItem.is_bought.is_(True))).all()
    count = len(items)
    for item in items:
        db.delete(item)
    db.commit()
    return {"message": f"Successfully removed {count} completed item(s)"}


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_item(
    item_id: int,
    db: Session = Depends(get_db),
):
    item = db.get(ShoppingListItem, item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )
    db.delete(item)
    db.commit()
    return None
