from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password
from app.models.household import Household, HouseholdMembership
from app.models.preferences import FoodAllergy, FoodPreference
from app.models.user import User
from app.schemas.preferences import FoodProfileInput
from app.services.preferences import write_profile


def headers(user):
    return {"Authorization": "Bearer " + create_access_token(subject=user.email, user_id=user.id)}


def new_member(db, household, *, email="member@example.test", role="MEMBER"):
    user = User(email=email, hashed_password=hash_password("member-password"), is_active=True)
    db.add(user)
    db.flush()
    db.add(HouseholdMembership(household_id=household.id, user_id=user.id, role=role, is_default=True))
    db.commit()
    return user


def test_profile_lifecycle_explicit_allergies_and_revision_reset(client, db):
    url = "/api/v1/food-profiles/me"
    initial = client.get(url)
    assert initial.headers["cache-control"] == "no-store"
    assert initial.json()["allergy_status"] == "NOT_PROVIDED"
    assert initial.json()["revision"] is None
    payload = dict(allergy_status="DECLARED", allergies=[dict(allergen_code="fish", notes="Private note")],
        preferences=dict(preferred_cuisines=["Filipino"], preferred_regions=["Bicol"], diet_patterns=["no_pork"],
            dislikes=["eggplant"], meal_budget_php="150.50", servings="2.5"))
    created = client.put(url, json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["revision"] == 1
    assert created.json()["preferences"]["meal_budget_php"] == "150.50"
    assert created.json()["allergies"][0]["allergen_code"] == "fish"
    assert client.put(url, json=payload).status_code == 409
    assert client.delete(url + "?expected_revision=2").status_code == 409
    assert client.delete(url + "?expected_revision=1").status_code == 204
    reset = client.get(url).json()
    assert reset["revision"] == 2 and reset["allergy_status"] == "NOT_PROVIDED"
    assert reset["allergies"] == [] and reset["preferences"]["dislikes"] == []
    assert db.scalar(select(func.count()).select_from(FoodAllergy)) == 0
    assert client.put(url, json={**payload, "expected_revision": 1}).status_code == 409
    assert client.put(url, json=dict(expected_revision=2, allergy_status="NONE_DECLARED")).status_code == 200


@pytest.mark.parametrize("payload", [
    {}, {"allergy_status": "NONE_DECLARED", "allergies": [{"allergen_code": "egg"}]},
    {"allergy_status": "DECLARED"}, {"allergy_status": "NOT_PROVIDED", "allergies": [{"allergen_code": "egg"}]},
    {"allergy_status": "DECLARED", "allergies": [{}]},
    {"allergy_status": "DECLARED", "allergies": [{"allergen_code": "unknown"}]},
    {"allergy_status": "DECLARED", "allergies": [{"custom_text": " "}]},
    {"allergy_status": "DECLARED", "allergies": [{"allergen_code": "milk", "custom_text": "whey"}]},
    {"allergy_status": "DECLARED", "allergies": [{"allergen_code": "egg"}, {"allergen_code": "egg"}]},
    {"allergy_status": "NONE_DECLARED", "household_id": 99},
    {"allergy_status": "NONE_DECLARED", "member_user_id": 99},
    {"allergy_status": "NONE_DECLARED", "preferences": {"servings": "NaN"}},
    {"allergy_status": "NONE_DECLARED", "preferences": {"meal_budget_php": "Infinity"}},
    {"allergy_status": "NONE_DECLARED", "preferences": {"preferred_cuisines": ["Filipino", "filipino"]}},
    {"allergy_status": "NONE_DECLARED", "preferences": {"diet_patterns": ["invented"]}},
    {"allergy_status": "NONE_DECLARED", "preferences": {"ingredient_exclusions": [999999]}},
])
def test_invalid_profiles_fail_without_writes(client, db, payload):
    response = client.put("/api/v1/food-profiles/me", json=payload)
    assert response.status_code == 422, response.text
    assert db.scalar(select(func.count()).select_from(FoodPreference)) == 0


def test_member_privacy_household_owner_permission_and_foreign_context(unauthed_client, db, auth_household, auth_user):
    member = new_member(db, auth_household)
    own, other = headers(auth_user), headers(member)
    url = "/api/v1/food-profiles"
    sensitive = dict(allergy_status="DECLARED", allergies=[dict(custom_text="My sensitivity", severity="severe", notes="private")])
    assert unauthed_client.put(url + "/me", headers=own, json=sensitive).status_code == 200
    assert unauthed_client.get(url + "/me", headers=other).json()["allergies"] == []
    assert unauthed_client.get(url + f"/members/{auth_user.id}", headers=other).status_code == 404
    assert unauthed_client.put(url + "/household", headers=other, json=sensitive).status_code == 403
    assert unauthed_client.put(url + "/household", headers=own, json=sensitive).status_code == 200
    assert unauthed_client.get(url + "/household", headers=other).json()["allergies"][0]["custom_text"] == "My sensitivity"
    assert unauthed_client.delete(url + "/household?expected_revision=1", headers=other).status_code == 403
    foreign = Household(name="Foreign", slug="foreign-profile")
    db.add(foreign)
    db.commit()
    assert unauthed_client.get(url + "/me", headers={**own, "X-Household-ID": str(foreign.id)}).status_code == 403
    assert unauthed_client.get(url + "/me").status_code == 401


def test_export_omits_other_members_profiles_and_deletion_removes_own(unauthed_client, db, auth_household, auth_user):
    member = new_member(db, auth_household)
    url = "/api/v1/food-profiles/me"
    for user, note in [(auth_user, "owner-private"), (member, "member-private")]:
        response = unauthed_client.put(url, headers=headers(user), json=dict(allergy_status="DECLARED",
            allergies=[dict(allergen_code="milk", notes=note)]))
        assert response.status_code == 200
    exported = unauthed_client.get("/api/v1/privacy/export", headers=headers(member))
    assert exported.status_code == 200
    assert "member-private" in exported.text and "owner-private" not in exported.text
    response = unauthed_client.post("/api/v1/privacy/account-deletion", headers=headers(member),
        json=dict(confirmation="DELETE MY ACCOUNT", password="member-password"))
    assert response.status_code == 204, response.text
    assert db.scalar(select(func.count()).select_from(FoodPreference).where(FoodPreference.member_user_id == member.id)) == 0
    assert db.scalar(select(func.count()).select_from(FoodAllergy)) == 1


def test_concurrent_profile_creation_only_accepts_one_writer(db, engine, auth_household, auth_user):
    household_id, user_id = auth_household.id, auth_user.id
    db.rollback()
    barrier = Barrier(2)

    def write(status):
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                return write_profile(independent, household_id, user_id, user_id,
                    FoodProfileInput(allergy_status=status)).revision
            except HTTPException as exc:
                independent.rollback()
                return exc.status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        result = list(workers.map(write, ["NONE_DECLARED", "NOT_PROVIDED"]))
    assert sorted(result) == [1, 409]
    assert db.scalar(select(func.count()).select_from(FoodPreference)) == 1
