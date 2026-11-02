from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select

from app.core.security import create_access_token
from app.models.household import Household
from app.models.cooking import CookingIdempotency, CookingSession
from app.models.leftover import Leftover, LeftoverEvent, LeftoverEventType
from app.models.meal_plan import MealPlan, MealPlanRevision
from app.schemas.leftover import LeftoverCreate, LeftoverDispositionInput
from app.schemas.meal_plan import MealPlanReplaceRequest
from app.schemas.recipe import RecipeWrite
from app.services.leftovers import create_leftover, record_leftover_event
from app.services.meal_plans import replace_week
from app.services.recipes import write_recipe


def test_export_scopes_shared_plans_and_leftovers_and_deletion_clears_authorship(
    unauthed_client, db, auth_household, auth_user
):
    plan = replace_week(db, auth_household.id, auth_user.id, date(2026, 10, 26), MealPlanReplaceRequest(entries=[]))
    leftover = create_leftover(db, auth_household.id, auth_user.id,
        LeftoverCreate(name="Shared own leftovers", quantity=3, unit="count"))
    record_leftover_event(db, auth_household.id, auth_user.id, leftover.id, LeftoverEventType.DISCARDED,
        LeftoverDispositionInput(expected_revision=1, quantity=1))
    recipe = write_recipe(db, auth_household.id, auth_user.id, RecipeWrite(
        title="Own recorded meal", servings=1, instructions=["Synthetic privacy fixture."],
        content_permission="OWNED_OR_PERMISSION_GRANTED",
        ingredients=[dict(display_name="garlic", amount=1, unit="g")]))
    cooking = CookingSession(household_id=auth_household.id, recipe_id=recipe.id,
        recipe_revision=recipe.revision, actor_user_id=auth_user.id, servings=1, inventory_revision=0)
    db.add(cooking)
    db.flush()
    retry = CookingIdempotency(household_id=auth_household.id, cooking_session_id=cooking.id,
        actor_user_id=auth_user.id, idempotency_key="privacy-cooking-retry", request_hash="a" * 64,
        response_snapshot={})
    db.add(retry)
    foreign = Household(name="Foreign planning", slug="foreign-planning-privacy")
    db.add(foreign)
    db.flush()
    db.add(Leftover(household_id=foreign.id, name="Other household secret leftovers", quantity=1,
        remaining_quantity=1, unit="count", prepared_at=datetime.now(timezone.utc), revision=1))
    db.commit()
    headers = {"Authorization": "Bearer " + create_access_token(subject=auth_user.email, user_id=auth_user.id)}
    exported = unauthed_client.get("/api/v1/privacy/export", headers=headers)
    assert exported.status_code == 200, exported.text
    assert [item["id"] for item in exported.json()["meal_plans"]] == [plan.id]
    assert len(exported.json()["meal_plan_history"][str(plan.id)]) == 1
    assert [item["id"] for item in exported.json()["cooking_sessions"]] == [cooking.id]
    assert "Shared own leftovers" in exported.text and "Other household secret leftovers" not in exported.text
    deleted = unauthed_client.post("/api/v1/privacy/account-deletion", headers=headers,
        json=dict(confirmation="DELETE MY ACCOUNT", password="password123"))
    assert deleted.status_code == 204, deleted.text
    db.expire_all()
    assert db.get(MealPlan, plan.id).created_by_user_id is None
    assert db.scalar(select(MealPlanRevision).where(MealPlanRevision.plan_id == plan.id)).created_by_user_id is None
    assert db.get(Leftover, leftover.id).created_by_user_id is None
    assert db.scalar(select(LeftoverEvent).where(LeftoverEvent.leftover_id == leftover.id)).actor_user_id is None
    assert db.get(Leftover, leftover.id).remaining_quantity == 2
    assert db.get(CookingSession, cooking.id).actor_user_id is None
    assert db.get(CookingIdempotency, retry.id).actor_user_id is None


def test_leftover_disposal_is_reported_as_unpriced_waste_and_consumption_is_excluded(
    unauthed_client, db, auth_household, auth_user
):
    start = datetime.now(timezone.utc)-timedelta(seconds=1)
    leftover = create_leftover(db, auth_household.id, auth_user.id,
        LeftoverCreate(name="Recorded rice", quantity=3, unit="portion"))
    record_leftover_event(db, auth_household.id, auth_user.id, leftover.id, LeftoverEventType.CONSUMED,
        LeftoverDispositionInput(expected_revision=1, quantity=1))
    record_leftover_event(db, auth_household.id, auth_user.id, leftover.id, LeftoverEventType.DISCARDED,
        LeftoverDispositionInput(expected_revision=2, quantity=1))
    headers = {"Authorization": "Bearer " + create_access_token(subject=auth_user.email, user_id=auth_user.id)}
    response = unauthed_client.post("/api/v1/meal-insights/waste", headers=headers,
        json=dict(start=start.isoformat(), end=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()))
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["event_count"] == 1 and result["leftover_event_count"] == 1
    assert result["inventory_event_count"] == 0 and result["unpriced_event_count"] == 1
    assert result["estimated_total_loss_php"] is None
    assert result["leftover_events"][0]["cost_unknown_reason"] == "leftover_cost_not_recorded"
