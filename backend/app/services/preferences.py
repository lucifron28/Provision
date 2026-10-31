"""Profile privacy, revision checks and membership serialization."""

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.household import Household, HouseholdMembership
from app.models.ingredient import Ingredient
from app.models.preferences import FoodAllergy, FoodPreference
from app.schemas.preferences import FoodAllergyInput, FoodPreferencesInput, FoodProfileInput, FoodProfileRead


def _profile(db: Session, household_id: int, member_user_id: int | None):
    return db.scalar(select(FoodPreference).where(
        FoodPreference.household_id == household_id,
        FoodPreference.member_user_id == member_user_id,
    ).execution_options(populate_existing=True))


def read_profile(db: Session, household_id: int, member_user_id: int | None) -> FoodProfileRead:
    profile = _profile(db, household_id, member_user_id)
    scope = "household" if member_user_id is None else "member"
    if profile is None:
        return FoodProfileRead(scope=scope)
    allergies = db.scalars(select(FoodAllergy).where(FoodAllergy.profile_id == profile.id)
        .order_by(FoodAllergy.id)).all()
    return FoodProfileRead(scope=scope, revision=profile.revision, preferences=profile.preferences,
        allergy_status=profile.allergy_status, allergies=[FoodAllergyInput(**{
            field: getattr(item, field) for field in FoodAllergyInput.model_fields
        }) for item in allergies])


def _lock_writer(db: Session, household_id: int, actor_id: int, member_user_id: int | None):
    if member_user_id is not None and member_user_id != actor_id:
        raise HTTPException(403, "Only your own member profile can be changed")
    db.scalar(select(Household.id).where(Household.id == household_id).with_for_update())
    member = db.scalar(select(HouseholdMembership).where(
        HouseholdMembership.household_id == household_id, HouseholdMembership.user_id == actor_id
    ).execution_options(populate_existing=True))
    if member is None or (member_user_id is None and member.role != "OWNER"):
        raise HTTPException(403, "Authorized membership and household owner permission are required")


def write_profile(db: Session, household_id: int, actor_id: int, member_user_id: int | None,
                  request: FoodProfileInput) -> FoodProfileRead:
    _lock_writer(db, household_id, actor_id, member_user_id)
    current = _profile(db, household_id, member_user_id)
    if request.expected_revision != (current.revision if current else None):
        raise HTTPException(409, "FOOD_PROFILE_REVISION_CONFLICT")
    exclusions = set(request.preferences.ingredient_exclusions)
    available = set(db.scalars(select(Ingredient.id).where(
        Ingredient.id.in_(exclusions), Ingredient.is_active.is_(True))).all())
    if available != exclusions:
        raise HTTPException(422, "Ingredient exclusion references an unavailable ingredient")
    if current is None:
        current = FoodPreference(household_id=household_id, member_user_id=member_user_id,
            revision=1, preferences={}, allergy_status=request.allergy_status)
        db.add(current)
        db.flush()
    else:
        current.revision += 1
        db.execute(delete(FoodAllergy).where(FoodAllergy.profile_id == current.id))
    current.preferences = request.preferences.model_dump(mode="json")
    current.allergy_status = request.allergy_status
    for declaration in request.allergies:
        db.add(FoodAllergy(profile_id=current.id, **declaration.model_dump()))
    db.commit()
    return read_profile(db, household_id, member_user_id)


def delete_profile(db: Session, household_id: int, actor_id: int, member_user_id: int | None,
                   expected_revision: int):
    _lock_writer(db, household_id, actor_id, member_user_id)
    profile = _profile(db, household_id, member_user_id)
    if profile is None or profile.revision != expected_revision:
        raise HTTPException(409, "FOOD_PROFILE_REVISION_CONFLICT")
    db.execute(delete(FoodAllergy).where(FoodAllergy.profile_id == profile.id))
    profile.preferences = FoodPreferencesInput().model_dump(mode="json")
    profile.allergy_status = "NOT_PROVIDED"
    # Retain only scope and revision so an old update cannot overwrite a reset.
    profile.revision += 1
    db.commit()
