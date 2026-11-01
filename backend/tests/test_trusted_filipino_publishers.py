from pathlib import Path
import pytest
from fastapi import HTTPException

from app.models.household import Household
from app.models.privacy import ProcessingConsent
from app.models.recipe_source import RecipeSource
from app.models.user import User
from app.schemas.privacy import CONSENT_POLICY_VERSION
from app.schemas.recipe_source import SourcePolicy, SourceReviewInput
from app.services.privacy import CONSENT_PURPOSE
from app.schemas.deepseek import (
    DeepSeekSearchRequest,
    DeepSeekSearchResponse,
    DeepSeekSearchResult,
)
from app.services.deepseek_discovery import (
    ProviderSearchHit,
    authorize_recipe_fetch,
    discover_recipes,
)
from app.services.recipe_sources import (
    discovery_plan,
    reference_policy,
    source_approved,
    write_source_review,
)


REVIEWS_DIR = Path(__file__).resolve().parents[1] / "source_reviews"

FILIPINO_PUBLISHER_FILES = [
    "panlasang_pinoy.json",
    "kawaling_pinoy.json",
    "yummy_ph.json",
    "ang_sarap.json",
]


class FakeSearchProvider:
    def __init__(self, mapping: dict[str, list[DeepSeekSearchResult]]):
        self._mapping = mapping
        self.max_search_results = 10
        self.calls: list[DeepSeekSearchRequest] = []

    def search(self, request: DeepSeekSearchRequest) -> DeepSeekSearchResponse:
        self.calls.append(request)
        for key, results in self._mapping.items():
            if key in request.query:
                return DeepSeekSearchResponse(results=results)
        return DeepSeekSearchResponse(results=[])


def _grant(db, user: User, household: Household) -> None:
    db.add(
        ProcessingConsent(
            household_id=household.id,
            user_id=user.id,
            purpose=CONSENT_PURPOSE,
            policy_version=CONSENT_POLICY_VERSION,
            granted=True,
        )
    )
    db.flush()


@pytest.fixture
def approved_filipino_publishers(db):
    """Ensure all 4 Filipino publishers are approved in the test database."""
    applied = []
    for filename in FILIPINO_PUBLISHER_FILES:
        filepath = REVIEWS_DIR / filename
        assert filepath.exists(), f"Review file {filename} missing"
        review = SourceReviewInput.model_validate_json(filepath.read_text(encoding="utf-8"))
        # In test schema, check current revision of existing source or set expected_revision
        current = db.query(RecipeSource).filter(RecipeSource.canonical_host == review.canonical_host).first()
        review_dict = review.model_dump(mode="json")
        review_dict["expected_revision"] = current.revision if current else None
        review = SourceReviewInput.model_validate(review_dict)
        applied.append(write_source_review(db, review))
    return applied


def test_review_files_validate_against_schema():
    """Verify that all 4 review JSON files meet SourceReviewInput schema rules."""
    for filename in FILIPINO_PUBLISHER_FILES:
        filepath = REVIEWS_DIR / filename
        assert filepath.exists()
        raw_text = filepath.read_text(encoding="utf-8")
        review = SourceReviewInput.model_validate_json(raw_text)

        assert review.policy.review_status == "approved"
        assert review.policy.tier == "filipino_priority"
        assert review.policy.enabled is True
        assert review.policy.access_mode == "search_link_only"
        assert review.policy.extraction_methods == []
        assert "Filipino" in review.policy.cuisine_tags
        assert review.canonical_host in review.policy.allowed_hosts
        assert review.policy.terms_reference is not None
        assert review.policy.terms_reviewed_at is not None
        assert review.policy.last_audited_at is not None
        assert review.policy.review_expires_at is not None
        assert review.policy.review_expires_at > review.policy.last_audited_at
        assert review.policy.disabled_reason is None


def test_approved_filipino_publishers_active_in_registry(db, approved_filipino_publishers):
    """Verify that approved publishers have currently_approved True and filipino_priority tier."""
    for source_read in approved_filipino_publishers:
        assert source_read.review_status == "approved"
        assert source_read.tier == "filipino_priority"
        assert source_read.access_mode == "search_link_only"
        assert source_read.currently_approved is True
        assert source_read.live_fetch_enabled is False

        # Verify DB model
        source = db.get(RecipeSource, source_read.id)
        assert source is not None
        assert source_approved(source) is True


