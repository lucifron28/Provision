from sqlalchemy import func, select
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.recipe_sources import get_wikibooks_transport, get_wikimedia_budget
from app.core.config import settings
from app.main import app
from app.models.shopping import ShoppingListItem
from app.services.deepseek_discovery import PageFetchResponse
from app.services.deepseek_discovery import authorize_recipe_fetch
from test_deepseek_discovery import FakePinnedTransport, _add_source, _grant
from test_themealdb_reviewed import Budget


def test_preview_returns_untrusted_text_with_attribution(client, db, auth_user, auth_household, monkeypatch):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    transport = FakePinnedTransport(responses=[
        PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /wiki/\n"),
        PageFetchResponse(200, {"content-type": "text/html"},
            b"<h2>Ingredients</h2><ul><li>salt to taste</li></ul>"
            b"<h2>Preparation</h2><ol><li>Cook.</li></ol>"),
    ])
    app.dependency_overrides[get_wikibooks_transport] = lambda: transport
    app.dependency_overrides[get_wikimedia_budget] = lambda: Budget()
    result = client.post("/api/v1/recipe-sources/wikibooks/adobo/preview")
    assert result.status_code == 200, result.text
    data = result.json()
    assert data["ingredients"] == ["salt to taste"]
    assert data["publisher"] == "Wikibooks contributors"
    assert data["license_url"] == "https://creativecommons.org/licenses/by-sa/4.0/"
    assert data["adapted"] is False and data["safety"] == "review_required"
    assert data["untrusted_content"] is True
    assert result.headers["cache-control"] == "no-store"
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0


def test_other_wikibooks_pages_remain_unapproved(db):
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    with pytest.raises(HTTPException) as error:
        authorize_recipe_fetch(db, "https://en.wikibooks.org/wiki/Cookbook:Another_Recipe")
    assert error.value.status_code == 403


def test_disabled_source_does_not_fetch(client, db, auth_user, auth_household, monkeypatch):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "enabled": False}
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    transport = FakePinnedTransport()
    app.dependency_overrides[get_wikibooks_transport] = lambda: transport
    app.dependency_overrides[get_wikimedia_budget] = lambda: Budget()
    result = client.post("/api/v1/recipe-sources/wikibooks/adobo/preview")
    assert result.status_code == 403
    assert transport.requests == []


def test_preview_requires_current_consent(client, db, monkeypatch):
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    transport = FakePinnedTransport()
    app.dependency_overrides[get_wikibooks_transport] = lambda: transport
    app.dependency_overrides[get_wikimedia_budget] = lambda: Budget()
    result = client.post("/api/v1/recipe-sources/wikibooks/adobo/preview")
    assert result.status_code == 403
    assert transport.requests == []
