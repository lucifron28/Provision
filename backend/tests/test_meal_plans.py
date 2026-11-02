from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Barrier, Event

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.endpoints.auth import get_current_user
from app.api.v1.endpoints.meal_plans import router as meal_plans_router
from app.core.database import get_db
from app.models.household import Household, HouseholdMembership, HouseholdRole
from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanRevision
from app.models.user import User
from app.schemas.meal_plan import MealPlanReplaceRequest
from app.schemas.recipe import RecipeWrite
from app.services import meal_plans as meal_plan_service
from app.services.ingredient_matching import seed_ingredient_catalog_v1
from app.services.meal_plans import get_plan, replace_week
from app.services.recipes import write_recipe


WEEK_START = date(2026, 10, 26)


def recipe_request(
    ingredient_id: int,
    title: str,
    *,
    content_permission="OWNED_OR_PERMISSION_GRANTED",
    expected_revision=None,
) -> RecipeWrite:
    return RecipeWrite(
        title=title,
        cuisine="Filipino",
        ph_regions=["region_unknown"],
        content_permission=content_permission,
        servings=Decimal("1"),
        instructions=["Prepare the ingredients."],
        expected_revision=expected_revision,
        ingredients=[
            {"ingredient_id": ingredient_id, "amount": "3", "unit": "g"}
        ],
    )


def make_recipe(db, household, user, ingredient, title):
    return write_recipe(db, household.id, user.id, recipe_request(ingredient.id, title))


def setup_ingredient(db):
    seed_ingredient_catalog_v1(db)
    db.commit()
    from app.models.ingredient import Ingredient

    return db.scalar(select(Ingredient).where(Ingredient.normalized_name == "garlic"))


def local_client(db, user):
    app = FastAPI()
    app.include_router(meal_plans_router, prefix="/meal-plans")

    def override_db():
        try:
            yield db
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


def entry(recipe, *, meal_date=WEEK_START, slot="breakfast", position=0, servings="1"):
    return {
        "meal_date": meal_date.isoformat(),
        "slot": slot,
        "position": position,
        "recipe_id": recipe.id,
        "recipe_revision": recipe.revision,
        "servings": servings,
    }


def test_week_replacement_move_reset_and_archive_preserve_snapshots(
    db, auth_household, auth_user
):
    ingredient = setup_ingredient(db)
    garlic_rice = make_recipe(db, auth_household, auth_user, ingredient, "Garlic rice")
    garlic_soup = make_recipe(db, auth_household, auth_user, ingredient, "Garlic soup")

    with local_client(db, auth_user) as client:
        created = client.put(
            f"/meal-plans/weeks/{WEEK_START.isoformat()}",
            json={
                "expected_revision": None,
                "entries": [
                    entry(garlic_rice),
                    entry(garlic_soup, meal_date=date(2026, 10, 27), slot="dinner"),
                ],
            },
        )
        assert created.status_code == 200, created.text
        plan = created.json()
        assert plan["revision"] == 1
        assert len(plan["entries"]) == 2

        moved = client.put(
            f"/meal-plans/weeks/{WEEK_START.isoformat()}",
            json={
                "expected_revision": 1,
                "entries": [
                    entry(garlic_rice, meal_date=date(2026, 10, 28), slot="lunch"),
                ],
            },
        )
        assert moved.status_code == 200, moved.text
        assert moved.json()["revision"] == 2
        assert len(moved.json()["entries"]) == 1
        assert moved.json()["entries"][0]["meal_date"] == "2026-10-28"
        assert moved.json()["entries"][0]["recipe_revision"] == garlic_rice.revision

        reset = client.put(
            f"/meal-plans/weeks/{WEEK_START.isoformat()}",
            json={"expected_revision": 2, "entries": []},
        )
        assert reset.status_code == 200, reset.text
        assert reset.json()["revision"] == 3
        assert reset.json()["entries"] == []

        history = client.get(f"/meal-plans/{plan['id']}/history")
        assert history.status_code == 200, history.text
        assert [item["revision"] for item in history.json()] == [1, 2, 3]
        assert len(history.json()[0]["snapshot"]["entries"]) == 2
        assert history.json()[1]["snapshot"]["entries"][0]["meal_date"] == "2026-10-28"
        assert history.json()[2]["snapshot"]["entries"] == []

        archived = client.delete(
            f"/meal-plans/{plan['id']}", params={"expected_revision": 3}
        )
        assert archived.status_code == 204
        current = client.get(f"/meal-plans/{plan['id']}")
        assert current.json()["is_active"] is False
        assert current.json()["revision"] == 4

    assert db.scalar(select(func.count()).select_from(MealPlanRevision)) == 4


