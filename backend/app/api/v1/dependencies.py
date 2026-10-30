from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.user import User


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


def require_household_owner(
    membership: HouseholdMembership = Depends(get_current_membership),
) -> HouseholdMembership:
    if membership.role != HouseholdRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household owner role required",
        )
    return membership
