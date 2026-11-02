from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household_id, get_current_household_id_for_write
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.leftover import LeftoverEventType
from app.models.user import User
from app.schemas.leftover import (
    LeftoverCreate,
    LeftoverDispositionInput,
    LeftoverDispositionRead,
    LeftoverRead,
    LeftoverUpdate,
)
from app.services.leftovers import (
    archive_leftover,
    create_leftover,
    get_leftover_read,
    list_leftovers,
    record_leftover_event,
    update_leftover,
)


router = APIRouter()


@router.get("", response_model=list[LeftoverRead])
def leftovers(
    response: Response,
    include_archived: bool = False,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return list_leftovers(db, household_id, include_archived=include_archived)


@router.get("/{leftover_id}", response_model=LeftoverRead)
def leftover(
    leftover_id: int,
    response: Response,
    household_id: int = Depends(get_current_household_id),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return get_leftover_read(db, household_id, leftover_id)


@router.post("", response_model=LeftoverRead, status_code=201)
def create(
    request: LeftoverCreate,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return create_leftover(db, household_id, user.id, request)


@router.patch("/{leftover_id}", response_model=LeftoverRead)
def update(
    leftover_id: int,
    request: LeftoverUpdate,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return update_leftover(db, household_id, user.id, leftover_id, request)


@router.delete("/{leftover_id}", status_code=204)
def archive(
    leftover_id: int,
    expected_revision: int = Query(ge=1),
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    archive_leftover(db, household_id, user.id, leftover_id, expected_revision)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/{leftover_id}/consume", response_model=LeftoverDispositionRead)
def consume(
    leftover_id: int,
    request: LeftoverDispositionInput,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return record_leftover_event(
        db, household_id, user.id, leftover_id, LeftoverEventType.CONSUMED, request
    )


@router.post("/{leftover_id}/discard", response_model=LeftoverDispositionRead)
def discard(
    leftover_id: int,
    request: LeftoverDispositionInput,
    response: Response,
    household_id: int = Depends(get_current_household_id_for_write),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    response.headers["Cache-Control"] = "no-store"
    return record_leftover_event(
        db, household_id, user.id, leftover_id, LeftoverEventType.DISCARDED, request
    )
