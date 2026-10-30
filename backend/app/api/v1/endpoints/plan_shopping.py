"""Explicit preview and confirmation for household plan shopping."""

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.plan_shopping import (
    PlanShoppingConfirmRead,
    PlanShoppingConfirmRequest,
    PlanShoppingPreviewRead,
    PlanShoppingPreviewRequest,
)
from app.services.plan_shopping import confirm_plan_shopping, preview_plan_shopping


router = APIRouter()


@router.post("/preview", response_model=PlanShoppingPreviewRead)
def preview(
    request: PlanShoppingPreviewRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return preview_plan_shopping(db, household_id, user.id, request)


@router.post("/confirm", response_model=PlanShoppingConfirmRead)
def confirm(
    request: PlanShoppingConfirmRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return confirm_plan_shopping(db, household_id, user.id, request)