def test_discovery_plan_prioritizes_approved_filipino_publishers(db, approved_filipino_publishers):
    """Verify that discovery_plan generates site: queries for all approved Filipino publishers."""
    plan = discovery_plan(db, "sinigang na baboy")

    priority_queries = plan["priority_queries"]
    assert len(priority_queries) >= 4

    query_text = " ".join(priority_queries)
    assert "site:panlasangpinoy.com" in query_text
    assert "site:www.kawalingpinoy.com" in query_text
    assert "site:www.yummy.ph" in query_text
    assert "site:www.angsarap.net" in query_text

    # Broader query is None by default
    assert plan["broader_query"] is None
    assert plan["provider_enabled"] is False
    assert plan["fetch_enabled"] is False
    assert plan["executed"] is False


def test_reference_policy_accepts_approved_filipino_publishers_without_broader_web(
    db, approved_filipino_publishers
):
    """Verify that references to approved Filipino publishers are allowed and labeled."""
    urls = [
        "https://panlasangpinoy.com/pork-sinigang-recipe/",
        "https://www.panlasangpinoy.com/pork-sinigang-recipe/",
        "https://www.kawalingpinoy.com/sinigang-na-baboy/",
        "https://kawalingpinoy.com/sinigang-na-baboy/",
        "https://www.yummy.ph/recipe/classic-pork-sinigang-recipe",
        "https://yummy.ph/recipe/classic-pork-sinigang-recipe",
        "https://www.angsarap.net/2012/03/19/sinigang-na-baboy/",
        "https://angsarap.net/2012/03/19/sinigang-na-baboy/",
    ]

    for url in urls:
        source, allowed, label = reference_policy(db, url, broader_permission=False)
        assert source is not None, f"Source missing for {url}"
        assert allowed is True, f"Reference disallowed for {url}"
        assert label == "Reference to reviewed Filipino publisher", f"Wrong label for {url}: {label}"


def test_discover_recipes_tags_filipino_priority_tier(
    db, auth_household, auth_user, approved_filipino_publishers
):
    """Verify that search hits from approved Filipino publishers receive filipino_priority tier."""
    provider = FakeSearchProvider(
        {
            "site:panlasangpinoy.com": [
                DeepSeekSearchResult(
                    rerank_score=2.0,
                    title="Pork Adobo Recipe",
                    url="https://panlasangpinoy.com/pork-adobo/",
                    snippet="Authentic Filipino pork adobo with soy sauce and vinegar.",
                    summary="Summary not returned",
                    content="",
                    site_name="Panlasang Pinoy",
                    site_icon=None,
                    date=None,
                    authority=2,
                )
            ],
            "site:www.kawalingpinoy.com": [
                DeepSeekSearchResult(
                    rerank_score=2.0,
                    title="Classic Chicken Adobo",
                    url="https://www.kawalingpinoy.com/chicken-adobo/",
                    snippet="Savory, tangy chicken adobo.",
                    summary="Summary not returned",
                    content="",
                    site_name="Kawaling Pinoy",
                    site_icon=None,
                    date=None,
                    authority=2,
                )
            ],
        }
    )

    _grant(db, auth_user, auth_household)
    response = discover_recipes(
        db,
        auth_household.id,
        auth_user.id,
        "adobo",
        provider=provider,
        max_results=5,
    )

    assert len(response.results) >= 2
    for result in response.results:
        assert result.source_tier == "filipino_priority"
        assert result.untrusted_content is True
        assert result.canonical_url.startswith(
            ("https://panlasangpinoy.com/", "https://www.kawalingpinoy.com/")
        )

    assert response.fetch_performed is False


def test_authorize_recipe_fetch_fails_closed_for_search_link_only_publishers(
    db, approved_filipino_publishers
):
    """Verify that fetch authorization fails closed for search_link_only sources."""
    urls = [
        "https://panlasangpinoy.com/pork-sinigang-recipe/",
        "https://www.kawalingpinoy.com/sinigang-na-baboy/",
        "https://www.yummy.ph/recipe/classic-pork-sinigang-recipe",
        "https://www.angsarap.net/2012/03/19/sinigang-na-baboy/",
    ]

    for url in urls:
        with pytest.raises(HTTPException) as exc_info:
            authorize_recipe_fetch(db, url)
        assert exc_info.value.status_code == 403
        assert exc_info.value.detail == "RECIPE_FETCH_NOT_AUTHORIZED"