def test_stale_full_week_replacement_is_rejected(db, auth_household, auth_user):
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, "Garlic noodles")
    initial = replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_START,
        MealPlanReplaceRequest(expected_revision=None, entries=[]),
    )
    replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_START,
        MealPlanReplaceRequest(
            expected_revision=initial.revision,
            entries=[
                {
                    "meal_date": WEEK_START,
                    "slot": "breakfast",
                    "recipe_id": recipe.id,
                    "recipe_revision": recipe.revision,
                    "servings": "2",
                }
            ],
        ),
    )
    with pytest.raises(HTTPException) as stale:
        replace_week(
            db,
            auth_household.id,
            auth_user.id,
            WEEK_START,
            MealPlanReplaceRequest(expected_revision=1, entries=[]),
        )
    assert stale.value.status_code == 409
    assert stale.value.detail == "PLAN_REVISION_CONFLICT"


def test_plan_rejects_pinned_revision_after_current_permission_withdrawal(
    db, auth_household, auth_user
):
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, "Permission withdrawal")
    write_recipe(
        db,
        auth_household.id,
        auth_user.id,
        recipe_request(
            ingredient.id,
            "Permission withdrawn",
            content_permission="NOT_DECLARED",
            expected_revision=recipe.revision,
        ),
        recipe_id=recipe.id,
    )

    with pytest.raises(HTTPException) as denied:
        replace_week(
            db,
            auth_household.id,
            auth_user.id,
            WEEK_START,
            MealPlanReplaceRequest(
                expected_revision=None,
                entries=[entry(recipe)],
            ),
        )

    assert denied.value.status_code == 422
    assert denied.value.detail == "RECIPE_CONTENT_PERMISSION_REQUIRED"
    db.rollback()
    assert db.scalar(select(func.count()).select_from(MealPlan)) == 0


def test_concurrent_week_replacements_allow_only_one_revision_writer(
    db, engine, auth_household, auth_user
):
    ingredient = setup_ingredient(db)
    recipe = make_recipe(db, auth_household, auth_user, ingredient, "Garlic porridge")
    plan = replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_START,
        MealPlanReplaceRequest(expected_revision=None, entries=[]),
    )
    household_id, actor_id = auth_household.id, auth_user.id
    barrier = Barrier(2)
    db.rollback()

    def replace_on_independent_session(day):
        with Session(engine, autoflush=False, expire_on_commit=False) as independent:
            barrier.wait(timeout=8)
            request = MealPlanReplaceRequest(
                expected_revision=plan.revision,
                entries=[
                    {
                        "meal_date": day,
                        "slot": "breakfast",
                        "recipe_id": recipe.id,
                        "recipe_revision": recipe.revision,
                        "servings": "1",
                    }
                ],
            )
            try:
                result = replace_week(
                    independent, household_id, actor_id, WEEK_START, request
                )
                return ("ok", result.revision)
            except HTTPException as exc:
                independent.rollback()
                return ("http", exc.status_code)

    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(
            workers.map(
                replace_on_independent_session,
                [WEEK_START, date(2026, 10, 27)],
            )
        )
    assert sorted(results, key=str) == sorted([("ok", 2), ("http", 409)], key=str)
    db.expire_all()
    current = db.scalar(
        select(MealPlan).where(
            MealPlan.household_id == household_id,
            MealPlan.week_start == WEEK_START,
        )
    )
    assert current.revision == 2
    assert db.scalar(
        select(func.count()).select_from(MealPlanRevision).where(
            MealPlanRevision.plan_id == plan.id
        )
    ) == 2


