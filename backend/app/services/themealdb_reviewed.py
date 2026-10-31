"""Source-checked TheMealDB lookup. Returned data is untrusted and unsaved."""

import re
from dataclasses import dataclass
from typing import ContextManager, Protocol

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.services.deepseek_discovery import (
    _require_member_and_consent,
    _same_fetch_authorization,
    authorize_recipe_fetch,
)
from app.services.household_writes import lock_household_write
from app.services.themealdb import MealDBClient, MealDBError, MealDBRateLimited


class MealDBBudget(Protocol):
    def request(self) -> ContextManager[None]: ...


@dataclass(frozen=True)
class ReviewedMeal:
    data: dict
    api_source_id: int
    original_source_id: int
    untrusted_content: bool = True


def lookup_reviewed_meal(
    db: Session, household_id: int, actor_id: int, meal_id: str, *,
    client: MealDBClient, budget: MealDBBudget, allow_broader_web: bool = False,
) -> ReviewedMeal | None:
    """Check both sources before releasing content to a future caller.

    The caller must supply a shared, durable API budget. This function neither
    validates recipe safety nor permits an inventory or shopping-list write.
    """
    if not isinstance(meal_id, str) or not re.fullmatch(r"[0-9]{1,12}", meal_id):
        raise HTTPException(422, "INVALID_MEAL_ID")
    _require_member_and_consent(db, household_id, actor_id)
    lock_household_write(db, household_id, actor_id=actor_id)
    _require_member_and_consent(db, household_id, actor_id)
    api_url = f"https://www.themealdb.com/api/json/v1/1/lookup.php?i={meal_id}"
    api = authorize_recipe_fetch(db, api_url, allow_broader_web=allow_broader_web)
    if "api_json" not in api.extraction_methods:
        raise HTTPException(403, "RECIPE_FETCH_METHOD_NOT_AUTHORIZED")
    try:
        with budget.request():
            if not _same_fetch_authorization(db, api, allow_broader_web=allow_broader_web):
                raise HTTPException(403, "RECIPE_FETCH_NOT_AUTHORIZED")
            _require_member_and_consent(db, household_id, actor_id)
            meal = client.lookup(meal_id)
    except MealDBRateLimited:
        raise HTTPException(429, "MEALDB_RATE_LIMITED") from None
    except MealDBError:
        raise HTTPException(502, "MEALDB_UNAVAILABLE") from None
    if not _same_fetch_authorization(db, api, allow_broader_web=allow_broader_web):
        raise HTTPException(403, "RECIPE_FETCH_NOT_AUTHORIZED")
    _require_member_and_consent(db, household_id, actor_id)
    if meal is None:
        return None
    source_url = meal.get("strSource")
    if not isinstance(source_url, str) or not source_url:
        raise HTTPException(403, "MEAL_SOURCE_UNVERIFIED")
    try:
        original = authorize_recipe_fetch(db, source_url, allow_broader_web=allow_broader_web)
    except HTTPException:
        raise HTTPException(403, "MEAL_SOURCE_UNVERIFIED") from None
    if "full_text" not in original.extraction_methods:
        raise HTTPException(403, "MEAL_SOURCE_UNVERIFIED")
    if not _same_fetch_authorization(db, original, allow_broader_web=allow_broader_web):
        raise HTTPException(403, "MEAL_SOURCE_UNVERIFIED")
    _require_member_and_consent(db, household_id, actor_id)
    return ReviewedMeal(meal, api.source_id, original.source_id)
