from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.v1.dependencies import get_current_household
from app.api.v1.endpoints.auth import get_current_user
from app.core.database import get_db
from app.models.household import Household
from app.models.user import User
from app.schemas.privacy import (
    CONSENT_POLICY_VERSION,
    AccountDeletion,
    AccountExport,
    ConsentRead,
    ConsentUpdate,
)
from app.services.privacy import (
    HouseholdMembershipChanged,
    InvalidAccountPassword,
    LastHouseholdOwnerConflict,
    delete_account,
    export_account_data,
    read_member_consent,
    set_member_consent,
)

router = APIRouter()


@router.get("/consent", response_model=ConsentRead)
def get_consent(
    response: Response,
    current_user: User = Depends(get_current_user),
    household: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
) -> ConsentRead:
    response.headers["Cache-Control"] = "no-store"
    return read_member_consent(
        db,
        household_id=household.id,
        user_id=current_user.id,
    )


@router.put("/consent", response_model=ConsentRead)
def update_consent(
    consent: ConsentUpdate,
    response: Response,
    current_user: User = Depends(get_current_user),
    household: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
) -> ConsentRead:
    response.headers["Cache-Control"] = "no-store"
    try:
        return set_member_consent(
            db,
            household_id=household.id,
            user_id=current_user.id,
            policy_version=consent.policy_version,
            granted=consent.granted,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household membership is required",
        ) from exc


@router.delete("/consent", status_code=status.HTTP_204_NO_CONTENT)
def revoke_consent(
    current_user: User = Depends(get_current_user),
    household: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
) -> Response:
    try:
        set_member_consent(
            db,
            household_id=household.id,
            user_id=current_user.id,
            policy_version=CONSENT_POLICY_VERSION,
            granted=False,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Household membership is required",
        ) from exc
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/export", response_model=AccountExport)
def export_account(
    response: Response,
    current_user: User = Depends(get_current_user),
    household: Household = Depends(get_current_household),
    db: Session = Depends(get_db),
) -> AccountExport:
    response.headers["Cache-Control"] = "no-store"
    return export_account_data(db, user=current_user, household=household)


@router.post("/account-deletion", status_code=status.HTTP_204_NO_CONTENT)
def request_account_deletion(
    request: AccountDeletion,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    response.headers["Cache-Control"] = "no-store"
    try:
        delete_account(
            db,
            user_id=current_user.id,
            password=request.password,
        )
    except InvalidAccountPassword as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Current password is incorrect",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except LastHouseholdOwnerConflict as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="LAST_HOUSEHOLD_OWNER",
        ) from exc
    except HouseholdMembershipChanged as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Household membership changed; retry account deletion",
        ) from exc
    return Response(
        status_code=status.HTTP_204_NO_CONTENT,
        headers={"Cache-Control": "no-store"},
    )
