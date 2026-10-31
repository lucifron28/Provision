"""Privacy operations scoped to the authenticated member and household."""

from datetime import datetime, timezone
import secrets
from uuid import uuid4

from sqlalchemy import case, delete, distinct, exists, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, selectinload

from app.core.security import hash_password, verify_password
from app.models.batch import InventoryBatch
from app.models.event import InventoryEvent
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.location import StorageLocation
from app.models.privacy import ProcessingConsent
from app.models.product import Product
from app.models.session import GrocerySession
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.models.recipe import Recipe, SavedRecipe
from app.models.meal_plan import MealPlan, MealPlanRevision
from app.models.cooking import CookingSession, CookingIdempotency
from app.models.leftover import Leftover, LeftoverEvent
from app.schemas.batch import InventoryBatchWithDetails
from app.schemas.event import InventoryEventRead
from app.schemas.location import StorageLocationRead
from app.schemas.privacy import (
    AccountExport,
    AccountExportProfile,
    ConsentRead,
    HouseholdExport,
    PantryExport,
)
from app.schemas.product import ProductRead
from app.schemas.privacy import CONSENT_POLICY_VERSION
from app.schemas.session import GrocerySessionRead
from app.schemas.shopping import ShoppingListItemRead
from app.services.preferences import read_profile
from app.services.recipes import read_recipe, saved_read
from app.services.meal_plans import get_plan, plan_history
from app.services.leftovers import read_leftover
from app.services.cooking import list_cooking_sessions

CONSENT_PURPOSE = "deepseek_recipes_v1"
CONSENT_CONSTRAINT = "uq_processing_consent_scope"


class InvalidAccountPassword(Exception):
    """The member did not reauthenticate with the current password."""


class LastHouseholdOwnerConflict(Exception):
    """An owner cannot leave a shared household without another owner."""


class HouseholdMembershipChanged(Exception):
    """Membership changed while account deletion was acquiring its locks."""


def _consent_read(consent: ProcessingConsent | None) -> ConsentRead:
    from app.core.config import settings

    if consent is None:
        return ConsentRead(policy_version=CONSENT_POLICY_VERSION, provider_enabled=settings.DEEPSEEK_ENABLED)
    return ConsentRead(
        purpose=CONSENT_PURPOSE,
        policy_version=CONSENT_POLICY_VERSION,
        granted=(
            consent.granted
            and consent.policy_version == CONSENT_POLICY_VERSION
        ),
        updated_at=consent.updated_at,
        provider_enabled=settings.DEEPSEEK_ENABLED,
    )


def read_member_consent(
    db: Session,
    *,
    household_id: int,
    user_id: int,
) -> ConsentRead:
    consent = db.scalar(
        select(ProcessingConsent).where(
            ProcessingConsent.household_id == household_id,
            ProcessingConsent.user_id == user_id,
            ProcessingConsent.purpose == CONSENT_PURPOSE,
        )
    )
    return _consent_read(consent)


def set_member_consent(
    db: Session,
    *,
    household_id: int,
    user_id: int,
    policy_version: str,
    granted: bool,
) -> ConsentRead:
    if policy_version != CONSENT_POLICY_VERSION:
        raise ValueError("The current consent policy version is required.")

    # Household membership mutations take this same lock before changing membership.
    # Holding it through the upsert prevents a grant from racing with a member removal.
    locked_household_id = db.scalar(
        select(Household.id)
        .where(Household.id == household_id)
        .with_for_update()
    )
    if locked_household_id is None:
        db.rollback()
        raise LookupError("The household is unavailable.")

    membership_exists = db.scalar(
        select(HouseholdMembership.id).where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == user_id,
        )
    )
    if membership_exists is None:
        db.rollback()
        raise LookupError("The member is not authorized for this household.")

    statement = (
        pg_insert(ProcessingConsent)
        .values(
            household_id=household_id,
            user_id=user_id,
            purpose=CONSENT_PURPOSE,
            policy_version=policy_version,
            granted=granted,
        )
        .on_conflict_do_update(
            constraint=CONSENT_CONSTRAINT,
            set_={
                "policy_version": policy_version,
                "granted": granted,
                "updated_at": datetime.now(timezone.utc),
            },
        )
        .returning(ProcessingConsent.id)
    )
    consent_id = db.scalar(statement)
    db.commit()
    consent = db.get(ProcessingConsent, consent_id)
    return _consent_read(consent)


