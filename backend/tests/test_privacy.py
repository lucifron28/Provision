import re

from sqlalchemy import func, select

from app.core.security import create_access_token, hash_password
from app.models.batch import InventoryBatch
from app.models.event import EventType, InventoryEvent
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.location import StorageLocation
from app.models.privacy import ProcessingConsent
from app.models.product import Product
from app.models.session import GrocerySession
from app.models.shopping import ShoppingListItem
from app.models.user import User
from app.schemas.privacy import CONSENT_POLICY_VERSION
from app.services.privacy import all_active_household_members_consented


def _new_user(db, email: str, *, active: bool = True) -> User:
    user = User(
        email=email,
        hashed_password=hash_password("account-password-123"),
        display_name=email.split("@", maxsplit=1)[0],
        is_active=active,
    )
    db.add(user)
    db.flush()
    return user


def _new_household(db, slug: str, name: str = "Shared Home") -> Household:
    household = Household(name=name, slug=slug)
    db.add(household)
    db.flush()
    return household


def _add_member(
    db,
    user: User,
    household: Household,
    role: HouseholdRole,
    *,
    is_default: bool = False,
) -> HouseholdMembership:
    membership = HouseholdMembership(
        user_id=user.id,
        household_id=household.id,
        role=role.value,
        is_default=is_default,
    )
    db.add(membership)
    db.flush()
    return membership


def _headers(user: User) -> dict[str, str]:
    token = create_access_token(subject=user.email, user_id=user.id)
    return {"Authorization": f"Bearer {token}"}


def _consent(db, user: User, household: Household, *, granted: bool = True) -> ProcessingConsent:
    consent = ProcessingConsent(
        household_id=household.id,
        user_id=user.id,
        purpose="deepseek_recipes_v1",
        policy_version=CONSENT_POLICY_VERSION,
        granted=granted,
    )
    db.add(consent)
    db.flush()
    return consent


