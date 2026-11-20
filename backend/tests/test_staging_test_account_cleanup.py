from datetime import datetime, timedelta, timezone
import uuid

from pydantic import SecretStr
from sqlalchemy import select, update

from app.core.config import settings
from app.core.staging_fixtures import is_staging_test_account
from app.core.security import create_access_token, hash_password
from app.models.batch import InventoryBatch
from app.models.deepseek_budget import HouseholdDeepSeekBudget
from app.models.event import EventType, InventoryEvent
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.privacy import ProcessingConsent
from app.models.preferences import FoodAllergy, FoodPreference
from app.models.product import Product
from app.models.user import User


FIXTURE_TOKEN = "staging-fixture-token-for-tests"


def _enable_staging_cleanup(monkeypatch):
    monkeypatch.setattr(settings, "DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURES_ENABLED", True)
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURE_TOKEN", SecretStr(FIXTURE_TOKEN))


def test_staging_fixture_identifiers_accept_legacy_and_run_owned_patterns():
    assert is_staging_test_account(f"provision-e2e+{'a' * 32}@example.com")
    assert is_staging_test_account(f"provision-e2e+43450000000-2-{'b' * 32}@example.com")
    assert not is_staging_test_account(f"provision-e2e+43450000000-2-{'b' * 31}@example.com")
    assert not is_staging_test_account("person@example.com")


def _staging_test_user(db, email: str | None = None, *, age_minutes: int = 0):
    suffix = uuid.uuid4().hex
    user = User(
        email=email or f"provision-e2e+{suffix}@example.com",
        hashed_password=hash_password("synthetic-test-password"),
        is_active=True,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=age_minutes),
    )
    db.add(user)
    db.flush()
    household = Household(name="Home", slug=f"user-{user.id}")
    db.add(household)
    db.flush()
    membership = HouseholdMembership(
        household_id=household.id,
        user_id=user.id,
        role=HouseholdRole.OWNER.value,
        is_default=True,
    )
    db.add(membership)
    db.commit()
    return user, household


def _delete_request(client, user: User, *, fixture_token: str = FIXTURE_TOKEN):
    jwt = create_access_token(subject=user.email, user_id=user.id)
    return client.delete(
        "/api/v1/auth/staging-test-account",
        headers={
            "Authorization": f"Bearer {jwt}",
            "X-Staging-Test-Token": fixture_token,
        },
    )


def test_staging_cleanup_is_hidden_when_disabled(unauthed_client, db, monkeypatch):
    user, _ = _staging_test_user(db)
    monkeypatch.setattr(settings, "DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURES_ENABLED", False)

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 404
    assert db.get(User, user.id) is not None


