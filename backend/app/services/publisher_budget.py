"""Durable, fail-closed budgets and pacing for publisher HTTP requests."""
from contextlib import contextmanager
from datetime import timedelta
from math import ceil
from time import sleep

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.core.config import settings
from app.models.publisher_budget import PublisherBudget, PublisherPacing


class PublisherRequestError(HTTPException):
    """Sanitized, expected publisher request refusal."""


def _limited(seconds, code="PUBLISHER_REQUEST_RATE_LIMITED"):
    return PublisherRequestError(429, code, headers={"Retry-After": str(max(1, ceil(seconds)))})


class PublisherRequestBudget:
    def consume(self):
        """Reserve only the global counter, retained for direct budget callers."""
        from app.core import database
        try:
            with database.engine.begin() as connection:
                self._consume_global(connection)
        except PublisherRequestError:
            raise
        except Exception:
            raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None

    def _consume_global(self, connection):
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
            raise PublisherRequestError(429, "PUBLISHER_REQUEST_BUDGET_EXHAUSTED")
        connection.execute(update(PublisherBudget).where(PublisherBudget.id == 1).values(
            used=used + 1, window_started=start))

    @contextmanager
    def request(self, source_id, canonical_host):
        """Serialize one publisher's request through response cooldown recording."""
        from app.core import database
        policy = settings.PUBLISHER_PACING_OVERRIDES.get(canonical_host, settings.PUBLISHER_PACING_DEFAULT)
        try:
            connection = database.engine.connect()
        except Exception:
            raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None
        acquired = False
        response = None
        outbound_error = None
        try:
            acquired = connection.scalar(select(func.pg_try_advisory_lock(734963, source_id)))
            if not acquired:
                raise _limited(1, "PUBLISHER_REQUEST_BUSY")
            connection.execute(select(func.set_config("lock_timeout", "2000ms", True)))
            connection.execute(select(func.set_config("statement_timeout", "2000ms", True)))
            now = connection.scalar(select(func.clock_timestamp()))
            connection.execute(insert(PublisherPacing).values(source_id=source_id, window_started=now,
                window_used=0, next_allowed=now, paused=False).on_conflict_do_nothing(index_elements=[PublisherPacing.source_id]))
            row = connection.execute(select(PublisherPacing.__table__).where(
                PublisherPacing.source_id == source_id).with_for_update()).one()
            now = connection.scalar(select(func.clock_timestamp()))
            if row.paused:
                raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE")
            delay = (row.next_allowed - now).total_seconds()
            if delay > 1:
                raise _limited(delay)
            if delay > 0:
                sleep(delay)
                now = connection.scalar(select(func.clock_timestamp()))
            used, start = ((0, now) if now - row.window_started >= timedelta(seconds=policy.window_seconds)
                           else (row.window_used, row.window_started))
            if used >= policy.window_requests:
                raise _limited((start + timedelta(seconds=policy.window_seconds) - now).total_seconds())
            self._consume_global(connection)
            now = connection.scalar(select(func.clock_timestamp()))
            connection.execute(update(PublisherPacing).where(PublisherPacing.source_id == source_id).values(
                window_used=used + 1, window_started=start,
                next_allowed=now + timedelta(seconds=policy.min_interval_seconds), paused=True))
            connection.commit()
            def record(value):
                nonlocal response
                response = value
            try:
                yield record
            except BaseException as error:
                outbound_error = error
                raise
            finally:
                # A crash or failed update leaves paused=True, so future requests fail closed.
                now = connection.scalar(select(func.clock_timestamp()))
                deadline = now + timedelta(seconds=policy.min_interval_seconds)
                upstream_limited = False
                if outbound_error is not None:
                    deadline = max(deadline, now + timedelta(seconds=min(60, settings.PUBLISHER_MAX_COOLDOWN_SECONDS)))
                response_status = getattr(response, "status_code", None)
                headers = getattr(response, "headers", None)
                retry_values = ([v for k, v in headers.items()
                                 if isinstance(k, str) and k.casefold() == "retry-after"]
                                if isinstance(headers, dict) else [])
                if response_status in {429, 503} or retry_values:
                    from app.services.themealdb_budget import _retry_deadline
                    parsed = _retry_deadline(retry_values[0], now) if len(retry_values) == 1 else None
                    seconds = 60 if parsed is None else max(1, ceil((parsed - now).total_seconds()))
                    deadline = max(deadline, now + timedelta(seconds=min(seconds, settings.PUBLISHER_MAX_COOLDOWN_SECONDS)))
                    upstream_limited = response_status in {429, 503}
                values = {"paused": False, "next_allowed": func.greatest(PublisherPacing.next_allowed, deadline)}
                connection.execute(update(PublisherPacing).where(PublisherPacing.source_id == source_id).values(**values))
                connection.commit()
            if upstream_limited:
                if response.status_code == 429:
                    raise _limited((deadline - now).total_seconds(), "PUBLISHER_UPSTREAM_RATE_LIMITED")
                raise PublisherRequestError(503, "PUBLISHER_UPSTREAM_UNAVAILABLE",
                    headers={"Retry-After": str(max(1, ceil((deadline - now).total_seconds())))})
        except PublisherRequestError:
            raise
        except TimeoutError as exc:
            if exc is outbound_error:
                raise
            raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None
        except Exception as exc:
            if exc is outbound_error:
                raise
            raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None
        finally:
            try:
                connection.rollback()
                if acquired:
                    unlocked = connection.scalar(select(func.pg_advisory_unlock(734963, source_id)))
                    if unlocked is not True:
                        raise RuntimeError("Publisher lock release failed")
                    connection.commit()
            except Exception:
                connection.invalidate()
                raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None
            finally:
                try:
                    connection.close()
                except Exception:
                    raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE") from None


class BudgetedPublisherTransport:
    def __init__(self, transport, budget, source_id, canonical_host):
        self.transport = transport
        self.budget = budget
        self.source_id = source_id
        self.canonical_host = canonical_host
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
        with self.budget.request(self.source_id, self.canonical_host) as record:
            response = self.transport.fetch_once_pinned(url, connect_ip=connect_ip,
                timeout_seconds=timeout_seconds, max_bytes=max_bytes)
            record(response)
            return response
