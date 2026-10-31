from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, update

from app.models.themealdb_budget import MealDBBudget
from app.services.themealdb import MealDBRateLimited
from app.services.themealdb_budget import PostgresMealDBBudget, _retry_deadline


def make_budget():
    return PostgresMealDBBudget(SimpleNamespace(MEALDB_REQUEST_BUDGET=2, MEALDB_MIN_INTERVAL_SECONDS=2))


def test_budget_is_durable_serial_and_counts_attempts(engine):
    budget = make_budget()
    with budget.request():
        with engine.connect() as connection:
            row = connection.execute(select(MealDBBudget.__table__)).one()
            assert row.used == 1 and row.paused
        with pytest.raises(HTTPException) as busy:
            with make_budget().request():
                pass
        assert busy.value.detail == "MEALDB_REQUEST_BUSY"
    with pytest.raises(HTTPException) as limited:
        with make_budget().request():
            pass
    assert limited.value.detail == "MEALDB_REQUEST_RATE_LIMITED"
    with engine.begin() as connection:
        connection.execute(update(MealDBBudget).values(next_allowed=datetime.now(timezone.utc) - timedelta(seconds=1)))
    with make_budget().request():
        pass
    with engine.begin() as connection:
        connection.execute(update(MealDBBudget).values(next_allowed=datetime.now(timezone.utc) - timedelta(seconds=1)))
    with pytest.raises(HTTPException) as exhausted:
        with make_budget().request():
            pass
    assert exhausted.value.detail == "MEALDB_REQUEST_BUDGET_EXHAUSTED"


def test_retry_after_persists_across_budget_instances(engine):
    with pytest.raises(MealDBRateLimited):
        with make_budget().request():
            raise MealDBRateLimited("120")
    with engine.connect() as connection:
        row = connection.execute(select(MealDBBudget.__table__)).one()
        assert not row.paused and row.next_allowed > datetime.now(timezone.utc) + timedelta(seconds=110)
    with pytest.raises(HTTPException) as limited:
        with make_budget().request():
            pass
    assert limited.value.detail == "MEALDB_REQUEST_RATE_LIMITED"


@pytest.mark.parametrize("error", [MealDBRateLimited(None), RuntimeError("network failure")])
def test_unknown_retry_or_failure_pauses_until_operator_review(engine, error):
    with pytest.raises(type(error)):
        with make_budget().request():
            raise error
    with pytest.raises(HTTPException) as paused:
        with make_budget().request():
            pass
    assert paused.value.detail == "MEALDB_BUDGET_PAUSED"


def test_retry_after_http_date_and_invalid_value():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert _retry_deadline("Thu, 01 Jan 2026 00:02:00 GMT", now) == now + timedelta(seconds=120)
    assert _retry_deadline("not-a-date", now) is None
