"""Household-scoped weekly plan reads, replacement, archive and history."""

from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import delete, select, tuple_
from sqlalchemy.orm import Session

from app.models.meal_plan import MealPlan, MealPlanEntry, MealPlanRevision
from app.models.recipe import Recipe, RecipeRevision
from app.schemas.meal_plan import (
    MealPlanEntryInput,
    MealPlanEntryRead,
    MealPlanRead,
    MealPlanReplaceRequest,
    MealPlanRevisionRead,
)
from app.services.household_writes import lock_household_write
from app.services.recipe_sources import recipe_source_context
from app.services.recipe_shopping import _readonly_snapshot


def _week_start(value: date) -> date:
    if value.weekday() != 0:
        raise HTTPException(status_code=422, detail="WEEK_START_MUST_BE_MONDAY")
    return value


def _revision_snapshots(
    db: Session, household_id: int, entries: list[MealPlanEntry]
) -> dict[tuple[int, int], dict]:
    if not entries:
        return {}
    revision_keys = {(entry.recipe_id, entry.recipe_revision) for entry in entries}
    rows = db.scalars(
        select(RecipeRevision)
        .where(
            RecipeRevision.household_id == household_id,
            tuple_(RecipeRevision.recipe_id, RecipeRevision.revision).in_(
                sorted(revision_keys)
            ),
        )
        .execution_options(populate_existing=True)
    ).all()
    return {(row.recipe_id, row.revision): row.snapshot for row in rows}


def _read_plan(db: Session, plan: MealPlan) -> MealPlanRead:
    entries = db.scalars(
        select(MealPlanEntry)
        .where(
            MealPlanEntry.household_id == plan.household_id,
            MealPlanEntry.plan_id == plan.id,
        )
        .order_by(
            MealPlanEntry.meal_date,
            MealPlanEntry.slot,
            MealPlanEntry.position,
            MealPlanEntry.id,
        )
        .execution_options(populate_existing=True)
    ).all()
    snapshots = _revision_snapshots(db, plan.household_id, entries)
    return MealPlanRead(
        id=plan.id,
        week_start=plan.week_start,
        revision=plan.revision,
        is_active=plan.is_active,
        entries=[
            MealPlanEntryRead(
                id=entry.id,
                meal_date=entry.meal_date,
                slot=entry.slot,
                position=entry.position,
                recipe_id=entry.recipe_id,
                recipe_revision=entry.recipe_revision,
                recipe_title=snapshots[(entry.recipe_id, entry.recipe_revision)]["title"],
                servings=entry.servings,
            )
            for entry in entries
        ],
    )


def _find_plan(db: Session, household_id: int, plan_id: int, *, lock: bool = False):
    statement = select(MealPlan).where(
        MealPlan.household_id == household_id,
        MealPlan.id == plan_id,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement.execution_options(populate_existing=True))


def list_plans(
    db: Session,
    household_id: int,
    *,
    from_week: date | None = None,
    to_week: date | None = None,
) -> list[MealPlanRead]:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        return _list_plans(snapshot, household_id, from_week=from_week, to_week=to_week)


def _list_plans(
    db: Session,
    household_id: int,
    *,
    from_week: date | None = None,
    to_week: date | None = None,
) -> list[MealPlanRead]:
    statement = select(MealPlan).where(
        MealPlan.household_id == household_id,
        MealPlan.is_active.is_(True),
    )
    if from_week is not None:
        statement = statement.where(MealPlan.week_start >= _week_start(from_week))
    if to_week is not None:
        statement = statement.where(MealPlan.week_start <= _week_start(to_week))
    if from_week is not None and to_week is not None and to_week < from_week:
        raise HTTPException(status_code=422, detail="INVALID_WEEK_RANGE")
    plans = db.scalars(statement.order_by(MealPlan.week_start).execution_options(populate_existing=True)).all()
    return [_read_plan(db, plan) for plan in plans]


def get_plan(db: Session, household_id: int, plan_id: int) -> MealPlanRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        return get_plan_in_session(snapshot, household_id, plan_id)


