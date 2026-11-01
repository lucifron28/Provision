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


@pytest.fixture
def structured_kawaling_source(db):
    filepath = REVIEWS_DIR / "kawaling_pinoy.json"
    review = SourceReviewInput.model_validate_json(filepath.read_text(encoding="utf-8"))
    source = db.query(RecipeSource).filter(RecipeSource.canonical_host == review.canonical_host).first()
    review_dict = review.model_dump(mode="json")
    review_dict["expected_revision"] = source.revision if source else None
    review = SourceReviewInput.model_validate(review_dict)
    return write_source_review(db, review)


def test_preview_does_not_bypass_waf_block(
    client, db, auth_user, auth_household, authorized_wordpress
):
    _grant(db, auth_user, auth_household)
    robots = PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")
    waf = PageFetchResponse(403, {"content-type": "text/html"}, b"Cloudflare challenge")
    transport = FakePublisherTransport([robots, waf])
    fastapi_app.dependency_overrides[get_publisher_transport] = lambda: transport
    try:
        res = client.post(
            "/api/v1/recipe-sources/preview",
            json={"url": "https://www.kawalingpinoy.com/dinakdakan/"},
        )
        assert res.status_code == 502
        assert transport.requests == [
            "https://www.kawalingpinoy.com/robots.txt",
            "https://www.kawalingpinoy.com/dinakdakan/",
        ]
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_transport, None)

@pytest.fixture
def authorized_wordpress(db, structured_kawaling_source):
    source = db.get(RecipeSource, structured_kawaling_source.id)
    policy = dict(source.policy)
    policy["extraction_methods"] = ["json_ld", "api_json"]
    policy["wordpress_api_endpoint"] = "https://www.kawalingpinoy.com/wp-json/wp/v2/posts"
    source.policy = policy
    db.commit()
    return source


def _wp_responses(body=None, content_type="application/json"):
    import json
    robots = PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")
    missing = PageFetchResponse(404, {}, b"")
    if body is None:
        body = json.dumps([{
            "slug": "dinakdakan", "status": "publish",
            "link": "https://www.kawalingpinoy.com/dinakdakan/",
            "title": {"rendered": "Dinakdakan"},
            "content": {"rendered": '<li class="wprm-recipe-ingredient">Pork</li>'
                                      '<li class="wprm-recipe-instruction">Cook</li>'},
        }]).encode()
    return [robots, missing, robots, PageFetchResponse(200, {"content-type": content_type}, body)]


def _preview_with(client, transport):
    fastapi_app.dependency_overrides[get_publisher_transport] = lambda: transport
    try:
        return client.post("/api/v1/recipe-sources/preview", json={
            "url": "https://www.kawalingpinoy.com/dinakdakan/"})
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_transport, None)


