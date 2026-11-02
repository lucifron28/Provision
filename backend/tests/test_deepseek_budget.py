from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest
import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError

from app.core import database
from app.models.deepseek_budget import DeepSeekBudget
from app.models.deepseek_budget import HouseholdDeepSeekBudget
from app.models.household import Household
from app.services.deepseek_budget import PostgresDeepSeekBudget
from app.services.deepseek_provider import (
    DeepSeekHTTPError, DeepSeekProvider, DeepSeekProviderError, DeepSeekRateLimitError, DeepSeekRequestBudgetExceeded,
)
from app.schemas.deepseek import DeepSeekSearchRequest
from test_deepseek_provider import make_settings
from test_deepseek_provider import chat_wire
from test_privacy import _consent


def settings(*, budget=20, rate=20, household_budget=20):
    return SimpleNamespace(DEEPSEEK_REQUEST_BUDGET=budget, DEEPSEEK_REQUESTS_PER_MINUTE=rate,
                           DEEPSEEK_TIMEOUT_SECONDS=2, DEEPSEEK_HOUSEHOLD_REQUEST_BUDGET=household_budget)


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


def test_locked_budget_times_out_without_calling_provider():
    config = make_settings(DEEPSEEK_TIMEOUT_SECONDS=0.1)
    budget = PostgresDeepSeekBudget(config)
    budget.consume("search")

    def unexpected_request(request):
        pytest.fail("provider must not be called while budget storage is locked")

    with database.engine.begin() as connection:
        connection.execute(select(DeepSeekBudget).where(DeepSeekBudget.id == 1).with_for_update())
        with DeepSeekProvider(config, transport=httpx.MockTransport(unexpected_request), budget=budget) as provider:
            with pytest.raises(DeepSeekProviderError) as error:
                provider.search(DeepSeekSearchRequest(query="adobo"))
    assert error.value.code == "budget_unavailable"


def test_household_limits_are_independent_and_share_global_cap(db, auth_household):
    other = Household(name="Second", slug="budget-test-second")
    db.add(other)
    db.commit()
    config = settings(budget=3, household_budget=1)
    first = PostgresDeepSeekBudget(config, household_id=auth_household.id)
    second = PostgresDeepSeekBudget(config, household_id=other.id)
    first.prepare_household()
    second.prepare_household()
    first.consume("chat")
    with pytest.raises(DeepSeekRequestBudgetExceeded):
        first.consume("search")
    second.consume("chat")
    assert db.scalar(select(DeepSeekBudget.used)) == 2
    assert db.scalar(select(HouseholdDeepSeekBudget.used).where(
        HouseholdDeepSeekBudget.household_id == other.id)) == 1


def test_prepared_household_budget_works_while_household_is_locked(db, auth_household):
    budget = PostgresDeepSeekBudget(settings(), household_id=auth_household.id)
    budget.prepare_household()
    db.execute(select(Household).where(Household.id == auth_household.id).with_for_update())
    PostgresDeepSeekBudget(settings(), household_id=auth_household.id).prepare_household()
    budget.consume("chat")
    db.rollback()
    assert db.scalar(select(HouseholdDeepSeekBudget.used)) == 1


def test_concurrent_household_requests_respect_household_cap(db, auth_household):
    household_id = auth_household.id
    config = settings(household_budget=2)
    PostgresDeepSeekBudget(config, household_id=household_id).prepare_household()

    def attempt(_):
        try:
            PostgresDeepSeekBudget(config, household_id=household_id).consume("chat")
            return True
        except DeepSeekRequestBudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=6) as executor:
        assert sum(executor.map(attempt, range(6))) == 2
    assert db.scalar(select(DeepSeekBudget.used)) == 2
    assert db.scalar(select(HouseholdDeepSeekBudget.used)) == 2


def test_household_deletion_removes_its_quota(db, auth_household):
    household_id = auth_household.id
    budget = PostgresDeepSeekBudget(settings(), household_id=household_id)
    budget.prepare_household()
    budget.consume("chat")
    db.execute(delete(Household).where(Household.id == household_id))
    db.commit()
    assert db.scalar(select(HouseholdDeepSeekBudget.used)) is None
    assert db.scalar(select(DeepSeekBudget.used)) == 1


def test_generation_api_applies_household_quota(client, db, auth_user, auth_household, monkeypatch):
    from app.api.v1.endpoints import ai_recipes

    _consent(db, auth_user, auth_household)
    db.commit()
    config = make_settings(DEEPSEEK_HOUSEHOLD_REQUEST_BUDGET=1)
    calls = []
    recipe = {"title": "Rice", "servings": 1,
              "ingredients": [{"name": "rice", "amount": 1, "unit": "g", "required": True}],
              "steps": ["Cook the rice."]}

    def respond(request):
        calls.append(request)
        return httpx.Response(200, json=chat_wire(json.dumps(recipe)))

    monkeypatch.setattr(ai_recipes, "settings", config)
    monkeypatch.setattr(ai_recipes, "DeepSeekProvider", lambda settings, budget: DeepSeekProvider(
        settings, budget=budget, transport=httpx.MockTransport(respond)
    ))
    first = client.post("/api/v1/ai-recipes/generate", json={"dish": "rice"})
    second = client.post("/api/v1/ai-recipes/generate", json={"dish": "rice"})
    assert first.status_code == 200, first.text
    assert second.status_code == 429
    assert len(calls) == 1
    assert db.scalar(select(DeepSeekBudget.used)) == 1
    assert db.scalar(select(HouseholdDeepSeekBudget.used)) == 1