def get_plan_in_session(
    db: Session, household_id: int, plan_id: int
) -> MealPlanRead:
    plan = _find_plan(db, household_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return _read_plan(db, plan)


def get_plan_for_week(db: Session, household_id: int, week_start: date) -> MealPlanRead:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        return _get_plan_for_week(snapshot, household_id, week_start)


def _get_plan_for_week(
    db: Session, household_id: int, week_start: date
) -> MealPlanRead:
    plan = db.scalar(
        select(MealPlan)
        .where(MealPlan.household_id == household_id, MealPlan.week_start == _week_start(week_start))
        .execution_options(populate_existing=True)
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return _read_plan(db, plan)


def _validate_entries(
    db: Session,
    household_id: int,
    week_start: date,
    entries: list[MealPlanEntryInput],
) -> None:
    week_end = week_start + timedelta(days=7)
    for entry in entries:
        if not week_start <= entry.meal_date < week_end:
            raise HTTPException(status_code=422, detail="MEAL_DATE_OUTSIDE_PLAN_WEEK")

    recipe_ids = {entry.recipe_id for entry in entries}
    if not recipe_ids:
        return
    recipes = {
        recipe.id: recipe
        for recipe in db.scalars(
            select(Recipe)
            .where(
                Recipe.household_id == household_id,
                Recipe.id.in_(recipe_ids),
            )
            .execution_options(populate_existing=True)
        ).all()
    }
    needed_revisions = {(entry.recipe_id, entry.recipe_revision) for entry in entries}
    revisions = {
        (row.recipe_id, row.revision): row
        for row in db.scalars(
            select(RecipeRevision)
            .where(
                RecipeRevision.household_id == household_id,
                tuple_(RecipeRevision.recipe_id, RecipeRevision.revision).in_(
                    sorted(needed_revisions)
                ),
            )
            .execution_options(populate_existing=True)
        ).all()
    }
    for recipe_id, revision in needed_revisions:
        recipe = recipes.get(recipe_id)
        snapshot = revisions.get((recipe_id, revision))
        if recipe is None or snapshot is None:
            raise HTTPException(status_code=404, detail="Household recipe revision not found")
        if not recipe.is_active:
            raise HTTPException(status_code=409, detail="RECIPE_ARCHIVED")
        if (
            snapshot.snapshot.get("content_permission")
            != "OWNED_OR_PERMISSION_GRANTED"
            or recipe.content.get("content_permission")
            != "OWNED_OR_PERMISSION_GRANTED"
        ):
            raise HTTPException(status_code=422, detail="RECIPE_CONTENT_PERMISSION_REQUIRED")
    for recipe_id, revision in needed_revisions:
        source_allowed, _priority, _reference = recipe_source_context(
            db, household_id, recipe_id, recipe_revision=revision
        )
        if not source_allowed:
            raise HTTPException(status_code=409, detail="SOURCE_NOT_AVAILABLE")


def _record_revision(db: Session, plan: MealPlan, actor_id: int) -> None:
    snapshot = _read_plan(db, plan).model_dump(mode="json")
    db.add(
        MealPlanRevision(
            household_id=plan.household_id,
            plan_id=plan.id,
            revision=plan.revision,
            snapshot=snapshot,
            created_by_user_id=actor_id,
        )
    )


def replace_week(
    db: Session,
    household_id: int,
    actor_id: int,
    week_start: date,
    request: MealPlanReplaceRequest,
) -> MealPlanRead:
    week_start = _week_start(week_start)
    lock_household_write(db, household_id, actor_id=actor_id)
    plan = db.scalar(
        select(MealPlan)
        .where(MealPlan.household_id == household_id, MealPlan.week_start == week_start)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if plan is None:
        if request.expected_revision is not None:
            raise HTTPException(status_code=409, detail="PLAN_REVISION_CONFLICT")
        plan = MealPlan(
            household_id=household_id,
            week_start=week_start,
            revision=1,
            is_active=True,
            created_by_user_id=actor_id,
        )
        db.add(plan)
        db.flush()
    else:
        if not plan.is_active:
            raise HTTPException(status_code=409, detail="PLAN_ARCHIVED")
        if request.expected_revision != plan.revision:
            raise HTTPException(status_code=409, detail="PLAN_REVISION_CONFLICT")

    _validate_entries(db, household_id, week_start, request.entries)
    if plan.revision > 1 or request.expected_revision is not None:
        plan.revision += 1
    db.execute(
        delete(MealPlanEntry).where(
            MealPlanEntry.household_id == household_id,
            MealPlanEntry.plan_id == plan.id,
        )
    )
    db.flush()
    db.add_all(
        [
            MealPlanEntry(
                household_id=household_id,
                plan_id=plan.id,
                meal_date=entry.meal_date,
                slot=entry.slot,
                position=entry.position,
                recipe_id=entry.recipe_id,
                recipe_revision=entry.recipe_revision,
                servings=entry.servings,
            )
            for entry in request.entries
        ]
    )
    db.flush()
    _record_revision(db, plan, actor_id)
    result = _read_plan(db, plan)
    db.commit()
    return result


def archive_plan(
    db: Session,
    household_id: int,
    actor_id: int,
    plan_id: int,
    expected_revision: int,
) -> None:
    lock_household_write(db, household_id, actor_id=actor_id)
    plan = _find_plan(db, household_id, plan_id, lock=True)
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    if not plan.is_active or plan.revision != expected_revision:
        raise HTTPException(status_code=409, detail="PLAN_REVISION_CONFLICT")
    plan.is_active = False
    plan.revision += 1
    _record_revision(db, plan, actor_id)
    db.commit()


def plan_history(
    db: Session, household_id: int, plan_id: int
) -> list[MealPlanRevisionRead]:
    with _readonly_snapshot(db.get_bind()) as snapshot:
        return _plan_history(snapshot, household_id, plan_id)


def _plan_history(
    db: Session, household_id: int, plan_id: int
) -> list[MealPlanRevisionRead]:
    plan = _find_plan(db, household_id, plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    revisions = db.scalars(
        select(MealPlanRevision)
        .where(
            MealPlanRevision.household_id == household_id,
            MealPlanRevision.plan_id == plan_id,
        )
        .order_by(MealPlanRevision.revision)
        .execution_options(populate_existing=True)
    ).all()
    return [
        MealPlanRevisionRead(
            revision=row.revision,
            created_at=row.created_at,
            created_by_user_id=row.created_by_user_id,
            snapshot=row.snapshot,
        )
        for row in revisions
    ]