def test_consent_defaults_false_grants_explicitly_and_revokes(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    headers = _headers(auth_user)

    default = unauthed_client.get("/api/v1/privacy/consent", headers=headers)
    assert default.status_code == 200
    assert default.json()["granted"] is False
    assert default.json()["policy_version"] == CONSENT_POLICY_VERSION
    assert default.json()["provider_enabled"] is False
    assert default.headers["cache-control"] == "no-store"

    bad_confirmation = unauthed_client.post(
        "/api/v1/privacy/account-deletion",
        headers=headers,
        json={"confirmation": "DELETE", "password": "password123"},
    )
    assert bad_confirmation.status_code == 422

    grant = unauthed_client.put(
        "/api/v1/privacy/consent",
        headers=headers,
        json={"policy_version": CONSENT_POLICY_VERSION, "granted": True},
    )
    assert grant.status_code == 200
    assert grant.json()["granted"] is True
    assert grant.json()["provider_enabled"] is False

    unsupported = unauthed_client.put(
        "/api/v1/privacy/consent",
        headers=headers,
        json={"policy_version": "future-policy", "granted": True},
    )
    assert unsupported.status_code == 422

    revoke = unauthed_client.delete("/api/v1/privacy/consent", headers=headers)
    assert revoke.status_code == 204
    saved = db.scalar(
        select(ProcessingConsent).where(
            ProcessingConsent.user_id == auth_user.id,
            ProcessingConsent.household_id == household.id,
        )
    )
    assert saved is not None
    assert saved.granted is False
    assert saved.policy_version == CONSENT_POLICY_VERSION


def test_provider_consent_gate_requires_every_active_current_grant(
    db, auth_user, auth_household
):
    household = auth_household
    other = _new_user(db, "another-member@provision.local")
    inactive = _new_user(db, "inactive-member@provision.local", active=False)
    _add_member(db, other, household, HouseholdRole.MEMBER)
    _add_member(db, inactive, household, HouseholdRole.MEMBER)
    _consent(db, auth_user, household)
    db.commit()

    assert all_active_household_members_consented(db, household_id=household.id) is False

    _consent(db, other, household)
    db.commit()
    assert all_active_household_members_consented(db, household_id=household.id) is True

    old_policy = db.scalar(
        select(ProcessingConsent).where(
            ProcessingConsent.user_id == other.id,
            ProcessingConsent.household_id == household.id,
        )
    )
    old_policy.policy_version = "older-policy"
    db.commit()
    assert all_active_household_members_consented(db, household_id=household.id) is False


def test_household_header_cannot_select_another_members_household(
    unauthed_client, db, auth_user, auth_household
):
    own_household = auth_household
    other_household = _new_household(db, "other-house")
    stranger = _new_user(db, "stranger@provision.local")
    _add_member(db, stranger, other_household, HouseholdRole.OWNER, is_default=True)
    db.commit()

    response = unauthed_client.get(
        "/api/v1/privacy/consent",
        headers={**_headers(auth_user), "X-Household-ID": str(other_household.id)},
    )
    assert response.status_code == 403


def test_export_is_household_scoped_and_omits_other_profiles_and_secrets(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    household.name = "Export Home"
    other_household = _new_household(db, "unrelated-house", "Private Home")
    other_member = _new_user(db, "private.person@provision.local")
    _add_member(db, other_member, household, HouseholdRole.MEMBER)
    _add_member(db, other_member, other_household, HouseholdRole.OWNER, is_default=True)
    _consent(db, auth_user, household, granted=False)
    _consent(db, other_member, household, granted=True)

    product = Product(household_id=household.id, name="Shared oats")
    unrelated_product = Product(household_id=other_household.id, name="Private apples")
    location = StorageLocation(household_id=household.id, name="Pantry")
    session = GrocerySession(
        household_id=household.id,
        store_name="Local market",
        notes="Shared receipt note",
        idempotency_key="private-idempotency-key",
        idempotency_fingerprint="private-fingerprint",
    )
    db.add_all([product, unrelated_product, location, session])
    db.flush()
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        storage_location_id=location.id,
        grocery_session_id=session.id,
        original_quantity=2,
        remaining_quantity=1,
    )
    db.add(batch)
    db.flush()
    db.add(
        InventoryEvent(
            batch_id=batch.id,
            event_type=EventType.PURCHASED,
            quantity=2,
            reason="intake",
        )
    )
    db.add(
        ShoppingListItem(
            household_id=household.id,
            product_id=product.id,
            name="Shared oats",
            quantity=1,
        )
    )
    db.commit()

    response = unauthed_client.get("/api/v1/privacy/export", headers=_headers(auth_user))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    payload = response.json()
    serialized = response.text
    assert payload["account"]["email"] == auth_user.email
    assert payload["account"]["is_active"] is True
    assert payload["household"] == {"id": household.id, "name": "Export Home"}
    assert payload["consent"]["granted"] is False
    assert [row["name"] for row in payload["pantry"]["products"]] == ["Shared oats"]
    assert payload["pantry"]["inventory_events"][0]["batch_id"] == batch.id
    assert "private.person@provision.local" not in serialized
    assert "private.person" not in serialized
    assert "Private apples" not in serialized
    assert "Private Home" not in serialized
    assert "hashed_password" not in serialized
    assert "password" not in payload["account"]
    assert "idempotency_key" not in serialized
    assert "idempotency_fingerprint" not in serialized
    assert _headers(auth_user)["Authorization"].removeprefix("Bearer ") not in serialized


def test_wrong_password_leaves_account_memberships_and_consent_unchanged(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    consent = _consent(db, auth_user, household)
    db.commit()
    original_hash = auth_user.hashed_password

    response = unauthed_client.post(
        "/api/v1/privacy/account-deletion",
        headers=_headers(auth_user),
        json={"confirmation": "DELETE MY ACCOUNT", "password": "wrong-password"},
    )
    assert response.status_code == 401

    db.refresh(auth_user)
    assert auth_user.email == "testuser@provision.local"
    assert auth_user.display_name == "Test User"
    assert auth_user.is_active is True
    assert auth_user.hashed_password == original_hash
    assert db.scalar(
        select(func.count(HouseholdMembership.id)).where(
            HouseholdMembership.user_id == auth_user.id
        )
    ) == 1
    saved_consent = db.scalar(select(ProcessingConsent).where(ProcessingConsent.id == consent.id))
    assert saved_consent is not None and saved_consent.granted is True


def test_member_deletion_preserves_shared_household_and_pantry(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    auth_membership = db.scalar(
        select(HouseholdMembership).where(
            HouseholdMembership.user_id == auth_user.id,
            HouseholdMembership.household_id == household.id,
        )
    )
    auth_membership.role = HouseholdRole.MEMBER.value
    owner = _new_user(db, "remaining-owner@provision.local")
    _add_member(db, owner, household, HouseholdRole.OWNER, is_default=True)
    additional_household = _new_household(db, "additional-delete-house")
    _add_member(db, auth_user, additional_household, HouseholdRole.OWNER)
    consent = _consent(db, auth_user, household)
    consent_id = consent.id
    product = Product(household_id=household.id, name="Retained beans")
    db.add(product)
    db.flush()
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=3,
        remaining_quantity=2,
    )
    db.add(batch)
    db.flush()
    event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.PURCHASED,
        quantity=3,
        reason="audit retained",
    )
    db.add(event)
    db.commit()

    response = unauthed_client.post(
        "/api/v1/privacy/account-deletion",
        headers=_headers(auth_user),
        json={"confirmation": "DELETE MY ACCOUNT", "password": "password123"},
    )
    assert response.status_code == 204

    db.refresh(auth_user)
    assert auth_user.is_active is False
    assert auth_user.display_name is None
    assert re.fullmatch(r"deleted-[0-9a-f]{32}@invalid\.local", auth_user.email)
    assert db.scalar(
        select(func.count(HouseholdMembership.id)).where(
            HouseholdMembership.user_id == auth_user.id
        )
    ) == 0
    assert db.get(ProcessingConsent, consent_id) is None
    assert db.get(Household, household.id) is not None
    assert db.get(Household, additional_household.id) is not None
    assert db.get(Product, product.id).name == "Retained beans"
    assert db.get(InventoryEvent, event.id).reason == "audit retained"
    assert db.scalar(
        select(func.count(HouseholdMembership.id)).where(
            HouseholdMembership.user_id == owner.id,
            HouseholdMembership.household_id == household.id,
        )
    ) == 1


def test_last_owner_conflict_rolls_back_every_account_change(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    member = _new_user(db, "shared-member@provision.local")
    _add_member(db, member, household, HouseholdRole.MEMBER, is_default=True)
    consent = _consent(db, auth_user, household)
    db.commit()
    original_hash = auth_user.hashed_password

    response = unauthed_client.post(
        "/api/v1/privacy/account-deletion",
        headers=_headers(auth_user),
        json={"confirmation": "DELETE MY ACCOUNT", "password": "password123"},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "LAST_HOUSEHOLD_OWNER"

    db.refresh(auth_user)
    assert auth_user.email == "testuser@provision.local"
    assert auth_user.display_name == "Test User"
    assert auth_user.is_active is True
    assert auth_user.hashed_password == original_hash
    assert db.scalar(
        select(func.count(HouseholdMembership.id)).where(
            HouseholdMembership.household_id == household.id
        )
    ) == 2
    saved_consent = db.get(ProcessingConsent, consent.id)
    assert saved_consent is not None and saved_consent.granted is True


def test_last_member_can_leave_and_old_token_cannot_access_reregistered_email(
    unauthed_client, db, auth_user, auth_household
):
    household = auth_household
    product = Product(household_id=household.id, name="Orphaned pantry item")
    db.add(product)
    db.flush()
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=1,
        remaining_quantity=0,
    )
    db.add(batch)
    db.flush()
    audit_event = InventoryEvent(
        batch_id=batch.id,
        event_type=EventType.CONSUMED,
        quantity=1,
        reason="history retained after last member leaves",
    )
    db.add(audit_event)
    db.commit()
    old_id = auth_user.id
    old_email = auth_user.email
    old_headers = _headers(auth_user)

    deleted = unauthed_client.post(
        "/api/v1/privacy/account-deletion",
        headers=old_headers,
        json={"confirmation": "DELETE MY ACCOUNT", "password": "password123"},
    )
    assert deleted.status_code == 204
    assert db.get(Household, household.id) is not None
    assert db.scalar(
        select(func.count(HouseholdMembership.id)).where(
            HouseholdMembership.household_id == household.id
        )
    ) == 0
    assert db.get(InventoryEvent, audit_event.id).reason == "history retained after last member leaves"

    registered = unauthed_client.post(
        "/api/v1/auth/register",
        json={"email": old_email, "password": "replacement-password-456"},
    )
    assert registered.status_code == 201
    assert registered.json()["id"] != old_id

    stale_token = unauthed_client.get("/api/v1/auth/me", headers=old_headers)
    assert stale_token.status_code == 401
    stale_privacy_request = unauthed_client.get(
        "/api/v1/privacy/consent", headers=old_headers
    )
    assert stale_privacy_request.status_code == 401
