"""Shared, fail-closed budget for publisher robots and content requests."""
from datetime import timedelta
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from app.models.publisher_budget import PublisherBudget


class PublisherRequestBudget:
    def consume(self):
        from app.core import database
        try:
            with database.engine.begin() as connection:
                connection.execute(select(func.set_config("lock_timeout", "2000ms", True)))
                connection.execute(select(func.set_config("statement_timeout", "2000ms", True)))
                now = connection.scalar(select(func.clock_timestamp()))
                connection.execute(insert(PublisherBudget).values(id=1, used=0, window_started=now)
                    .on_conflict_do_nothing(index_elements=[PublisherBudget.id]))
                row = connection.execute(select(PublisherBudget.__table__).where(
                    PublisherBudget.id == 1).with_for_update()).one()
                now = connection.scalar(select(func.clock_timestamp()))
                used, start = (0, now) if now - row.window_started >= timedelta(days=1) else (row.used, row.window_started)
                if used >= 1000:
                    raise HTTPException(429, "PUBLISHER_REQUEST_BUDGET_EXHAUSTED")
                connection.execute(update(PublisherBudget).where(PublisherBudget.id == 1).values(
                    used=used + 1, window_started=start))
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None


class BudgetedPublisherTransport:
    def __init__(self, transport, budget):
        self.transport = transport
        self.budget = budget
        self.addresses = {}

    @property
    def user_agent(self):
        return self.transport.user_agent

    def resolve(self, hostname):
        addresses = tuple(self.transport.resolve(hostname))
        previous = self.addresses.setdefault(hostname, frozenset(addresses))
        if previous != frozenset(addresses):
            raise ValueError("Publisher DNS answers changed during request")
        return addresses

    def fetch_once_pinned(self, url, *, connect_ip, timeout_seconds, max_bytes):
        self.budget.consume()
        return self.transport.fetch_once_pinned(url, connect_ip=connect_ip,
            timeout_seconds=timeout_seconds, max_bytes=max_bytes)
