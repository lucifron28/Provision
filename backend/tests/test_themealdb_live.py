"""One explicitly opted-in official TheMealDB discovery request."""

import os
from pathlib import Path

import pytest

from app.core.config import settings
from app.schemas.recipe_source import SourceReviewInput
from app.services.recipe_sources import write_source_review
from test_deepseek_discovery import _grant


@pytest.mark.skipif(os.getenv("PROVISION_MEALDB_LIVE_DISCOVERY") != "1", reason="live discovery requires explicit opt-in")
def test_live_filipino_listing_uses_reviewed_api_and_budget(client, db, auth_user, auth_household, monkeypatch):
    review_path = Path(__file__).resolve().parents[1] / "source_reviews" / "themealdb_educational.json"
    review = SourceReviewInput.model_validate_json(review_path.read_text(encoding="utf-8"))
    write_source_review(db, review)
    _grant(db, auth_user, auth_household)
    db.commit()
    monkeypatch.setattr(settings, "MEALDB_ENABLED", True)
    response = client.post("/api/v1/recipe-sources/mealdb/discover", json={"query": "adobo", "max_results": 2})
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items and all(item["original_source"] == "not_yet_reviewed" for item in items)
    print("TheMealDB Filipino matches:", ", ".join(item["title"] for item in items))
