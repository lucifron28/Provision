from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.core.database import get_db
from app.schemas.food_safety import FoodSafetyRead, FoodSafetyRequest
from app.services.allergen_policy import evaluate_food_safety

router = APIRouter()


@router.post("/evaluate", response_model=FoodSafetyRead)
def evaluate(request: FoodSafetyRequest, response: Response,
             household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return evaluate_food_safety(db, household_id, request)
