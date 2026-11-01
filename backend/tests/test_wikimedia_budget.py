from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.models.wikimedia_budget import WikimediaBudget
from app.services.wikimedia_budget import PostgresWikimediaBudget
from app.services.wikimedia_transport import WikimediaRateLimited
from app.services.wikimedia_transport import REVIEWED_RECIPE_URL, fetch_reviewed_wikibooks


def test_budget_serializes_requests_and_persists_retry(engine):
    budget = PostgresWikimediaBudget()
    with pytest.raises(WikimediaRateLimited):
        with budget.request():
            with pytest.raises(HTTPException) as busy:
                with budget.request():
                    pass
            assert busy.value.detail == "WIKIMEDIA_REQUEST_BUSY"
            raise WikimediaRateLimited("120")
    with engine.connect() as connection:
        row = connection.execute(select(WikimediaBudget.__table__)).one()
        assert row.used == 1 and not row.paused
        assert row.next_allowed > datetime.now(timezone.utc) + timedelta(seconds=110)
    with pytest.raises(HTTPException) as limited:
        with PostgresWikimediaBudget().request():
            pass
    assert limited.value.detail == "WIKIMEDIA_REQUEST_RATE_LIMITED"


def test_unknown_failure_pauses_future_requests(engine):
    with pytest.raises(WikimediaRateLimited):
        with PostgresWikimediaBudget().request():
            raise WikimediaRateLimited(None)
    with pytest.raises(HTTPException) as paused:
        with PostgresWikimediaBudget().request():
            pass
    assert paused.value.detail == "WIKIMEDIA_BUDGET_PAUSED"


def test_normal_interval_allows_following_request(engine):
    budget = PostgresWikimediaBudget()
    with budget.request():
        pass
    with budget.request():
        pass
    with engine.connect() as connection:
        row = connection.execute(select(WikimediaBudget.__table__)).one()
        assert row.used == 2 and not row.paused


def test_reviewed_fetch_budgets_robots_and_page(db, auth_user, auth_household, monkeypatch):
    import app.services.deepseek_discovery as discovery
    from app.services.deepseek_discovery import PageFetchResponse, RecipeFetchAuthorization
    from test_deepseek_discovery import FakePinnedTransport, _grant

    _grant(db, auth_user, auth_household)
    url = REVIEWED_RECIPE_URL
    approval = RecipeFetchAuthorization(
        canonical_url=url, source_id=1, source_revision=1, publisher_name="Example",
        access_mode="licensed_full", extraction_methods=("full_text",),
        allowed_hosts=frozenset({"en.wikibooks.org"}), allowed_redirect_hosts=frozenset(),
    )
    monkeypatch.setattr(discovery, "authorize_recipe_fetch", lambda *args, **kwargs: approval)
    transport = FakePinnedTransport(responses=[
        PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /wiki/\n"),
        PageFetchResponse(200, {"content-type": "text/html"}, b"<p>recipe</p>"),
    ])
    page = fetch_reviewed_wikibooks(db, auth_household.id, auth_user.id, url,
                                    transport=transport, budget=PostgresWikimediaBudget())
    assert page.content == b"<p>recipe</p>"
    with db.bind.connect() as connection:
        row = connection.execute(select(WikimediaBudget.__table__)).one()
        assert row.used == 2 and not row.paused


def test_robots_rate_limit_persists_even_when_fetch_rejects(db, auth_user, auth_household, monkeypatch):
    import app.services.deepseek_discovery as discovery
    from app.services.deepseek_discovery import PageFetchResponse, RecipeFetchAuthorization
    from test_deepseek_discovery import FakePinnedTransport, _grant

    _grant(db, auth_user, auth_household)
    url = REVIEWED_RECIPE_URL
    approval = RecipeFetchAuthorization(
        canonical_url=url, source_id=1, source_revision=1, publisher_name="Example",
        access_mode="licensed_full", extraction_methods=("full_text",),
        allowed_hosts=frozenset({"en.wikibooks.org"}), allowed_redirect_hosts=frozenset(),
    )
    monkeypatch.setattr(discovery, "authorize_recipe_fetch", lambda *args, **kwargs: approval)
    transport = FakePinnedTransport(responses=[PageFetchResponse(429, {"retry-after": "120"}, b"")])
    with pytest.raises(HTTPException):
        fetch_reviewed_wikibooks(db, auth_household.id, auth_user.id, url,
                                  transport=transport, budget=PostgresWikimediaBudget())
    assert len(transport.requests) == 1
    with db.bind.connect() as connection:
        row = connection.execute(select(WikimediaBudget.__table__)).one()
        assert row.used == 1 and not row.paused
        assert row.next_allowed > datetime.now(timezone.utc) + timedelta(seconds=110)
