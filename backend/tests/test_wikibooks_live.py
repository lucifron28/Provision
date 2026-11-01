"""Opt-in, bounded smoke test for the openly licensed Wikibooks source."""

import os

import pytest

from app.services.pinned_page_transport import PinnedTLSTransport
from app.services.wikimedia_budget import PostgresWikimediaBudget
from app.services.wikimedia_transport import fetch_reviewed_wikibooks
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
