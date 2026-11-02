from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.preferences import FoodProfileInput, FoodProfileRead
from app.services.preferences import delete_profile, read_profile, write_profile

router = APIRouter()


@router.get("/me", response_model=FoodProfileRead)
def get_member(response: Response, household_id: int = Depends(get_current_household_id),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_profile(db, household_id, user.id)


@router.put("/me", response_model=FoodProfileRead)
def put_member(request: FoodProfileInput, response: Response,
               household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
               db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_profile(db, household_id, user.id, user.id, request)


@router.delete("/me", status_code=204)
def remove_member(expected_revision: int = Query(ge=1), household_id: int = Depends(get_current_household_id),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    delete_profile(db, household_id, user.id, user.id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.get("/household", response_model=FoodProfileRead)
def get_household(response: Response, household_id: int = Depends(get_current_household_id),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return read_profile(db, household_id, None)


@router.put("/household", response_model=FoodProfileRead)
def put_household(request: FoodProfileInput, response: Response,
                  household_id: int = Depends(get_current_household_id), user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return write_profile(db, household_id, user.id, None, request)


@router.delete("/household", status_code=204)
def remove_household(expected_revision: int = Query(ge=1), household_id: int = Depends(get_current_household_id),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    delete_profile(db, household_id, user.id, None, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})
