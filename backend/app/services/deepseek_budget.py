"""Durable, process-independent DeepSeek request budget."""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.models.deepseek_budget import DeepSeekBudget, HouseholdDeepSeekBudget
from app.services.deepseek_provider import DeepSeekProviderError, DeepSeekRateLimitError, DeepSeekRequestBudgetExceeded


class PostgresDeepSeekBudget:
    def __init__(self, settings, household_id=None):
        self.settings = settings
        self.household_id = household_id

    def prepare_household(self) -> None:
        """Create the FK-backed row before the caller takes its household lock."""
        if self.household_id is None:
            raise ValueError("A household is required")
        from app.core import database

        with database.engine.begin() as connection:
            timeout_ms = max(1, int(self.settings.DEEPSEEK_TIMEOUT_SECONDS * 1000))
            connection.execute(select(func.set_config("lock_timeout", f"{timeout_ms}ms", True)))
            connection.execute(select(func.set_config("statement_timeout", f"{timeout_ms}ms", True)))
            connection.execute(
                insert(HouseholdDeepSeekBudget).values(household_id=self.household_id, used=0)
                .on_conflict_do_nothing(index_elements=[HouseholdDeepSeekBudget.household_id])
            )

    def consume(self, operation: str) -> None:
        # A separate committed transaction counts attempts even when the caller
        # rolls back, the provider times out, or another worker serves the call.
        from app.core import database

        with database.engine.begin() as connection:
            # Do not let a stalled worker hold up other requests indefinitely.
            timeout_ms = max(1, int(self.settings.DEEPSEEK_TIMEOUT_SECONDS * 1000))
            connection.execute(
                select(func.set_config("lock_timeout", f"{timeout_ms}ms", True))
            )
            connection.execute(
                select(func.set_config("statement_timeout", f"{timeout_ms}ms", True))
            )
            now = connection.scalar(select(func.clock_timestamp()))
            connection.execute(
                insert(DeepSeekBudget).values(id=1, used=0, window_used=0, window_started=now)
                .on_conflict_do_nothing(index_elements=[DeepSeekBudget.id])
            )
            row = connection.execute(
                select(DeepSeekBudget.__table__).where(DeepSeekBudget.id == 1).with_for_update()
            ).one()
            # Get time again after waiting for the row lock.
            now = connection.scalar(select(func.clock_timestamp()))
            if row.used >= self.settings.DEEPSEEK_REQUEST_BUDGET:
                raise DeepSeekRequestBudgetExceeded(operation)
            household_row = None
            if self.household_id is not None:
                household_row = connection.execute(
                    select(HouseholdDeepSeekBudget.__table__)
                    .where(HouseholdDeepSeekBudget.household_id == self.household_id)
                    .with_for_update()
                ).one_or_none()
                if household_row is None:
                    raise DeepSeekProviderError("DeepSeek request budget is unavailable.",
                                                operation=operation, code="budget_unavailable")
                if household_row.used >= self.settings.DEEPSEEK_HOUSEHOLD_REQUEST_BUDGET:
                    raise DeepSeekRequestBudgetExceeded(operation)
            elapsed = (now - row.window_started).total_seconds()
            window_started = row.window_started
            window_used = row.window_used
            if elapsed >= 60:
                window_started = now
                window_used = 0
            if window_used >= self.settings.DEEPSEEK_REQUESTS_PER_MINUTE:
                raise DeepSeekRateLimitError(operation, retry_after_seconds=max(0, 60 - elapsed))
            connection.execute(
                update(DeepSeekBudget).where(DeepSeekBudget.id == 1).values(
                    used=row.used + 1, window_used=window_used + 1, window_started=window_started
                )
            )
            if household_row is not None:
                connection.execute(
                    update(HouseholdDeepSeekBudget)
                    .where(HouseholdDeepSeekBudget.household_id == self.household_id)
                    .values(used=household_row.used + 1)
                )