def test_plan_read_keeps_revision_and_entries_from_one_repeatable_snapshot(
    db, engine, auth_household, auth_user, monkeypatch
):
    ingredient = setup_ingredient(db)
    first_recipe = make_recipe(db, auth_household, auth_user, ingredient, "First meal")
    second_recipe = make_recipe(db, auth_household, auth_user, ingredient, "Second meal")
    plan = replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_START,
        MealPlanReplaceRequest(
            entries=[entry(first_recipe)],
        ),
    )
    db.rollback()

    plan_selected = Event()
    replacement_committed = Event()
    read_plan = meal_plan_service._read_plan

    def pause_after_plan_read(session, selected_plan):
        if session.get_bind().get_execution_options().get("isolation_level") == "REPEATABLE READ":
            plan_selected.set()
            assert replacement_committed.wait(timeout=10)
        return read_plan(session, selected_plan)

    monkeypatch.setattr(meal_plan_service, "_read_plan", pause_after_plan_read)

    def read_current_plan():
        with Session(engine, autoflush=False, expire_on_commit=False) as reader:
            return get_plan(reader, auth_household.id, plan.id)

    def replace_current_plan():
        assert plan_selected.wait(timeout=10)
        with Session(engine, autoflush=False, expire_on_commit=False) as writer:
            updated = replace_week(
                writer,
                auth_household.id,
                auth_user.id,
                WEEK_START,
                MealPlanReplaceRequest(
                    expected_revision=plan.revision,
                    entries=[entry(second_recipe, slot="dinner")],
                ),
            )
        replacement_committed.set()
        return updated

    with ThreadPoolExecutor(max_workers=2) as workers:
        read_future = workers.submit(read_current_plan)
        replace_future = workers.submit(replace_current_plan)
        read_result = read_future.result(timeout=15)
        replacement = replace_future.result(timeout=15)

    assert replacement.revision == 2
    assert read_result.revision == 1
    assert len(read_result.entries) == 1
    assert read_result.entries[0].recipe_id == first_recipe.id
    assert read_result.entries[0].recipe_title == first_recipe.title


def test_plan_rejects_foreign_recipe_and_composite_fk_blocks_tampering(
    db, engine, auth_household, auth_user
):
    ingredient = setup_ingredient(db)
    foreign_user = User(
        email="foreign-mealplan@example.test",
        hashed_password="not-used",
        is_active=True,
    )
    db.add(foreign_user)
    db.flush()
    foreign_household = Household(name="Foreign home", slug="foreign-mealplan-home")
    db.add(foreign_household)
    db.flush()
    db.add(
        HouseholdMembership(
            household_id=foreign_household.id,
            user_id=foreign_user.id,
            role=HouseholdRole.OWNER.value,
            is_default=True,
        )
    )
    db.commit()
    foreign_recipe = make_recipe(db, foreign_household, foreign_user, ingredient, "Foreign stew")
    local_plan = replace_week(
        db,
        auth_household.id,
        auth_user.id,
        WEEK_START,
        MealPlanReplaceRequest(expected_revision=None, entries=[]),
    )

    with local_client(db, auth_user) as client:
        response = client.put(
            f"/meal-plans/weeks/{WEEK_START.isoformat()}",
            json={
                "expected_revision": local_plan.revision,
                "entries": [entry(foreign_recipe)],
            },
        )
        assert response.status_code == 404

    with Session(engine, autoflush=False) as tamper:
        tamper.add(
            MealPlanEntry(
                household_id=auth_household.id,
                plan_id=local_plan.id,
                meal_date=WEEK_START,
                slot="breakfast",
                position=0,
                recipe_id=foreign_recipe.id,
                recipe_revision=foreign_recipe.revision,
                servings=Decimal("1"),
            )
        )
        with pytest.raises(IntegrityError):
            tamper.commit()
        tamper.rollback()

    assert db.scalar(
        select(func.count()).select_from(MealPlanEntry).where(
            MealPlanEntry.plan_id == local_plan.id
        )
    ) == 0
