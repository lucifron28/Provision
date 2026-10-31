from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.dependencies import (
    get_current_household,
    get_current_membership,
    require_household_owner,
)
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.user import User
from app.schemas.household import (
    HouseholdContextRead,
    HouseholdMemberCreate,
    HouseholdMemberRead,
    HouseholdMemberUpdate,
    HouseholdMembershipRead,
)

router = APIRouter()


@router.get("/", response_model=list[HouseholdMembershipRead])
def list_my_households(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(HouseholdMembership, Household)
        .join(Household, Household.id == HouseholdMembership.household_id)
        .where(HouseholdMembership.user_id == current_user.id)
        .order_by(HouseholdMembership.is_default.desc(), Household.id)
    ).all()
    return [
        HouseholdMembershipRead(
            id=household.id,
            name=household.name,
            role=membership.role,
            is_default=membership.is_default,
        )
        for membership, household in rows
    ]


def _locked_household(db: Session, household_id: int) -> Household:
    household = db.scalar(
        select(Household)
        .where(Household.id == household_id)
        .order_by(Household.id)
        .with_for_update()
    )
    if household is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household is unavailable")
    return household


def _require_current_owner(
    db: Session, membership_id: int, household_id: int
) -> HouseholdMembership:
    membership = db.scalar(
        select(HouseholdMembership)
        .where(
            HouseholdMembership.id == membership_id,
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.role == HouseholdRole.OWNER.value,
        )
        .execution_options(populate_existing=True)
    )
    if membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household owner role required",
        )
    return membership


@router.get("/current", response_model=HouseholdContextRead)
def get_household_context(
    household: Household = Depends(get_current_household),
    membership: HouseholdMembership = Depends(get_current_membership),
):
    return HouseholdContextRead(id=household.id, name=household.name, role=membership.role)


@router.get("/current/members", response_model=list[HouseholdMemberRead])
def list_household_members(
    household: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(HouseholdMembership, User)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(HouseholdMembership.household_id == household.id)
        .order_by(HouseholdMembership.created_at, HouseholdMembership.user_id)
    ).all()
    return [
        HouseholdMemberRead(
            user_id=membership.user_id,
            email=user.email,
            display_name=user.display_name,
            role=membership.role,
            is_default=membership.is_default,
            created_at=membership.created_at,
        )
        for membership, user in rows
    ]


@router.post(
    "/current/members",
    response_model=HouseholdMemberRead,
    status_code=status.HTTP_201_CREATED,
)
def add_household_member(
    member_in: HouseholdMemberCreate,
    household: Household = Depends(get_current_household),
    actor_membership: HouseholdMembership = Depends(require_household_owner),
    db: Session = Depends(get_db),
):
    _locked_household(db, household.id)
    _require_current_owner(db, actor_membership.id, household.id)

    user = db.scalar(
        select(User)
        .where(User.id == member_in.user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    existing = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household.id,
            HouseholdMembership.user_id == user.id,
        )
    )
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User is already a member")

    has_default = db.scalar(
        select(HouseholdMembership.id)
        .where(
            HouseholdMembership.user_id == user.id,
            HouseholdMembership.is_default.is_(True),
        )
        .limit(1)
    ) is not None
    membership = HouseholdMembership(
        household_id=household.id,
        user_id=user.id,
        role=member_in.role,
        is_default=not has_default,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return HouseholdMemberRead(
        user_id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=membership.role,
        is_default=membership.is_default,
        created_at=membership.created_at,
    )


@router.patch("/current/members/{user_id}", response_model=HouseholdMemberRead)
def update_household_member_role(
    user_id: int,
    member_in: HouseholdMemberUpdate,
    household: Household = Depends(get_current_household),
    actor_membership: HouseholdMembership = Depends(require_household_owner),
    db: Session = Depends(get_db),
):
    _locked_household(db, household.id)
    actor = _require_current_owner(db, actor_membership.id, household.id)
    if actor.user_id == user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owners cannot change their own membership role",
        )

    target = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household.id,
            HouseholdMembership.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household member not found")

    if target.role == HouseholdRole.OWNER.value and member_in.role != HouseholdRole.OWNER.value:
        other_owner_count = db.scalar(
            select(func.count(HouseholdMembership.id)).where(
                HouseholdMembership.household_id == household.id,
                HouseholdMembership.role == HouseholdRole.OWNER.value,
                HouseholdMembership.user_id != user_id,
            )
        ) or 0
        if other_owner_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Promote another owner before demoting the last owner",
            )

    target.role = member_in.role
    db.commit()
    db.refresh(target)
    user = db.get(User, target.user_id)
    return HouseholdMemberRead(
        user_id=target.user_id,
        email=user.email,
        display_name=user.display_name,
        role=target.role,
        is_default=target.is_default,
        created_at=target.created_at,
    )


@router.delete("/current/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_household_member(
    user_id: int,
    household: Household = Depends(get_current_household),
    actor_membership: HouseholdMembership = Depends(get_current_membership),
    db: Session = Depends(get_db),
):
    _locked_household(db, household.id)
    actor = db.scalar(
        select(HouseholdMembership)
        .where(HouseholdMembership.id == actor_membership.id)
        .execution_options(populate_existing=True)
    )
    if actor is None or actor.household_id != household.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Household membership required")

    is_self_leave = actor.user_id == user_id
    if not is_self_leave and actor.role != HouseholdRole.OWNER.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household owner role required",
        )

    target = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.household_id == household.id,
            HouseholdMembership.user_id == user_id,
        )
    )
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Household member not found")

    if target.role == HouseholdRole.OWNER.value:
        other_owner_count = db.scalar(
            select(func.count(HouseholdMembership.id)).where(
                HouseholdMembership.household_id == household.id,
                HouseholdMembership.role == HouseholdRole.OWNER.value,
                HouseholdMembership.user_id != user_id,
            )
        ) or 0
        if other_owner_count == 0:
            other_member_count = db.scalar(
                select(func.count(HouseholdMembership.id)).where(
                    HouseholdMembership.household_id == household.id,
                    HouseholdMembership.user_id != user_id,
                )
            ) or 0
            if other_member_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Promote another owner before removing the last owner",
                )

    if target.is_default:
        replacement = db.scalar(
            select(HouseholdMembership)
            .where(
                HouseholdMembership.user_id == target.user_id,
                HouseholdMembership.household_id != household.id,
            )
            .order_by(HouseholdMembership.household_id)
            .limit(1)
        )
        target.is_default = False
        db.flush()
        if replacement is not None:
            replacement.is_default = True

    db.delete(target)
    db.commit()
    return None
