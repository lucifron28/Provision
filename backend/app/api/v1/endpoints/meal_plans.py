"""Household weekly plan CRUD and revision history."""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.meal_plan import MealPlanRead, MealPlanReplaceRequest, MealPlanRevisionRead
from app.services.meal_plans import (
    archive_plan,
    get_plan,
    list_plans,
    plan_history,
    replace_week,
)


router = APIRouter()


@router.get("/", response_model=list[MealPlanRead])
def list_weekly_plans(
    response: Response,
    from_week: date | None = Query(default=None),
    to_week: date | None = Query(default=None),
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return list_plans(db, household_id, from_week=from_week, to_week=to_week)


@router.get("/{plan_id}", response_model=MealPlanRead)
def read_weekly_plan(
    plan_id: int,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return get_plan(db, household_id, plan_id)


@router.get("/{plan_id}/history", response_model=list[MealPlanRevisionRead])
def read_weekly_plan_history(
    plan_id: int,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return plan_history(db, household_id, plan_id)


@router.put("/weeks/{week_start}", response_model=MealPlanRead)
def replace_weekly_plan(
    week_start: date,
    request: MealPlanReplaceRequest,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return replace_week(db, household_id, user.id, week_start, request)


@router.delete("/{plan_id}", status_code=204)
def archive_weekly_plan(
    plan_id: int,
    response: Response,
    expected_revision: int = Query(ge=1),
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    archive_plan(db, household_id, user.id, plan_id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
