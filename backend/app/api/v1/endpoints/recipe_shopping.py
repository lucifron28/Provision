from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.recipe_shopping import (
    RecipeShoppingConfirmRead,
    RecipeShoppingConfirmRequest,
    RecipeShoppingPreviewRead,
    RecipeShoppingPreviewRequest,
)
from app.services.recipe_shopping import confirm_recipe_shopping, preview_recipe_shopping


router = APIRouter()


@router.post("/preview", response_model=RecipeShoppingPreviewRead)
def preview(
    request: RecipeShoppingPreviewRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return preview_recipe_shopping(db, household_id, user.id, request)


@router.post("/confirm", response_model=RecipeShoppingConfirmRead)
def confirm(
    request: RecipeShoppingConfirmRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return confirm_recipe_shopping(db, household_id, user.id, request)
