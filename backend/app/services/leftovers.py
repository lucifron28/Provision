from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.time import household_today
from app.models.cooking import CookingSession
from app.models.household import Household
from app.models.leftover import Leftover, LeftoverEvent, LeftoverEventType
from app.models.location import StorageLocation
from app.models.recipe import RecipeRevision
from app.schemas.leftover import (
    LeftoverCreate,
    LeftoverDispositionInput,
    LeftoverDispositionRead,
    LeftoverEventRead,
    LeftoverRead,
    LeftoverUpdate,
)
from app.services.household_writes import lock_household_write


@contextmanager
def _readonly_snapshot(bind):
    if not isinstance(bind, Engine) or bind.dialect.name != "postgresql":
        raise RuntimeError("Leftover reads require PostgreSQL")
    snapshot_bind = bind.execution_options(isolation_level="REPEATABLE READ")
    with Session(bind=snapshot_bind, autoflush=False, expire_on_commit=False) as snapshot:
        with snapshot.begin():
            snapshot.execute(text("SET TRANSACTION READ ONLY"))
            yield snapshot


def _is_expired(leftover: Leftover) -> bool:
    return leftover.use_by_date is not None and leftover.use_by_date < household_today()


def _event_read(event: LeftoverEvent) -> LeftoverEventRead:
    return LeftoverEventRead(
        id=event.id,
        event_type=LeftoverEventType(event.event_type),
        quantity=event.quantity,
        unit=event.unit,
        portions=event.portions,
        occurred_at=event.occurred_at,
        reason=event.reason,
    )


def read_leftover(db: Session, leftover: Leftover) -> LeftoverRead:
    rows = db.execute(
        select(Leftover, LeftoverEvent)
        .outerjoin(
            LeftoverEvent,
            (LeftoverEvent.household_id == Leftover.household_id)
            & (LeftoverEvent.leftover_id == Leftover.id),
        )
        .where(
            Leftover.household_id == leftover.household_id,
            Leftover.id == leftover.id,
        )
        .order_by(LeftoverEvent.occurred_at, LeftoverEvent.id)
        .execution_options(populate_existing=True)
    ).all()
    if not rows:
        raise HTTPException(status_code=404, detail="Leftover not found")
    leftover = rows[0][0]
    events = [event for _, event in rows if event is not None]
    return LeftoverRead(
        id=leftover.id,
        household_id=leftover.household_id,
        name=leftover.name,
        recipe_id=leftover.recipe_id,
        recipe_revision=leftover.recipe_revision,
        cooking_session_id=leftover.cooking_session_id,
        storage_location_id=leftover.storage_location_id,
        prepared_at=leftover.prepared_at,
        use_by_date=leftover.use_by_date,
        use_by_date_verified=leftover.use_by_date_verified,
        quantity=leftover.quantity,
        remaining_quantity=leftover.remaining_quantity,
        unit=leftover.unit,
        portions=leftover.portions,
        remaining_portions=leftover.remaining_portions,
        revision=leftover.revision,
        created_by_user_id=leftover.created_by_user_id,
        archived_at=leftover.archived_at,
        is_expired=_is_expired(leftover),
        events=[_event_read(event) for event in events],
    )


def _get_leftover(
    db: Session,
    household_id: int,
    leftover_id: int,
    *,
    lock: bool = False,
) -> Leftover:
    statement = select(Leftover).where(
        Leftover.household_id == household_id,
        Leftover.id == leftover_id,
    )
    if lock:
        statement = statement.with_for_update()
    leftover = db.scalar(statement.execution_options(populate_existing=True))
    if leftover is None:
        raise HTTPException(status_code=404, detail="Leftover not found")
    return leftover


