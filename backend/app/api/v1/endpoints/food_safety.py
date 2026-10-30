from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.core.database import get_db
from app.schemas.food_safety import FoodSafetyRead, FoodSafetyRequest
from app.services.allergen_policy import evaluate_food_safety
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.product_label import ProductLabelInput, ProductLabelRead
from app.services.product_labels import read_label, write_label, revoke_label

router = APIRouter()


@router.post("/evaluate", response_model=FoodSafetyRead)
def evaluate(request: FoodSafetyRequest, response: Response,
             household_id: int = Depends(get_current_household_id), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return evaluate_food_safety(db, household_id, request)


@router.get("/products/{product_id}/label", response_model=ProductLabelRead)
def get_label(product_id: int, response: Response, household_id: int = Depends(get_current_household_id),
              db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_label(db, household_id, product_id)


@router.put("/products/{product_id}/label", response_model=ProductLabelRead)
def put_label(product_id: int, request: ProductLabelInput, response: Response,
              household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_label(db, household_id, product_id, user.id, request)


@router.delete("/products/{product_id}/label", status_code=204)
def delete_label(product_id: int, expected_revision: int = Query(ge=1),
                 household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                 db: Session = Depends(get_db)):
    revoke_label(db, household_id, product_id, user.id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
