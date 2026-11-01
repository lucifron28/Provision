from pathlib import Path
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.recipe_sources import get_publisher_transport
from app.main import app as fastapi_app
from app.models.privacy import ProcessingConsent
from app.models.recipe_source import RecipeSource
from app.models.user import User
from app.schemas.privacy import CONSENT_POLICY_VERSION
from app.schemas.recipe_source import SourceReviewInput
from app.services.deepseek_discovery import PageFetchResponse
from app.services.privacy import CONSENT_PURPOSE
from app.services.recipe_sources import write_source_review
from tests.test_recipe_extractor import SAMPLE_PANLASANG_HTML


REVIEWS_DIR = Path(__file__).resolve().parents[1] / "source_reviews"


class FakePublisherTransport:
    def __init__(self, responses: list[PageFetchResponse]):
        self.user_agent = "ProvisionBot/1.0 (operator@example.com)"
        self.responses = list(responses)
        self.requests: list[str] = []

    def resolve(self, hostname: str):
        return ["93.184.216.34"]

    def fetch_once_pinned(self, url: str, *, connect_ip: str, timeout_seconds: float, max_bytes: int):
        self.requests.append(url)
        if self.responses:
            return self.responses.pop(0)
        return PageFetchResponse(
            status_code=404,
            headers={"content-type": "text/plain"},
            body=b"Not found",
        )


def _grant(db, user: User, household) -> None:
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
def structured_panlasang_source(db):
    filepath = REVIEWS_DIR / "panlasang_pinoy.json"
    review = SourceReviewInput.model_validate_json(filepath.read_text(encoding="utf-8"))
    source = db.query(RecipeSource).filter(RecipeSource.canonical_host == review.canonical_host).first()
    review_dict = review.model_dump(mode="json")
    review_dict["expected_revision"] = source.revision if source else None
    review = SourceReviewInput.model_validate(review_dict)
    return write_source_review(db, review)


def test_preview_publisher_recipe_extracts_text_and_photo(
    client, db, auth_user, auth_household, structured_panlasang_source
):
    _grant(db, auth_user, auth_household)

    # 1st response: robots.txt
    robots_res = PageFetchResponse(
        status_code=200,
        headers={"content-type": "text/plain", "content-encoding": "identity"},
        body=b"User-agent: *\nAllow: /\n",
    )
    # 2nd response: recipe page HTML
    page_res = PageFetchResponse(
        status_code=200,
        headers={"content-type": "text/html", "content-encoding": "identity"},
        body=SAMPLE_PANLASANG_HTML.encode("utf-8"),
    )

    transport = FakePublisherTransport([robots_res, page_res])
    fastapi_app.dependency_overrides[get_publisher_transport] = lambda: transport

    try:
        res = client.post(
            "/api/v1/recipe-sources/preview",
            json={"url": "https://panlasangpinoy.com/pork-adobo/"},
        )
        assert res.status_code == 200
        data = res.json()

        assert data["title"] == "Classic Pork Adobo"
        assert data["publisher_name"] == "Panlasang Pinoy"
        assert data["source_tier"] == "filipino_priority"
        assert data["image_url"] == "https://panlasangpinoy.com/wp-content/uploads/2021/04/pork-adobo-1x1.jpg"
        assert data["author"] == "Vanjo Merano"
        assert len(data["ingredients"]) == 8
        assert "2 lbs pork belly sliced into cubes" in data["ingredients"]
        assert len(data["instructions"]) == 5
        assert data["servings"] == "4 servings"
        assert data["prep_time"] == "10m"
        assert data["cook_time"] == "45m"
        assert data["untrusted_content"] is True
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_transport, None)


def test_preview_publisher_recipe_requires_household_consent(
    client, db, auth_user, auth_household, structured_panlasang_source
):
    # No consent granted
    res = client.post(
        "/api/v1/recipe-sources/preview",
        json={"url": "https://panlasangpinoy.com/pork-adobo/"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "CURRENT_HOUSEHOLD_CONSENT_REQUIRED"


def test_preview_publisher_recipe_rejects_unapproved_domain(
    client, db, auth_user, auth_household, structured_panlasang_source
):
    _grant(db, auth_user, auth_household)

    res = client.post(
        "/api/v1/recipe-sources/preview",
        json={"url": "https://unapproved.example.com/recipe/adobo"},
    )
    assert res.status_code == 403
    assert res.json()["detail"] == "RECIPE_FETCH_NOT_AUTHORIZED"


def test_preview_publisher_recipe_fails_when_robots_denies(
    client, db, auth_user, auth_household, structured_panlasang_source
):
    _grant(db, auth_user, auth_household)

    # Robots disallows all
    robots_res = PageFetchResponse(
        status_code=200,
        headers={"content-type": "text/plain", "content-encoding": "identity"},
        body=b"User-agent: *\nDisallow: /\n",
    )
    transport = FakePublisherTransport([robots_res])
    fastapi_app.dependency_overrides[get_publisher_transport] = lambda: transport

    try:
        res = client.post(
            "/api/v1/recipe-sources/preview",
            json={"url": "https://panlasangpinoy.com/pork-adobo/"},
        )
        assert res.status_code == 403
        assert res.json()["detail"] == "RECIPE_FETCH_ROBOTS_DENIED"
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_transport, None)
