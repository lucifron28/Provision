"""Durable, serialized TheMealDB requests across backend workers."""

from contextlib import contextmanager
from datetime import timedelta, timezone
from email.utils import parsedate_to_datetime

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.models.themealdb_budget import MealDBBudget
from app.services.themealdb import MealDBRateLimited


_LOCK = 734962182


def _retry_deadline(value: str | None, now):
    if not isinstance(value, str) or len(value) > 128:
        return None
    value = value.strip()
    try:
        if value.isascii() and value.isdecimal() and len(value) <= 9:
            return now + timedelta(seconds=int(value))
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            return None
        return max(now, parsed.astimezone(timezone.utc))
    except (TypeError, ValueError, OverflowError):
        return None


class PostgresMealDBBudget:
    def __init__(self, settings):
        self.settings = settings

    @contextmanager
    def request(self):
        """Reserve one request and hold an advisory lock until it finishes.

        A crash, transport failure, or unparseable Retry-After leaves the
        durable row paused. An operator must review and clear it deliberately.
        """
        from app.core import database

        with database.engine.connect() as connection:
            acquired = False
            try:
                acquired = connection.scalar(select(func.pg_try_advisory_lock(_LOCK)))
                if not acquired:
                    raise HTTPException(429, "MEALDB_REQUEST_BUSY")
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(text("SET LOCAL statement_timeout = '2s'"))
                now = connection.scalar(select(func.clock_timestamp()))
                connection.execute(
                    insert(MealDBBudget).values(id=1, used=0, next_allowed=now, paused=False)
                    .on_conflict_do_nothing(index_elements=[MealDBBudget.id])
                )
                row = connection.execute(select(MealDBBudget.__table__).where(MealDBBudget.id == 1).with_for_update()).one()
                now = connection.scalar(select(func.clock_timestamp()))
                if row.paused:
                    raise HTTPException(503, "MEALDB_BUDGET_PAUSED")
                if row.used >= self.settings.MEALDB_REQUEST_BUDGET:
                    raise HTTPException(429, "MEALDB_REQUEST_BUDGET_EXHAUSTED")
                if row.next_allowed > now:
                    raise HTTPException(429, "MEALDB_REQUEST_RATE_LIMITED")
                connection.execute(update(MealDBBudget).where(MealDBBudget.id == 1).values(
                    used=row.used + 1,
                    next_allowed=now + timedelta(seconds=self.settings.MEALDB_MIN_INTERVAL_SECONDS),
                    paused=True,
                ))
                connection.commit()
                try:
                    yield
                except MealDBRateLimited as exc:
                    now = connection.scalar(select(func.clock_timestamp()))
                    deadline = _retry_deadline(exc.retry_after, now)
                    if deadline is not None:
                        connection.execute(update(MealDBBudget).where(MealDBBudget.id == 1).values(
                            next_allowed=func.greatest(MealDBBudget.next_allowed, deadline), paused=False
                        ))
                        connection.commit()
                    raise
                else:
                    connection.execute(update(MealDBBudget).where(MealDBBudget.id == 1).values(paused=False))
                    connection.commit()
            finally:
                connection.rollback()
                if acquired:
                    try:
                        connection.execute(select(func.pg_advisory_unlock(_LOCK)))
                        connection.commit()
                    except Exception:
                        connection.invalidate()
                        raise
