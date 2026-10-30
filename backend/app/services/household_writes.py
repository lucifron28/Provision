"""Shared household write serialization and revision helpers."""

from fastapi import HTTPException
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.user import User


_WRITE_LOCK_STATE_KEY = "household_write_lock_state"


def _check_actor(db: Session, household_id: int, actor_id: int) -> None:
    membership = db.scalar(
        select(HouseholdMembership)
        .where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    user = db.scalar(
        select(User)
        .where(User.id == actor_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Active account required")
    if membership is None:
        raise HTTPException(status_code=403, detail="Household membership is required")


def lock_household_write(
    db: Session,
    household_id: int,
    *,
    actor_id: int | None = None,
) -> Household:
    """Lock a household before writes and optionally recheck its actor membership."""
    transaction = db.get_transaction()
    lock_state = db.info.setdefault(_WRITE_LOCK_STATE_KEY, {})
    for locked_household_id, state in tuple(lock_state.items()):
        if state[0] is not transaction:
            del lock_state[locked_household_id]
    previous = lock_state.get(household_id)
    if transaction is not None and previous is not None and previous[0] is transaction:
        household = db.get(Household, household_id)
        if household is None:
            raise HTTPException(status_code=404, detail="Household not found")
        authorized_actors = previous[1]
        if actor_id is not None and actor_id not in authorized_actors:
            _check_actor(db, household_id, actor_id)
            authorized_actors.add(actor_id)
        return household

    identity_key = db.identity_key(Household, household_id)
    existing = db.identity_map.get(identity_key)
    staged_values = {}
    if existing is not None:
        state = inspect(existing)
        staged_values = {
            attribute.key: state.dict[attribute.key]
            for attribute in state.mapper.column_attrs
            if attribute.key in state.dict and state.attrs[attribute.key].history.has_changes()
        }

    household = db.scalar(
        select(Household)
        .where(Household.id == household_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if household is None:
        raise HTTPException(status_code=404, detail="Household not found")
    for field, value in staged_values.items():
        setattr(household, field, value)

    authorized_actors: set[int] = set()
    if actor_id is not None:
        _check_actor(db, household_id, actor_id)
        authorized_actors.add(actor_id)

    transaction = db.get_transaction()
    if transaction is not None:
        lock_state[household_id] = (transaction, authorized_actors)

    return household


def bump_inventory_revision(db: Session, household_id: int) -> int:
    """Increment the pantry/product interpretation revision without committing."""
    household = lock_household_write(db, household_id)
    household.inventory_revision += 1
    return household.inventory_revision


def bump_shopping_revision(db: Session, household_id: int) -> int:
    """Increment the shopping-list revision without committing."""
    household = lock_household_write(db, household_id)
    household.shopping_revision += 1
    return household.shopping_revision