def _validate_location(db: Session, household_id: int, location_id: int | None) -> None:
    if location_id is None:
        return
    exists = db.scalar(
        select(StorageLocation.id).where(
            StorageLocation.household_id == household_id,
            StorageLocation.id == location_id,
        )
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Storage location not found")


def _validate_recipe_revision(
    db: Session,
    household_id: int,
    recipe_id: int | None,
    recipe_revision: int | None,
) -> None:
    if recipe_id is None and recipe_revision is None:
        return
    if recipe_id is None or recipe_revision is None:
        raise HTTPException(status_code=422, detail="Recipe ID and revision must be provided together")
    exists = db.scalar(
        select(RecipeRevision.id).where(
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == recipe_id,
            RecipeRevision.revision == recipe_revision,
        )
    )
    if exists is None:
        raise HTTPException(status_code=404, detail="Recipe revision not found")


def create_leftover_no_commit(
    db: Session,
    household_id: int,
    actor_id: int,
    request: LeftoverCreate,
    *,
    cooking_session: CookingSession | None = None,
) -> Leftover:
    """Create a household leftover inside the caller's existing transaction."""
    _validate_location(db, household_id, request.storage_location_id)
    recipe_id = request.recipe_id
    recipe_revision = request.recipe_revision
    cooking_session_id = request.cooking_session_id

    if cooking_session is not None:
        if cooking_session.household_id != household_id:
            raise HTTPException(status_code=404, detail="Cooking session not found")
        if cooking_session_id not in (None, cooking_session.id):
            raise HTTPException(status_code=422, detail="Leftover cooking session does not match")
        if recipe_id not in (None, cooking_session.recipe_id) or recipe_revision not in (
            None,
            cooking_session.recipe_revision,
        ):
            raise HTTPException(status_code=422, detail="Leftover recipe does not match cooking session")
        recipe_id = cooking_session.recipe_id
        recipe_revision = cooking_session.recipe_revision
        cooking_session_id = cooking_session.id
    elif cooking_session_id is not None:
        linked_session = db.scalar(
            select(CookingSession).where(
                CookingSession.household_id == household_id,
                CookingSession.id == cooking_session_id,
            ).execution_options(populate_existing=True)
        )
        if linked_session is None:
            raise HTTPException(status_code=404, detail="Cooking session not found")
        if recipe_id not in (None, linked_session.recipe_id) or recipe_revision not in (
            None,
            linked_session.recipe_revision,
        ):
            raise HTTPException(status_code=422, detail="Leftover recipe does not match cooking session")
        recipe_id = linked_session.recipe_id
        recipe_revision = linked_session.recipe_revision

    _validate_recipe_revision(db, household_id, recipe_id, recipe_revision)
    now = datetime.now(timezone.utc)
    if request.prepared_at.astimezone(timezone.utc) > now:
        raise HTTPException(status_code=422, detail="prepared_at cannot be in the future")

    leftover = Leftover(
        household_id=household_id,
        name=request.name,
        recipe_id=recipe_id,
        recipe_revision=recipe_revision,
        cooking_session_id=cooking_session_id,
        storage_location_id=request.storage_location_id,
        prepared_at=request.prepared_at,
        use_by_date=request.use_by_date,
        use_by_date_verified=request.use_by_date_verified,
        quantity=request.quantity,
        remaining_quantity=request.quantity,
        unit=request.unit,
        portions=request.portions,
        remaining_portions=request.portions,
        revision=1,
        created_by_user_id=actor_id,
    )
    db.add(leftover)
    db.flush()
    return leftover


def create_leftover(
    db: Session,
    household_id: int,
    actor_id: int,
    request: LeftoverCreate,
) -> LeftoverRead:
    lock_household_write(db, household_id, actor_id=actor_id)
    try:
        leftover = create_leftover_no_commit(db, household_id, actor_id, request)
        db.commit()
        return get_leftover_read(db, household_id, leftover.id)
    except Exception:
        db.rollback()
        raise


def list_leftovers(
    db: Session,
    household_id: int,
    *,
    include_archived: bool = False,
) -> list[LeftoverRead]:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        statement = select(Leftover).where(Leftover.household_id == household_id)
        if not include_archived:
            statement = statement.where(Leftover.archived_at.is_(None))
        rows = snapshot.scalars(
            statement.order_by(Leftover.prepared_at.desc(), Leftover.id.desc())
            .execution_options(populate_existing=True)
        ).all()
        return [read_leftover(snapshot, row) for row in rows]


def get_leftover_read(db: Session, household_id: int, leftover_id: int) -> LeftoverRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        return read_leftover(snapshot, _get_leftover(snapshot, household_id, leftover_id))


def update_leftover(
    db: Session,
    household_id: int,
    actor_id: int,
    leftover_id: int,
    request: LeftoverUpdate,
) -> LeftoverRead:
    lock_household_write(db, household_id, actor_id=actor_id)
    try:
        leftover = _get_leftover(db, household_id, leftover_id, lock=True)
        if leftover.archived_at is not None:
            raise HTTPException(status_code=409, detail="LEFTOVER_ARCHIVED")
        if leftover.revision != request.expected_revision:
            raise HTTPException(status_code=409, detail="LEFTOVER_REVISION_CONFLICT")

        changed = request.model_fields_set - {"expected_revision"}
        if "name" in changed:
            if request.name is None:
                raise HTTPException(status_code=422, detail="Leftover name cannot be null")
            leftover.name = request.name
        if "storage_location_id" in changed:
            _validate_location(db, household_id, request.storage_location_id)
            leftover.storage_location_id = request.storage_location_id
        if "use_by_date" in changed:
            leftover.use_by_date = request.use_by_date
            leftover.use_by_date_verified = bool(request.use_by_date_verified)

        leftover.revision += 1
        db.commit()
        return get_leftover_read(db, household_id, leftover_id)
    except Exception:
        db.rollback()
        raise


def archive_leftover(
    db: Session,
    household_id: int,
    actor_id: int,
    leftover_id: int,
    expected_revision: int,
) -> None:
    lock_household_write(db, household_id, actor_id=actor_id)
    try:
        leftover = _get_leftover(db, household_id, leftover_id, lock=True)
        if leftover.revision != expected_revision:
            raise HTTPException(status_code=409, detail="LEFTOVER_REVISION_CONFLICT")
        if leftover.archived_at is not None:
            raise HTTPException(status_code=409, detail="LEFTOVER_ARCHIVED")
        leftover.archived_at = datetime.now(timezone.utc)
        leftover.revision += 1
        db.commit()
    except Exception:
        db.rollback()
        raise


def record_leftover_event(
    db: Session,
    household_id: int,
    actor_id: int,
    leftover_id: int,
    event_type: LeftoverEventType,
    request: LeftoverDispositionInput,
) -> LeftoverDispositionRead:
    lock_household_write(db, household_id, actor_id=actor_id)
    try:
        leftover = _get_leftover(db, household_id, leftover_id, lock=True)
        if leftover.revision != request.expected_revision:
            raise HTTPException(status_code=409, detail="LEFTOVER_REVISION_CONFLICT")
        if leftover.archived_at is not None:
            raise HTTPException(status_code=409, detail="LEFTOVER_ARCHIVED")
        if event_type == LeftoverEventType.CONSUMED and _is_expired(leftover):
            raise HTTPException(status_code=409, detail="LEFTOVER_EXPIRED")

        quantity = Decimal(str(request.quantity))
        remaining = Decimal(str(leftover.remaining_quantity))
        if quantity <= 0 or quantity > remaining:
            raise HTTPException(status_code=422, detail="LEFTOVER_QUANTITY_EXCEEDS_REMAINING")

        portion_delta: Decimal | None = None
        remaining_portions: Decimal | None = None
        if leftover.portions is None:
            if request.portions is not None:
                raise HTTPException(status_code=422, detail="LEFTOVER_HAS_NO_PORTION_COUNT")
        else:
            if request.portions is None:
                raise HTTPException(status_code=422, detail="PORTION_COUNT_REQUIRED")
            portion_delta = Decimal(str(request.portions))
            remaining_portions = Decimal(str(leftover.remaining_portions))
            if portion_delta <= 0 or portion_delta > remaining_portions:
                raise HTTPException(status_code=422, detail="LEFTOVER_PORTIONS_EXCEED_REMAINING")

        next_quantity = remaining - quantity
        next_portions = remaining_portions - portion_delta if remaining_portions is not None else None
        if next_portions is not None and (next_quantity == 0) != (next_portions == 0):
            raise HTTPException(
                status_code=422,
                detail="Quantity and remaining portions must reach zero together",
            )

        event = LeftoverEvent(
            household_id=household_id,
            leftover_id=leftover.id,
            cooking_session_id=leftover.cooking_session_id,
            actor_user_id=actor_id,
            event_type=event_type.value,
            quantity=quantity,
            unit=leftover.unit,
            portions=portion_delta,
            occurred_at=datetime.now(timezone.utc),
            reason=request.reason or event_type.value.title(),
        )
        leftover.remaining_quantity = next_quantity
        leftover.remaining_portions = next_portions
        leftover.revision += 1
        if next_quantity == 0:
            leftover.archived_at = event.occurred_at
        db.add(event)
        db.flush()
        event_read = _event_read(event)
        db.commit()
        return LeftoverDispositionRead(
            leftover=get_leftover_read(db, household_id, leftover_id),
            event=event_read,
        )
    except Exception:
        db.rollback()
        raise