def test_authorized_wordpress_fallback(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    transport = FakePublisherTransport(_wp_responses())
    response = _preview_with(client, transport)
    assert response.status_code == 200, response.text
    assert response.json()["source_url"] == "https://www.kawalingpinoy.com/dinakdakan/"
    assert response.json()["ingredients"] == ["Pork"]
    assert len(transport.requests) == 4
    assert transport.requests[-1].startswith("https://www.kawalingpinoy.com/wp-json/wp/v2/posts?")


def test_wordpress_robots_denial_stops_before_api(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    responses = _wp_responses()
    responses[2] = PageFetchResponse(200, {"content-type": "text/plain"},
        b"User-agent: *\nDisallow: /wp-json/\n")
    transport = FakePublisherTransport(responses)
    response = _preview_with(client, transport)
    assert response.status_code == 403
    assert response.json()["detail"] == "RECIPE_FETCH_ROBOTS_DENIED"
    assert len(transport.requests) == 3


@pytest.mark.parametrize("body,content_type,status", [
    (b"not json", "application/json", 502),
    (b"[]", "text/html", 415),
    (b"x" * 1000001, "application/json", 413),
    (b'[{"slug":"dinakdakan","status":"publish","link":"https://evil.com/dinakdakan/"}]', "application/json", 502),
    (b'[{"slug":"dinakdakan","slug":"other"}]', "application/json", 502),
], ids=["malformed", "content-type", "oversized", "wrong-publisher", "duplicate-key"])
def test_wordpress_rejects_invalid_responses(client, db, auth_user, auth_household, authorized_wordpress, body, content_type, status):
    _grant(db, auth_user, auth_household)
    response = _preview_with(client, FakePublisherTransport(_wp_responses(body, content_type)))
    assert response.status_code == status


def test_wordpress_rejects_redirect(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    responses = _wp_responses()
    responses[-1] = PageFetchResponse(302, {"location": "https://evil.com/private"}, b"")
    transport = FakePublisherTransport(responses)
    assert _preview_with(client, transport).status_code == 403
    assert len(transport.requests) == 4


def test_wordpress_requires_independent_authorization(client, db, auth_user, auth_household, structured_kawaling_source):
    _grant(db, auth_user, auth_household)
    transport = FakePublisherTransport(_wp_responses())
    assert _preview_with(client, transport).status_code == 404
    assert len(transport.requests) == 2

@pytest.mark.parametrize("bad_resolution", [1, 2, 3, 4])
def test_wordpress_rejects_private_or_rebound_dns(client, db, auth_user, auth_household, authorized_wordpress, bad_resolution):
    _grant(db, auth_user, auth_household)
    class RebindingTransport(FakePublisherTransport):
        def __init__(self):
            super().__init__(_wp_responses())
            self.resolutions = 0
        def resolve(self, hostname):
            self.resolutions += 1
            return ["127.0.0.1"] if self.resolutions == bad_resolution else ["93.184.216.34"]
    transport = RebindingTransport()
    response = _preview_with(client, transport)
    assert response.status_code in (403, 502, 503)
    assert len(transport.requests) < 4


def test_wordpress_timeout_fails_closed(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    class TimeoutTransport(FakePublisherTransport):
        def fetch_once_pinned(self, url, **kwargs):
            if "/wp-json/" in url:
                raise TimeoutError("timeout")
            return super().fetch_once_pinned(url, **kwargs)
    assert _preview_with(client, TimeoutTransport(_wp_responses())).status_code == 502


def test_wordpress_budget_exhaustion_prevents_api_request(client, db, auth_user, auth_household, authorized_wordpress):
    from app.api.v1.endpoints.recipe_sources import get_publisher_budget
    _grant(db, auth_user, auth_household)
    class Budget:
        calls = 0
        def consume(self):
            self.calls += 1
            if self.calls > 3:
                raise HTTPException(429, "PUBLISHER_REQUEST_BUDGET_EXHAUSTED")
    transport = FakePublisherTransport(_wp_responses())
    fastapi_app.dependency_overrides[get_publisher_budget] = Budget
    try:
        assert _preview_with(client, transport).status_code == 502
        assert len(transport.requests) == 3
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_budget, None)


def test_rejected_wordpress_does_not_modify_household_data(client, db, auth_user, auth_household, authorized_wordpress):
    from sqlalchemy import func, select
    from app.models import Recipe, InventoryBatch, ShoppingListItem
    _grant(db, auth_user, auth_household)
    product = client.post("/api/v1/products/", json={"name": "Rice", "unit": "kg"}).json()
    location = client.post("/api/v1/locations/", json={"name": "Pantry"}).json()
    batch = client.post("/api/v1/batches/", json={"product_id": product["id"],
        "storage_location_id": location["id"], "original_quantity": 2}).json()
    assert client.post("/api/v1/shopping-list/", json={"name": "Eggs", "quantity": 3}).status_code == 201
    recipe = client.post("/api/v1/recipes/", json={
        "title": "Rice", "cuisine": "Filipino", "ph_regions": ["region_unknown"],
        "content_permission": "OWNED_OR_PERMISSION_GRANTED", "course_categories": ["breakfast"],
        "dish_types": ["rice"], "servings": 2, "prep_minutes": 5, "cook_minutes": 10,
        "instructions": ["Cook rice."], "ingredients": [{"display_name": "bigas", "amount": 100, "unit": "g"}],
    })
    assert recipe.status_code == 201, recipe.text
    def snapshot():
        return (db.scalar(select(func.count()).select_from(Recipe)),
                db.scalar(select(func.count()).select_from(InventoryBatch)),
                db.scalar(select(func.count()).select_from(ShoppingListItem)),
                client.get(f"/api/v1/batches/{batch['id']}").json(),
                client.get("/api/v1/shopping-list/").json(),
                client.get(f"/api/v1/recipes/{recipe.json()['id']}").json())
    before = snapshot()
    assert _preview_with(client, FakePublisherTransport(_wp_responses(b"not json"))).status_code == 502
    db.expire_all()
    assert snapshot() == before

def test_publisher_budget_rejects_when_exhausted(client, db, auth_user, auth_household, authorized_wordpress):
    from datetime import datetime, timezone
    from app.models.publisher_budget import PublisherBudget
    _grant(db, auth_user, auth_household)
    db.add(PublisherBudget(id=1, used=1000, window_started=datetime.now(timezone.utc)))
    db.commit()
    transport = FakePublisherTransport(_wp_responses())
    assert _preview_with(client, transport).status_code == 503
    assert transport.requests == []


def test_challenge_on_404_does_not_trigger_wordpress(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    responses = _wp_responses()
    responses[1] = PageFetchResponse(404, {"content-type": "text/html"}, b"Cloudflare challenge")
    transport = FakePublisherTransport(responses)
    assert _preview_with(client, transport).status_code == 502
    assert len(transport.requests) == 2


def test_wordpress_rejects_changed_public_dns(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    class RebindingTransport(FakePublisherTransport):
        calls = 0
        def resolve(self, hostname):
            self.calls += 1
            return ["93.184.216.34"] if self.calls < 3 else ["8.8.8.8"]
    transport = RebindingTransport(_wp_responses())
    assert _preview_with(client, transport).status_code == 502
    assert len(transport.requests) == 2

def test_empty_404_with_challenge_header_does_not_trigger_wordpress(client, db, auth_user, auth_household, authorized_wordpress):
    _grant(db, auth_user, auth_household)
    responses = _wp_responses()
    responses[1] = PageFetchResponse(404, {"cf-mitigated": "challenge"}, b"")
    transport = FakePublisherTransport(responses)
    assert _preview_with(client, transport).status_code == 502
    assert len(transport.requests) == 2


def test_publisher_budget_serializes_concurrent_reservations(db):
    from concurrent.futures import ThreadPoolExecutor
    from datetime import datetime, timezone
    from app.models.publisher_budget import PublisherBudget
    from app.services.publisher_budget import PublisherRequestBudget

    db.add(PublisherBudget(id=1, used=999, window_started=datetime.now(timezone.utc)))
    db.commit()
    def reserve(_):
        try:
            PublisherRequestBudget().consume()
            return 200
        except HTTPException as exc:
            return exc.status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sorted(executor.map(reserve, range(2))) == [200, 429]
