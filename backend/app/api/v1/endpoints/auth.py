import hmac
import re

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi import Header, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from sqlalchemy import and_, delete, exists, select
from sqlalchemy.exc import IntegrityError

from app.core.database import get_db
from app.core.config import settings
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.user import User
from app.models.base import Base
from app.models.privacy import ProcessingConsent
from app.schemas.auth import UserCreate, UserRead, LoginRequest, TokenResponse

router = APIRouter()
http_bearer = HTTPBearer(auto_error=False)


def _household_scope_filter(table, household_id: int, visited: frozenset[str] = frozenset()):
    """Return a SQL filter for rows owned by a household, including child tables."""
    if "household_id" in table.c:
        return table.c.household_id == household_id
    if table.name in visited:
        return None

    next_visited = visited | {table.name}
    filters = []
    for foreign_key in table.foreign_keys:
        parent = foreign_key.column.table
        parent_filter = _household_scope_filter(parent, household_id, next_visited)
        if parent_filter is not None:
            filters.append(
                table.c[foreign_key.parent.name].in_(
                    select(foreign_key.column).where(parent_filter)
                )
            )
    if not filters:
        return None
    return filters[0] if len(filters) == 1 else and_(*filters)


def get_current_user(
    auth: HTTPAuthorizationCredentials | None = Depends(http_bearer),
    db: Session = Depends(get_db),
) -> User:
    """
    Dependency that authenticates incoming requests via Authorization: Bearer <token>.
    Validates token signature and expiration, ensuring account exists and is active.
    """
    if not auth or not auth.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    payload = decode_access_token(auth.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    email = payload["sub"]
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("uid") != str(user.id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


def _user_read(db: Session, user: User) -> UserRead:
    membership = db.scalar(
        select(HouseholdMembership)
        .where(
            HouseholdMembership.user_id == user.id,
            HouseholdMembership.is_default.is_(True),
        )
    )
    household = db.get(Household, membership.household_id) if membership else None
    return UserRead(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
        default_household_id=household.id if household else None,
        default_household_name=household.name if household else None,
    )


@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register_user(
    user_in: UserCreate,
    db: Session = Depends(get_db),
):
    """
    Register a new user account with normalized email and Argon2-hashed password.
    Rejects duplicate email addresses.
    """
    normalized_email = user_in.email.strip().lower()
    
    existing = db.scalar(select(User).where(User.email == normalized_email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered",
        )
    
    user = User(
        email=normalized_email,
        hashed_password=hash_password(user_in.password),
        display_name=user_in.display_name.strip() if user_in.display_name else None,
        is_active=True,
    )
    db.add(user)
    db.flush()

    household = Household(name="Home", slug=f"user-{user.id}")
    db.add(household)
    db.flush()
    db.add(
        HouseholdMembership(
            household_id=household.id,
            user_id=user.id,
            role=HouseholdRole.OWNER.value,
            is_default=True,
        )
    )
    db.commit()
    db.refresh(user)
    return _user_read(db, user)


@router.post("/login", response_model=TokenResponse)
def login_user(
    login_in: LoginRequest,
    db: Session = Depends(get_db),
):
    """
    Authenticate user credentials and return a signed JWT access token.
    Returns a generic 401 error upon any authentication failure.
    """
    normalized_email = login_in.email.strip().lower()
    user = db.scalar(select(User).where(User.email == normalized_email))
    
    # Check existence and password
    if not user or not user.is_active or not verify_password(login_in.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = create_access_token(subject=user.email, user_id=user.id)
    return TokenResponse(access_token=access_token, token_type="bearer")


@router.delete("/staging-test-account", status_code=status.HTTP_204_NO_CONTENT)
def delete_staging_test_account(
    response: Response,
    fixture_token: str | None = Header(default=None, alias="X-Staging-Test-Token"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    """Remove only one run-owned synthetic staging account and its household data."""
    expected_token = settings.STAGING_TEST_FIXTURE_TOKEN
    if (
        settings.DEPLOYMENT_ENVIRONMENT != "staging"
        or not settings.STAGING_TEST_FIXTURES_ENABLED
        or expected_token is None
    ):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")
    if fixture_token is None or not hmac.compare_digest(
        fixture_token, expected_token.get_secret_value()
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authorized")
    if re.fullmatch(r"provision-e2e\+[0-9a-f]{32}@example\.com", current_user.email) is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not a staging test account")

    memberships = db.scalars(
        select(HouseholdMembership).where(HouseholdMembership.user_id == current_user.id)
    ).all()
    if len(memberships) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test account scope changed")
    membership = memberships[0]
    household = db.get(Household, membership.household_id)
    if (
        household is None
        or not membership.is_default
        or membership.role != HouseholdRole.OWNER.value
        or household.name != "Home"
        or household.slug != f"user-{current_user.id}"
    ):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test account scope changed")
    household_member_ids = db.scalars(
        select(HouseholdMembership.user_id).where(HouseholdMembership.household_id == household.id)
    ).all()
    if household_member_ids != [current_user.id]:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test household has another member")

    # A run-owned synthetic household may contain consent and data created by
    # the smoke. Refuse cleanup if its records refer to a different user.
    consent_rows = db.execute(
        select(
            ProcessingConsent.user_id,
        ).where(ProcessingConsent.household_id == household.id)
    ).all()
    if any(row.user_id != current_user.id for row in consent_rows):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test household scope changed")

    # Refuse to alter rows that reference the synthetic user outside its own
    # household (for example, a review on shared catalogue data).
    for table in Base.metadata.tables.values():
        for column in table.c:
            if any(foreign_key.column.table.name == "users" for foreign_key in column.foreign_keys):
                predicate = column == current_user.id
                if "household_id" in table.c:
                    predicate = predicate & (table.c.household_id != household.id)
                elif table.name not in {"household_memberships", "processing_consents"}:
                    has_rows = db.scalar(select(exists().where(predicate)))
                    if has_rows:
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail="Test account has related data outside its household",
                        )
                    continue
                else:
                    continue
                has_rows = db.scalar(select(exists().where(predicate)))
                if has_rows:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Test account has related data outside its household",
                    )

    try:
        for table in reversed(Base.metadata.sorted_tables):
            predicate = _household_scope_filter(table, household.id)
            if predicate is not None:
                db.execute(delete(table).where(predicate))
        db.delete(household)
        db.delete(current_user)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Test account has related data") from None

    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserRead)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the authenticated user's profile details.
    """
    return _user_read(db, current_user)
