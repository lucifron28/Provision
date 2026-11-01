"""Opt-in, bounded smoke test for the openly licensed Wikibooks source."""

import os

import pytest
from sqlalchemy import func, select

from app.services.pinned_page_transport import PinnedTLSTransport
from app.services.wikimedia_budget import PostgresWikimediaBudget
from app.services.wikimedia_transport import fetch_reviewed_wikibooks
from app.services.wikibooks_recipe import parse_wikibooks_recipe
from app.core.config import settings
from app.models.recipe import Recipe
from app.models.shopping import ShoppingListItem
from test_deepseek_discovery import _add_source, _grant


@pytest.mark.skipif(os.getenv("PROVISION_WIKIBOOKS_LIVE") != "1", reason="live fetch requires explicit opt-in")
def test_live_wikibooks_licensed_recipe_fetch(db, auth_user, auth_household):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    transport = PinnedTLSTransport(user_agent="ProvisionBot/1.0 (https://github.com/lucifron28/Provision)")
    page = fetch_reviewed_wikibooks(
        db, auth_household.id, auth_user.id,
        "https://en.wikibooks.org/wiki/Cookbook:Adobo_Chicken_(Philippine)",
        transport=transport, budget=PostgresWikimediaBudget(), allow_broader_web=False,
    )
    assert page.final_url.startswith("https://en.wikibooks.org/wiki/Cookbook:")
    assert page.content and page.untrusted_content
    ingredients, preparation = parse_wikibooks_recipe(page.content)
    assert ingredients and preparation


@pytest.mark.skipif(os.getenv("PROVISION_WIKIBOOKS_LIVE") != "1", reason="live fetch requires explicit opt-in")
def test_live_wikibooks_preview_endpoint(client, db, auth_user, auth_household, monkeypatch):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    response = client.post("/api/v1/recipe-sources/wikibooks/adobo/preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["ingredients"] and data["preparation"]
    assert data["license_name"] == "CC BY-SA 4.0"
    assert data["untrusted_content"] is True and data["safety"] == "review_required"


@pytest.mark.skipif(os.getenv("PROVISION_WIKIBOOKS_LIVE") != "1", reason="live fetch requires explicit opt-in")
def test_live_wikibooks_sinigang_preview(client, db, auth_user, auth_household, monkeypatch):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    source.revision = 2
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    response = client.post("/api/v1/recipe-sources/wikibooks/sinigang/preview")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "Sinigang (Philippine Sour Soup)"
    assert data["ingredients"] and data["preparation"]
    assert data["license_name"] == "CC BY-SA 4.0" and data["safety"] == "review_required"


@pytest.mark.skipif(os.getenv("PROVISION_WIKIBOOKS_AI_LIVE") != "1", reason="live DeepSeek call requires explicit opt-in")
def test_live_wikibooks_deepseek_adaptation(client, db, auth_user, auth_household, monkeypatch):
    _grant(db, auth_user, auth_household)
    source = _add_source(db, "en.wikibooks.org", access_mode="structured_recipe_fetch")
    source.policy = {**source.policy, "access_mode": "licensed_full", "extraction_methods": ["full_text"]}
    db.commit()
    monkeypatch.setattr(settings, "WIKIBOOKS_ENABLED", True)
    monkeypatch.setattr(settings, "DEEPSEEK_ENABLED", True)
    monkeypatch.setattr(settings, "DEEPSEEK_MAX_OUTPUT_TOKENS", 512)
    response = client.post("/api/v1/recipe-sources/wikibooks/adobo/adapt")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["proposal"]["steps"] and data["safety"] == "review_required"
    assert data["adapted"] is True and data["source"]["license_name"] == "CC BY-SA 4.0"
    assert db.scalar(select(func.count()).select_from(Recipe)) == 0
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0
    print({"model": data["model"], "usage": data["usage"]})
