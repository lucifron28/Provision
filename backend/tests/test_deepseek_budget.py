from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace

import pytest
import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core import database
from app.models.deepseek_budget import DeepSeekBudget
from app.services.deepseek_budget import PostgresDeepSeekBudget
from app.services.deepseek_provider import (
    DeepSeekHTTPError, DeepSeekProvider, DeepSeekProviderError, DeepSeekRateLimitError, DeepSeekRequestBudgetExceeded,
)
from app.schemas.deepseek import DeepSeekSearchRequest
from test_deepseek_provider import make_settings


def settings(*, budget=20, rate=20):
    return SimpleNamespace(DEEPSEEK_REQUEST_BUDGET=budget, DEEPSEEK_REQUESTS_PER_MINUTE=rate)


def test_budget_is_shared_across_instances_and_survives_caller_rollback(db):
    first = PostgresDeepSeekBudget(settings(budget=2))
    second = PostgresDeepSeekBudget(settings(budget=2))
    first.consume("chat")
    db.rollback()
    second.consume("search")
    with pytest.raises(DeepSeekRequestBudgetExceeded):
        PostgresDeepSeekBudget(settings(budget=2)).consume("chat")
    assert db.scalar(select(DeepSeekBudget.used)) == 2


def test_concurrent_workers_cannot_exceed_budget():
    def attempt(_):
        try:
            PostgresDeepSeekBudget(settings(budget=3)).consume("chat")
            return True
        except DeepSeekRequestBudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as executor:
        assert sum(executor.map(attempt, range(8))) == 3


def test_rate_limit_resets_without_resetting_total():
    budget = PostgresDeepSeekBudget(settings(budget=3, rate=1))
    budget.consume("chat")
    with pytest.raises(DeepSeekRateLimitError):
        budget.consume("search")
    with database.engine.begin() as connection:
        connection.execute(update(DeepSeekBudget).values(
            window_started=DeepSeekBudget.window_started - timedelta(seconds=61)
        ))
    budget.consume("search")
    with database.engine.connect() as connection:
        assert connection.scalar(select(DeepSeekBudget.used)) == 2


def test_failed_provider_request_still_consumes_shared_budget():
    config = make_settings(DEEPSEEK_REQUEST_BUDGET=1)
    transport = httpx.MockTransport(lambda request: httpx.Response(503))
    with DeepSeekProvider(config, transport=transport, budget=PostgresDeepSeekBudget(config)) as provider:
        with pytest.raises(DeepSeekHTTPError):
            provider.search(DeepSeekSearchRequest(query="adobo"))
        with pytest.raises(DeepSeekRequestBudgetExceeded):
            provider.search(DeepSeekSearchRequest(query="adobo"))


def test_budget_database_failure_prevents_provider_request():
    class UnavailableBudget:
        def consume(self, operation):
            raise SQLAlchemyError("private database detail")

    def unexpected_request(request):
        pytest.fail("provider must not be called when budget storage fails")

    with DeepSeekProvider(make_settings(), transport=httpx.MockTransport(unexpected_request),
                          budget=UnavailableBudget()) as provider:
        with pytest.raises(DeepSeekProviderError) as error:
            provider.search(DeepSeekSearchRequest(query="adobo"))
    assert error.value.code == "budget_unavailable"
    assert "private database detail" not in str(error.value)
