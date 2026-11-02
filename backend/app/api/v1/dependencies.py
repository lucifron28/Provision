from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.user import User
from app.services.household_writes import lock_household_write


def get_current_membership(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_household_id: int | None = Header(default=None, alias="X-Household-ID"),
) -> HouseholdMembership:
    stmt = (
        select(HouseholdMembership)
        .options(joinedload(HouseholdMembership.household))
        .where(HouseholdMembership.user_id == current_user.id)
    )
    if x_household_id is None:
        stmt = stmt.where(HouseholdMembership.is_default.is_(True))
    else:
        stmt = stmt.where(HouseholdMembership.household_id == x_household_id)

    membership = db.scalar(stmt)
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No authorized household membership",
        )
    return membership


def get_current_household(
    membership: HouseholdMembership = Depends(get_current_membership),
) -> Household:
    return membership.household


def get_current_household_id(
    household: Household = Depends(get_current_household),
) -> int:
    return household.id


def get_current_household_id_for_write(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_household_id: int | None = Header(default=None, alias="X-Household-ID"),
) -> int:
    if x_household_id is None:
        household_id = db.scalar(
            select(Household.id)
            .join(
                HouseholdMembership,
                HouseholdMembership.household_id == Household.id,
            )
            .where(
                HouseholdMembership.user_id == current_user.id,
                HouseholdMembership.is_default.is_(True),
            )
            .with_for_update(of=Household)
        )
    else:
        household_id = db.scalar(
            select(Household.id)
            .join(
                HouseholdMembership,
                HouseholdMembership.household_id == Household.id,
            )
            .where(Household.id == x_household_id)
            .where(HouseholdMembership.user_id == current_user.id)
            .with_for_update(of=Household)
        )

    if household_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No authorized household membership",
        )

    lock_household_write(db, household_id, actor_id=current_user.id)
    return household_id


def require_household_owner(
    membership: HouseholdMembership = Depends(get_current_membership),
) -> HouseholdMembership:
    if membership.role != HouseholdRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household owner role required",
        )
    return membership
