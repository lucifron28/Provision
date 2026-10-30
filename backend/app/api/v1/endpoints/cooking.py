from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.cooking import (
    CookingConfirmRead,
    CookingConfirmRequest,
    CookingPreviewRead,
    CookingPreviewRequest,
    CookingSessionRead,
)
from app.services.cooking import (
    confirm_cooking,
    get_cooking_session_read,
    list_cooking_sessions,
    preview_cooking,
)


router = APIRouter()


@router.post("/preview", response_model=CookingPreviewRead)
def preview(
    request: CookingPreviewRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return preview_cooking(db, household_id, user.id, request)


@router.post("/confirm", response_model=CookingConfirmRead)
def confirm(
    request: CookingConfirmRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return confirm_cooking(db, household_id, user.id, request)


@router.get("/sessions", response_model=list[CookingSessionRead])
def sessions(
    response: Response,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return list_cooking_sessions(db, household_id)


@router.get("/sessions/{cooking_session_id}", response_model=CookingSessionRead)
def session(
    cooking_session_id: int,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return get_cooking_session_read(db, household_id, cooking_session_id)
