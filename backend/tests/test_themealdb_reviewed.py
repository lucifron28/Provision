from contextlib import contextmanager

import pytest
from fastapi import HTTPException

from app.services.themealdb_reviewed import lookup_reviewed_meal
from app.services.themealdb import MealDBRateLimited
from test_deepseek_discovery import _add_source, _grant
from test_themealdb_budget import make_budget


class Budget:
    def __init__(self):
        self.used = 0

    @contextmanager
    def request(self):
        self.used += 1
        yield


class Client:
    def __init__(self, meal, callback=None):
        self.meal = meal
        self.callback = callback
        self.calls = 0

    def lookup(self, meal_id):
        self.calls += 1
        if self.callback:
            self.callback()
        if isinstance(self.meal, Exception):
            raise self.meal
        return self.meal


def add_api_source(db):
    source = _add_source(db, "www.themealdb.com", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "extraction_methods": ["api_json"]}
    db.flush()
    return source


def add_origin(db):
    source = _add_source(db, "recipes.publisher.example.com", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.flush()
    return source


def call(db, user, household, client, budget):
    return lookup_reviewed_meal(db, household.id, user.id, "123", client=client, budget=budget)


def test_requires_api_approval_before_network(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    client, budget = Client(None), Budget()
    with pytest.raises(HTTPException):
        call(db, auth_user, auth_household, client, budget)
    assert client.calls == budget.used == 0


def test_requires_original_source_permission(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    add_api_source(db)
    client = Client({"idMeal": "123", "strSource": "https://recipes.publisher.example.com/adobo"})
    budget = Budget()
    with pytest.raises(HTTPException) as error:
        call(db, auth_user, auth_household, client, budget)
    assert error.value.detail == "MEAL_SOURCE_UNVERIFIED"
    assert client.calls == budget.used == 1


def test_returns_untrusted_record_only_when_both_sources_approved(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    api, origin = add_api_source(db), add_origin(db)
    client = Client({"idMeal": "123", "strSource": "https://recipes.publisher.example.com/adobo"})
    result = call(db, auth_user, auth_household, client, Budget())
    assert result.untrusted_content is True
    assert (result.api_source_id, result.original_source_id) == (api.id, origin.id)


def test_api_revocation_during_fetch_discards_result(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    source = add_api_source(db)
    add_origin(db)
    def revoke():
        source.policy = {**source.policy, "enabled": False}
        db.flush()
    client = Client({"idMeal": "123", "strSource": "https://recipes.publisher.example.com/adobo"}, revoke)
    with pytest.raises(HTTPException) as error:
        call(db, auth_user, auth_household, client, Budget())
    assert error.value.detail == "RECIPE_FETCH_NOT_AUTHORIZED"


def test_api_revocation_during_budget_check_prevents_fetch(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    source = add_api_source(db)
    class RevokingBudget:
        @contextmanager
        def request(self):
            source.policy = {**source.policy, "enabled": False}
            db.flush()
            yield
    client = Client(None)
    with pytest.raises(HTTPException) as error:
        call(db, auth_user, auth_household, client, RevokingBudget())
    assert error.value.detail == "RECIPE_FETCH_NOT_AUTHORIZED"
    assert client.calls == 0


def test_rate_limit_blocks_following_lookup_across_budget_instances(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    add_api_source(db)
    client = Client(MealDBRateLimited("120"))
    with pytest.raises(HTTPException) as first:
        call(db, auth_user, auth_household, client, make_budget())
    assert first.value.detail == "MEALDB_RATE_LIMITED"
    with pytest.raises(HTTPException) as second:
        call(db, auth_user, auth_household, client, make_budget())
    assert second.value.detail == "MEALDB_REQUEST_RATE_LIMITED"
    assert client.calls == 1