def test_staging_cleanup_rejects_wrong_token_and_non_fixture_accounts(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    fixture_user, _ = _staging_test_user(db)
    response = _delete_request(unauthed_client, fixture_user, fixture_token="wrong-token")
    assert response.status_code == 401
    assert db.get(User, fixture_user.id) is not None

    ordinary_user, _ = _staging_test_user(db, email="ordinary@example.com")
    response = _delete_request(unauthed_client, ordinary_user)
    assert response.status_code == 403
    assert db.get(User, ordinary_user.id) is not None


def test_staging_cleanup_deletes_only_an_empty_synthetic_household(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    user, household = _staging_test_user(db)
    consent = ProcessingConsent(
        household_id=household.id,
        user_id=user.id,
        purpose="deepseek_recipes_v1",
        policy_version="test-policy",
        granted=False,
    )
    db.add(consent)
    db.add(HouseholdDeepSeekBudget(household_id=household.id, used=1))
    db.commit()

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 204
    assert db.get(User, user.id) is None
    assert db.get(Household, household.id) is None


def test_staging_cleanup_removes_only_the_run_owned_household_graph(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    user, household = _staging_test_user(db)
    other_user, other_household = _staging_test_user(db)

    profile = FoodPreference(
        household_id=household.id,
        member_user_id=user.id,
        revision=1,
        preferences={},
        allergy_status="DECLARED",
    )
    other_product = Product(name="Other household item", household_id=other_household.id)
    product = Product(name="Synthetic item", household_id=household.id)
    db.add_all([profile, other_product, product])
    db.flush()
    allergy = FoodAllergy(profile_id=profile.id, allergen_code="egg")
    batch = InventoryBatch(
        household_id=household.id,
        product_id=product.id,
        original_quantity=5,
        remaining_quantity=5,
    )
    consent = ProcessingConsent(
        household_id=household.id,
        user_id=user.id,
        purpose="deepseek_recipes_v1",
        policy_version="test-policy",
        granted=True,
    )
    budget = HouseholdDeepSeekBudget(household_id=household.id, used=1)
    db.add_all([allergy, batch, consent, budget])
    db.flush()
    event = InventoryEvent(batch_id=batch.id, event_type=EventType.PURCHASED, quantity=5)
    db.add(event)
    db.commit()
    user_id = user.id
    household_id = household.id
    other_household_id = other_household.id
    other_user_id = other_user.id
    profile_id = profile.id
    allergy_id = allergy.id
    batch_id = batch.id
    event_id = event.id
    consent_id = consent.id
    other_product_id = other_product.id

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 204
    assert db.get(User, user_id) is None
    assert db.get(Household, household_id) is None
    assert db.get(FoodPreference, profile_id) is None
    assert db.get(FoodAllergy, allergy_id) is None
    assert db.get(InventoryBatch, batch_id) is None
    assert db.get(InventoryEvent, event_id) is None
    assert db.get(ProcessingConsent, consent_id) is None
    assert db.get(HouseholdDeepSeekBudget, household_id) is None
    assert db.scalar(select(Product).where(Product.household_id == other_household_id)).id == other_product_id
    assert db.get(User, other_user_id) is not None


def test_staging_cleanup_refuses_a_household_with_another_member(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    user, household = _staging_test_user(db)
    other_user, _ = _staging_test_user(db)
    product = Product(name="Shared household item", household_id=household.id)
    db.add_all(
        [
            HouseholdMembership(
                household_id=household.id,
                user_id=other_user.id,
                role=HouseholdRole.MEMBER.value,
                is_default=False,
            ),
            product,
        ]
    )
    db.commit()

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 409
    assert db.get(User, user.id) is not None
    assert db.get(User, other_user.id) is not None
    assert db.get(Household, household.id) is not None
    assert db.scalar(select(Product).where(Product.household_id == household.id)).id == product.id


def test_staging_cleanup_refuses_user_references_in_another_household(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    user, household = _staging_test_user(db)
    _, other_household = _staging_test_user(db)
    consent = ProcessingConsent(
        household_id=other_household.id,
        user_id=user.id,
        purpose="deepseek_recipes_v1",
        policy_version="test-policy",
        granted=False,
    )
    db.add(consent)
    db.commit()

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 409
    assert db.get(User, user.id) is not None
    assert db.get(Household, household.id) is not None
    assert db.get(Household, other_household.id) is not None
    assert db.get(ProcessingConsent, consent.id) is not None


def test_token_only_stale_cleanup_removes_only_expired_exact_scope_fixtures(
    unauthed_client, db, monkeypatch
):
    _enable_staging_cleanup(monkeypatch)
    monkeypatch.setattr(settings, "STAGING_TEST_CHAT_MOCK_ENABLED", True)
    stale_user, stale_household = _staging_test_user(db, age_minutes=60)
    safe_stale_user, safe_stale_household = _staging_test_user(db, age_minutes=0)
    recent_user, recent_household = _staging_test_user(db, age_minutes=2)
    other_user, _ = _staging_test_user(db, email="household-member@example.com")
    db.execute(
        update(User)
        .where(User.id == stale_user.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=60))
    )
    db.execute(
        update(User)
        .where(User.id == recent_user.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=2))
    )
    db.execute(
        update(User)
        .where(User.id == safe_stale_user.id)
        .values(created_at=datetime.now(timezone.utc) - timedelta(minutes=60))
    )
    db.add(HouseholdMembership(
        household_id=stale_household.id,
        user_id=other_user.id,
        role=HouseholdRole.MEMBER.value,
        is_default=False,
    ))
    db.commit()
    stale_id = stale_user.id
    safe_stale_id = safe_stale_user.id
    recent_id = recent_user.id
    other_user_id = other_user.id
    recent_household_id = recent_household.id
    stale_household_id = stale_household.id
    safe_stale_household_id = safe_stale_household.id

    response = unauthed_client.post(
        "/api/v1/auth/staging-test-accounts/cleanup-stale",
        headers={"X-Staging-Test-Token": FIXTURE_TOKEN},
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "deleted_count": 1,
        "skipped_count": 1,
        "skipped_user_ids": [stale_id],
    }
    assert db.get(User, safe_stale_id) is None
    assert db.get(Household, safe_stale_household_id) is None
    assert db.get(User, stale_id) is not None
    assert db.get(Household, stale_household_id) is not None
    assert db.get(User, recent_id) is not None
    assert db.get(Household, recent_household_id) is not None
    assert db.get(User, other_user_id) is not None


def test_token_only_stale_cleanup_remains_hidden_and_rejects_wrong_token(
    unauthed_client, db, monkeypatch
):
    stale_user, _ = _staging_test_user(db, age_minutes=60)
    monkeypatch.setattr(settings, "DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURES_ENABLED", False)
    disabled = unauthed_client.post("/api/v1/auth/staging-test-accounts/cleanup-stale")
    assert disabled.status_code == 404
    assert db.get(User, stale_user.id) is not None

    _enable_staging_cleanup(monkeypatch)
    unauthorized = unauthed_client.post(
        "/api/v1/auth/staging-test-accounts/cleanup-stale",
        headers={"X-Staging-Test-Token": "wrong-token"},
    )
    assert unauthorized.status_code == 401
    assert db.get(User, stale_user.id) is not None