def all_active_household_members_consented(
    db: Session,
    *,
    household_id: int,
) -> bool:
    """Require current consent from every active household member."""
    current_grant_exists = exists(
        select(ProcessingConsent.id).where(
            ProcessingConsent.household_id == household_id,
            ProcessingConsent.user_id == HouseholdMembership.user_id,
            ProcessingConsent.purpose == CONSENT_PURPOSE,
            ProcessingConsent.policy_version == CONSENT_POLICY_VERSION,
            ProcessingConsent.granted.is_(True),
        )
    )
    active_count, granted_count = db.execute(
        select(
            func.count(distinct(HouseholdMembership.user_id)),
            func.count(
                distinct(
                    case(
                        (current_grant_exists, HouseholdMembership.user_id),
                        else_=None,
                    )
                )
            ),
        )
        .join(User, User.id == HouseholdMembership.user_id)
        .where(
            HouseholdMembership.household_id == household_id,
            User.is_active.is_(True),
        )
    ).one()
    return active_count > 0 and active_count == granted_count


def export_account_data(
    db: Session,
    *,
    user: User,
    household: Household,
) -> AccountExport:
    """Export the household selected by the request's authenticated membership context."""
    household_id = household.id
    products = db.scalars(
        select(Product)
        .where(Product.household_id == household_id)
        .order_by(Product.id)
    ).all()
    locations = db.scalars(
        select(StorageLocation)
        .where(StorageLocation.household_id == household_id)
        .order_by(StorageLocation.id)
    ).all()
    sessions = db.scalars(
        select(GrocerySession)
        .where(GrocerySession.household_id == household_id)
        .order_by(GrocerySession.id)
    ).all()
    batches = db.scalars(
        select(InventoryBatch)
        .options(
            selectinload(InventoryBatch.product),
            selectinload(InventoryBatch.storage_location),
        )
        .where(InventoryBatch.household_id == household_id)
        .order_by(InventoryBatch.id)
    ).all()
    events = db.scalars(
        select(InventoryEvent)
        .join(InventoryBatch, InventoryBatch.id == InventoryEvent.batch_id)
        .where(InventoryBatch.household_id == household_id)
        .order_by(InventoryEvent.id)
    ).all()
    shopping_items = db.scalars(
        select(ShoppingListItem)
        .options(selectinload(ShoppingListItem.product))
        .where(ShoppingListItem.household_id == household_id)
        .order_by(ShoppingListItem.id)
    ).all()

    own_profile = AccountExportProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_active=user.is_active,
        created_at=user.created_at,
    )
    own_consent = read_member_consent(
        db,
        household_id=household_id,
        user_id=user.id,
    )
    meal_plan_ids = db.scalars(select(MealPlan.id).where(MealPlan.household_id == household_id)
        .order_by(MealPlan.id)).all()
    return AccountExport(
        exported_at=datetime.now(timezone.utc),
        account=own_profile,
        household=HouseholdExport(id=household.id, name=household.name),
        consent=own_consent,
        food_profiles=[read_profile(db, household_id, user.id), read_profile(db, household_id, None)],
        recipes=[read_recipe(db, row) for row in db.scalars(select(Recipe).where(Recipe.household_id == household_id)
            .order_by(Recipe.id)).all()],
        saved_recipes=[saved_read(row) for row in db.scalars(select(SavedRecipe).where(
            SavedRecipe.household_id == household_id, SavedRecipe.member_user_id == user.id).order_by(SavedRecipe.recipe_id)).all()],
        meal_plans=[get_plan(db, household_id, plan_id) for plan_id in meal_plan_ids],
        meal_plan_history={plan_id: plan_history(db, household_id, plan_id) for plan_id in meal_plan_ids},
        leftovers=[read_leftover(db, row) for row in db.scalars(select(Leftover).where(
            Leftover.household_id == household_id).order_by(Leftover.id)).all()],
        cooking_sessions=list_cooking_sessions(db, household_id),
        pantry=PantryExport(
            products=[ProductRead.model_validate(row) for row in products],
            storage_locations=[StorageLocationRead.model_validate(row) for row in locations],
            grocery_sessions=[GrocerySessionRead.model_validate(row) for row in sessions],
            inventory_batches=[
                InventoryBatchWithDetails.model_validate(row) for row in batches
            ],
            inventory_events=[InventoryEventRead.model_validate(row) for row in events],
            shopping_list_items=[
                ShoppingListItemRead.model_validate(row) for row in shopping_items
            ],
        ),
    )


