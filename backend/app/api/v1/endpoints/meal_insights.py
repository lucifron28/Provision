from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.meal_insights import MealBudgetRead, MealBudgetRequest, WastePeriodRead, WastePeriodRequest
from app.services.meal_insights import recipe_budget, waste_for_period

router = APIRouter()


@router.post("/recipes/{recipe_id}/budget", response_model=MealBudgetRead)
def budget(recipe_id: int, request: MealBudgetRequest, response: Response,
           household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
           db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return recipe_budget(db, household_id, user.id, recipe_id, request)


@router.post("/waste", response_model=WastePeriodRead)
def waste(request: WastePeriodRequest, response: Response, household_id: int = Depends(get_current_household_id),
          db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return waste_for_period(db, household_id, request)
