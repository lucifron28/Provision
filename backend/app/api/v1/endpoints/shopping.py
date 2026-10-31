from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, and_

from app.core.database import get_db
from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.models.shopping import ShoppingListItem
from app.models.product import Product
from app.models.batch import InventoryBatch
from app.models.ingredient import Ingredient
from app.models.recipe import Recipe
from app.services.household_writes import bump_shopping_revision
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
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(ShoppingListItem.household_id == household_id)
    )
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
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    product = None
    item_name = item_in.name
    unit = item_in.unit

    if item_in.product_id is not None:
        product = db.scalar(
            select(Product).where(
                Product.id == item_in.product_id,
                Product.household_id == household_id,
            ).execution_options(populate_existing=True)
        )
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

    if item_in.ingredient_id is not None:
        ingredient = db.scalar(
            select(Ingredient).where(
                Ingredient.id == item_in.ingredient_id,
                Ingredient.is_active.is_(True),
            ).execution_options(populate_existing=True)
        )
        if ingredient is None:
            raise HTTPException(status_code=422, detail="Ingredient is not active")

    origin_recipe_revision = None
    if item_in.origin_recipe_id is not None:
        recipe = db.scalar(
            select(Recipe).where(
                Recipe.id == item_in.origin_recipe_id,
                Recipe.household_id == household_id,
                Recipe.is_active.is_(True),
            ).execution_options(populate_existing=True)
        )
        if recipe is None:
            raise HTTPException(status_code=404, detail="Origin recipe not found")
        origin_recipe_revision = recipe.revision

    item = ShoppingListItem(
        household_id=household_id,
        product_id=item_in.product_id,
        ingredient_id=item_in.ingredient_id,
        origin_recipe_id=item_in.origin_recipe_id,
        origin_recipe_revision=origin_recipe_revision,
        name=item_name,
        quantity=item_in.quantity,
        unit=unit,
        notes=item_in.notes,
        is_bought=False,
    )
    db.add(item)
    bump_shopping_revision(db, household_id)
    db.commit()
    db.refresh(item)

    stmt = (
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.id == item.id,
            ShoppingListItem.household_id == household_id,
        )
        .execution_options(populate_existing=True)
    )
    return db.scalar(stmt)


@router.get("/{item_id}", response_model=ShoppingListItemRead)
def get_shopping_item(
    item_id: int,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.household_id == household_id,
        )
        .execution_options(populate_existing=True)
    )
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
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.household_id == household_id,
        )
        .execution_options(populate_existing=True)
    )
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )

    update_data = item_in.model_dump(exclude_unset=True)
    if "product_id" in update_data and update_data["product_id"] is not None:
        product = db.scalar(
            select(Product).where(
                Product.id == update_data["product_id"],
                Product.household_id == household_id,
            ).execution_options(populate_existing=True)
        )
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product with ID {update_data['product_id']} not found",
            )

    if "ingredient_id" in update_data and update_data["ingredient_id"] is not None:
        ingredient = db.scalar(
            select(Ingredient).where(
                Ingredient.id == update_data["ingredient_id"],
                Ingredient.is_active.is_(True),
            ).execution_options(populate_existing=True)
        )
        if ingredient is None:
            raise HTTPException(status_code=422, detail="Ingredient is not active")

    if "origin_recipe_id" in update_data:
        if update_data["origin_recipe_id"] is None:
            update_data["origin_recipe_revision"] = None
        else:
            recipe = db.scalar(
                select(Recipe).where(
                    Recipe.id == update_data["origin_recipe_id"],
                    Recipe.household_id == household_id,
                    Recipe.is_active.is_(True),
                ).execution_options(populate_existing=True)
            )
            if recipe is None:
                raise HTTPException(status_code=404, detail="Origin recipe not found")
            update_data["origin_recipe_revision"] = recipe.revision
            # Explicitly changing the primary origin replaces a prior plan link.
            update_data["origin_plan_id"] = None
            update_data["origin_plan_revision"] = None

    changed = any(getattr(item, field) != value for field, value in update_data.items())
    for field, value in update_data.items():
        setattr(item, field, value)

    if changed:
        bump_shopping_revision(db, household_id)
    db.commit()
    db.refresh(item)
    return item


@router.post("/{item_id}/toggle", response_model=ShoppingListItemRead)
def toggle_item_bought_status(
    item_id: int,
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    stmt = (
        select(ShoppingListItem)
        .options(joinedload(ShoppingListItem.product))
        .where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.household_id == household_id,
        )
        .execution_options(populate_existing=True)
    )
    item = db.scalar(stmt)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )
    item.is_bought = not item.is_bought
    bump_shopping_revision(db, household_id)
    db.commit()
    db.refresh(item)
    return item


@router.post("/generate-from-low-stock", response_model=List[ShoppingListItemRead])
def generate_from_low_stock(
    req: AutoGenerateShoppingRequest = AutoGenerateShoppingRequest(),
    household_id: int = Depends(get_current_household_id_for_write),
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
        .where(
            InventoryBatch.household_id == household_id,
            InventoryBatch.remaining_quantity > 0,
        )
        .group_by(InventoryBatch.product_id)
        .subquery()
    )

    stmt = (
        select(
            Product,
            func.coalesce(stock_subq.c.total_stock, 0.0).label("stock"),
        )
        .outerjoin(stock_subq, Product.id == stock_subq.c.product_id)
        .where(Product.household_id == household_id)
        .execution_options(populate_existing=True)
    )

    results = db.execute(stmt).all()
    created_items: List[ShoppingListItem] = []

    for product, current_stock in results:
        if float(current_stock) <= req.threshold:
            # Check if active unbought item already exists for this product
            already_listed = db.scalar(
                select(ShoppingListItem).where(
                    ShoppingListItem.product_id == product.id,
                    ShoppingListItem.household_id == household_id,
                    ShoppingListItem.is_bought.is_(False),
                ).execution_options(populate_existing=True)
            )
            if not already_listed:
                new_item = ShoppingListItem(
                    household_id=household_id,
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
        bump_shopping_revision(db, household_id)
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
        .where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.id.in_(item_ids),
        )
    ).all()


@router.delete("/completed/clear", status_code=status.HTTP_200_OK)
def clear_completed_items(
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    items = db.scalars(
        select(ShoppingListItem).where(
            ShoppingListItem.household_id == household_id,
            ShoppingListItem.is_bought.is_(True),
        ).execution_options(populate_existing=True)
    ).all()
    count = len(items)
    for item in items:
        db.delete(item)
    if count:
        bump_shopping_revision(db, household_id)
    db.commit()
    return {"message": f"Successfully removed {count} completed item(s)"}


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shopping_item(
    item_id: int,
    household_id: int = Depends(get_current_household_id_for_write),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(ShoppingListItem).where(
            ShoppingListItem.id == item_id,
            ShoppingListItem.household_id == household_id,
        ).execution_options(populate_existing=True)
    )
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Shopping list item with ID {item_id} not found",
        )
    db.delete(item)
    bump_shopping_revision(db, household_id)
    db.commit()
    return None