def _lock_households_and_memberships(
    db: Session,
    *,
    user_id: int,
) -> tuple[list[int], list[HouseholdMembership]]:
    initial_household_ids = sorted(
        set(
            db.scalars(
                select(HouseholdMembership.household_id)
                .where(HouseholdMembership.user_id == user_id)
                .distinct()
            ).all()
        )
    )
    locked_household_ids = []
    if initial_household_ids:
        locked_household_ids = db.scalars(
            select(Household.id)
            .where(Household.id.in_(initial_household_ids))
            .order_by(Household.id)
            .with_for_update()
        ).all()

    memberships = db.scalars(
        select(HouseholdMembership)
        .where(HouseholdMembership.user_id == user_id)
        .order_by(HouseholdMembership.household_id, HouseholdMembership.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    current_household_ids = {membership.household_id for membership in memberships}
    if not current_household_ids.issubset(set(locked_household_ids)):
        db.rollback()
        raise HouseholdMembershipChanged
    return list(locked_household_ids), memberships


def delete_account(
    db: Session,
    *,
    user_id: int,
    password: str,
) -> None:
    household_ids, memberships = _lock_households_and_memberships(db, user_id=user_id)
    user = db.scalar(
        select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if user is None or not user.is_active:
        db.rollback()
        raise InvalidAccountPassword
    if not verify_password(password, user.hashed_password):
        db.rollback()
        raise InvalidAccountPassword

    # A membership could have been added in a different household while this
    # transaction was locking the original memberships. Recheck after the user
    # row lock; the member-add path must take this same user lock before inserting.
    current_household_ids = set(
        db.scalars(
            select(HouseholdMembership.household_id)
            .where(HouseholdMembership.user_id == user_id)
            .distinct()
        ).all()
    )
    if not current_household_ids.issubset(set(household_ids)):
        db.rollback()
        raise HouseholdMembershipChanged

    if household_ids:
        household_memberships = db.execute(
            select(
                HouseholdMembership.household_id,
                HouseholdMembership.user_id,
                HouseholdMembership.role,
            ).where(HouseholdMembership.household_id.in_(household_ids))
        ).all()
        members_by_household: dict[int, list[tuple[int, str]]] = {}
        for household_id, member_id, role in household_memberships:
            members_by_household.setdefault(household_id, []).append((member_id, role))

        for membership in memberships:
            if membership.role != HouseholdRole.OWNER.value:
                continue
            household_members = members_by_household.get(membership.household_id, [])
            other_members = [
                (member_id, role)
                for member_id, role in household_members
                if member_id != user_id
            ]
            other_owners = [
                member_id
                for member_id, role in other_members
                if role == HouseholdRole.OWNER.value
            ]
            if other_members and not other_owners:
                db.rollback()
                raise LastHouseholdOwnerConflict

    try:
        db.execute(delete(ProcessingConsent).where(ProcessingConsent.user_id == user_id))
        for model, field in (
            (CookingSession, "actor_user_id"), (CookingIdempotency, "actor_user_id"),
            (Leftover, "created_by_user_id"), (LeftoverEvent, "actor_user_id"),
            (MealPlan, "created_by_user_id"), (MealPlanRevision, "created_by_user_id"),
        ):
            db.execute(update(model).where(getattr(model, field) == user_id).values({field: None}))
        for membership in memberships:
            db.delete(membership)

        user.email = f"deleted-{uuid4().hex}@invalid.local"
        user.display_name = None
        user.hashed_password = hash_password(secrets.token_urlsafe(48))
        user.is_active = False
        db.commit()
    except Exception:
        db.rollback()
        raise
