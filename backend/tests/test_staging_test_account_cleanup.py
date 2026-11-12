import uuid

from pydantic import SecretStr
from sqlalchemy import select

from app.core.config import settings
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


def _staging_test_user(db, email: str | None = None):
    suffix = uuid.uuid4().hex
    user = User(
        email=email or f"provision-e2e+{suffix}@example.com",
        hashed_password=hash_password("synthetic-test-password"),
        is_active=True,
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

    response = _delete_request(unauthed_client, user)

    assert response.status_code == 204
    assert db.get(User, user.id) is None
    assert db.get(Household, household.id) is None
    assert db.get(FoodPreference, profile.id) is None
    assert db.get(FoodAllergy, allergy.id) is None
    assert db.get(InventoryBatch, batch.id) is None
    assert db.get(InventoryEvent, event.id) is None
    assert db.get(ProcessingConsent, consent.id) is None
    assert db.get(HouseholdDeepSeekBudget, household.id) is None
    assert db.scalar(select(Product).where(Product.household_id == other_household.id)).id == other_product.id
    assert db.get(User, other_user.id) is not None


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
