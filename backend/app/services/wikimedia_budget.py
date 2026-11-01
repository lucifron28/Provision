"""Serialize and rate-limit Wikimedia requests across backend workers."""

from contextlib import contextmanager
from datetime import timedelta
from math import ceil
from time import sleep

from fastapi import HTTPException
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.models.wikimedia_budget import WikimediaBudget
from app.services.themealdb_budget import _retry_deadline
from app.services.wikimedia_transport import WikimediaRateLimited


_LOCK = 734962183


class PostgresWikimediaBudget:
    """Use one request at a time and at least one second between starts."""

    def __init__(self, max_requests=100):
        if type(max_requests) is not int or max_requests < 1:
            raise ValueError("Invalid Wikimedia request budget")
        self.max_requests = max_requests

    @contextmanager
    def request(self):
        from app.core import database

        with database.engine.connect() as connection:
            acquired = False
            try:
                acquired = connection.scalar(select(func.pg_try_advisory_lock(_LOCK)))
                if not acquired:
                    raise HTTPException(429, "WIKIMEDIA_REQUEST_BUSY", headers={"Retry-After": "2"})
                connection.execute(text("SET LOCAL lock_timeout = '2s'"))
                connection.execute(text("SET LOCAL statement_timeout = '2s'"))
                now = connection.scalar(select(func.clock_timestamp()))
                connection.execute(insert(WikimediaBudget).values(
                    id=1, used=0, next_allowed=now, paused=False
                ).on_conflict_do_nothing(index_elements=[WikimediaBudget.id]))
                row = connection.execute(select(WikimediaBudget.__table__).where(
                    WikimediaBudget.id == 1).with_for_update()).one()
                now = connection.scalar(select(func.clock_timestamp()))
                if row.paused:
                    raise HTTPException(503, "WIKIMEDIA_BUDGET_PAUSED")
                if row.used >= self.max_requests:
                    raise HTTPException(429, "WIKIMEDIA_REQUEST_BUDGET_EXHAUSTED")
                # A normal request interval must not prevent the immediately
                # following robots/page request. Longer provider cooldowns are
                # returned to the caller instead of blocking a worker.
                remaining = (row.next_allowed - now).total_seconds()
                if 0 < remaining <= 1:
                    sleep(remaining)
                    now = connection.scalar(select(func.clock_timestamp()))
                if row.next_allowed > now:
                    delay = max(1, ceil((row.next_allowed - now).total_seconds()))
                    raise HTTPException(429, "WIKIMEDIA_REQUEST_RATE_LIMITED", headers={"Retry-After": str(delay)})
                connection.execute(update(WikimediaBudget).where(WikimediaBudget.id == 1).values(
                    used=row.used + 1, next_allowed=now + timedelta(seconds=1), paused=True))
                connection.commit()
                try:
                    yield
                except WikimediaRateLimited as error:
                    now = connection.scalar(select(func.clock_timestamp()))
                    deadline = _retry_deadline(error.retry_after, now)
                    if deadline is not None:
                        connection.execute(update(WikimediaBudget).where(WikimediaBudget.id == 1).values(
                            next_allowed=func.greatest(WikimediaBudget.next_allowed, deadline), paused=False))
                        connection.commit()
                    raise
                else:
                    connection.execute(update(WikimediaBudget).where(WikimediaBudget.id == 1).values(paused=False))
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
