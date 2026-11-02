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
    from app.models.publisher_budget import PublisherBudget, PublisherPacing
    _grant(db, auth_user, auth_household)
    transport = FakePublisherTransport(_wp_responses())
    response = _preview_with(client, transport)
    assert response.status_code == 200, response.text
    assert response.json()["source_url"] == "https://www.kawalingpinoy.com/dinakdakan/"
    assert response.json()["ingredients"] == ["Pork"]
    assert len(transport.requests) == 4
    assert transport.requests[-1].startswith("https://www.kawalingpinoy.com/wp-json/wp/v2/posts?")
    db.expire_all()
    assert db.get(PublisherBudget, 1).used == 4
    assert db.get(PublisherPacing, authorized_wordpress.id).window_used == 4


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
    assert _preview_with(client, TimeoutTransport(_wp_responses())).status_code == 504


def test_wordpress_budget_exhaustion_prevents_api_request(client, db, auth_user, auth_household, authorized_wordpress):
    from app.api.v1.endpoints.recipe_sources import get_publisher_budget
    from app.services.publisher_budget import PublisherRequestError
    from contextlib import contextmanager
    _grant(db, auth_user, auth_household)
    class Budget:
        calls = 0
        @contextmanager
        def request(self, source_id, canonical_host):
            self.calls += 1
            if self.calls > 3:
                raise PublisherRequestError(429, "PUBLISHER_REQUEST_BUDGET_EXHAUSTED")
            yield lambda response: None
    transport = FakePublisherTransport(_wp_responses())
    fastapi_app.dependency_overrides[get_publisher_budget] = Budget
    try:
        assert _preview_with(client, transport).status_code == 429
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
    assert _preview_with(client, transport).status_code == 429
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


def test_per_publisher_pacing_serializes_concurrent_workers(db, structured_kawaling_source):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError

    entered, release = Event(), Event()
    source_id = structured_kawaling_source.id
    host = "www.kawalingpinoy.com"
    def first():
        with PublisherRequestBudget().request(source_id, host) as record:
            entered.set()
            assert release.wait(5)
            record(PageFetchResponse(200, {}, b""))
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(first)
        assert entered.wait(5)
        try:
            with pytest.raises(PublisherRequestError) as error:
                with PublisherRequestBudget().request(source_id, host):
                    pytest.fail("Concurrent request must not start")
            assert error.value.status_code == 429
        finally:
            release.set()
        pending.result()


def test_publisher_short_window_limit_counts_every_request(db, structured_kawaling_source, monkeypatch):
    from app.core.config import settings, PublisherPacingSettings
    from app.models.publisher_budget import PublisherBudget, PublisherPacing
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    monkeypatch.setattr(settings, "PUBLISHER_PACING_DEFAULT", PublisherPacingSettings(
        min_interval_seconds=0.001, window_seconds=60, window_requests=2))
    source_id = structured_kawaling_source.id
    budget = PublisherRequestBudget()
    for _ in range(2):
        with budget.request(source_id, "www.kawalingpinoy.com") as record:
            record(PageFetchResponse(200, {}, b""))
    with pytest.raises(PublisherRequestError) as error:
        with budget.request(source_id, "www.kawalingpinoy.com"):
            pytest.fail("Rate-limited request must not start")
    assert error.value.status_code == 429
    db.expire_all()
    assert db.get(PublisherBudget, 1).used == 2
    assert db.get(PublisherPacing, source_id).window_used == 2


@pytest.mark.parametrize("retry_after,minimum", [("3", 2), ("invalid", 59), ("999999", 3599)])
def test_publisher_retry_after_cooldown_is_durable_and_bounded(db, structured_kawaling_source, retry_after, minimum):
    from datetime import datetime, timezone
    from app.models.publisher_budget import PublisherPacing
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    source_id = structured_kawaling_source.id
    with pytest.raises(PublisherRequestError) as error:
        with PublisherRequestBudget().request(source_id, "www.kawalingpinoy.com") as record:
            record(PageFetchResponse(429, {"retry-after": retry_after}, b""))
    assert error.value.status_code == 429
    db.expire_all()
    row = db.get(PublisherPacing, source_id)
    remaining = (row.next_allowed - datetime.now(timezone.utc)).total_seconds()
    assert minimum <= remaining <= 3600
    assert row.paused is False
    with pytest.raises(PublisherRequestError) as blocked:
        with PublisherRequestBudget().request(source_id, "www.kawalingpinoy.com"):
            pytest.fail("Cooldown must prevent an outbound request")
    assert blocked.value.status_code == 429


def test_publisher_budget_database_unavailable_fails_closed(monkeypatch):
    from app.core import database
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    class BrokenEngine:
        def connect(self):
            raise RuntimeError("private database information")
    with monkeypatch.context() as patch:
        patch.setattr(database, "engine", BrokenEngine())
        with pytest.raises(PublisherRequestError) as error:
            with PublisherRequestBudget().request(1, "example.com"):
                pytest.fail("Unavailable budget must prevent an outbound request")
    assert error.value.status_code == 503
    assert error.value.detail == "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE"


def test_robots_timeout_is_504_without_leaking_error(client, db, auth_user, auth_household, structured_kawaling_source):
    _grant(db, auth_user, auth_household)
    class TimeoutTransport(FakePublisherTransport):
        def fetch_once_pinned(self, url, **kwargs):
            raise TimeoutError("private socket details")
    response = _preview_with(client, TimeoutTransport([]))
    assert response.status_code == 504
    assert response.json()["detail"] == "PUBLISHER_REQUEST_TIMEOUT"


def test_upstream_robots_rate_limit_blocks_subsequent_requests(client, db, auth_user, auth_household, structured_kawaling_source):
    _grant(db, auth_user, auth_household)
    transport = FakePublisherTransport([
        PageFetchResponse(429, {"retry-after": "30"}, b"limited"),
    ])
    first = _preview_with(client, transport)
    assert first.status_code == 429
    assert first.json()["detail"] == "PUBLISHER_UPSTREAM_RATE_LIMITED"
    assert first.headers["retry-after"] == "30"
    second = _preview_with(client, transport)
    assert second.status_code == 429
    assert len(transport.requests) == 1


def test_publisher_override_applies_to_its_source_only(db, structured_kawaling_source, structured_panlasang_source, monkeypatch):
    from app.core.config import settings, PublisherPacingSettings
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    monkeypatch.setattr(settings, "PUBLISHER_PACING_DEFAULT", PublisherPacingSettings(
        min_interval_seconds=0.001, window_seconds=60, window_requests=2))
    monkeypatch.setattr(settings, "PUBLISHER_PACING_OVERRIDES", {
        "www.kawalingpinoy.com": PublisherPacingSettings(min_interval_seconds=0.001, window_seconds=60, window_requests=1),
    })
    budget = PublisherRequestBudget()
    kawaling = (structured_kawaling_source.id, "www.kawalingpinoy.com")
    panlasang = (structured_panlasang_source.id, "panlasangpinoy.com")
    for source in (kawaling, panlasang, panlasang):
        with budget.request(*source) as record:
            record(PageFetchResponse(200, {}, b""))
    with pytest.raises(PublisherRequestError) as error:
        with budget.request(*kawaling):
            pytest.fail("Publisher override must limit this publisher")
    assert error.value.status_code == 429


def test_minimum_interval_rejects_early_request_then_allows_retry(db, structured_kawaling_source, monkeypatch):
    from datetime import datetime, timedelta, timezone
    from app.core.config import settings, PublisherPacingSettings
    from app.models.publisher_budget import PublisherPacing
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    monkeypatch.setattr(settings, "PUBLISHER_PACING_DEFAULT", PublisherPacingSettings(
        min_interval_seconds=30, window_seconds=60, window_requests=10))
    source_id = structured_kawaling_source.id
    budget = PublisherRequestBudget()
    with budget.request(source_id, "www.kawalingpinoy.com") as record:
        record(PageFetchResponse(200, {}, b""))
    with pytest.raises(PublisherRequestError) as error:
        with budget.request(source_id, "www.kawalingpinoy.com"):
            pytest.fail("Early request must not start")
    assert error.value.status_code == 429
    assert int(error.value.headers["Retry-After"]) >= 28
    db.expire_all()
    row = db.get(PublisherPacing, source_id)
    row.next_allowed = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    with PublisherRequestBudget().request(source_id, "www.kawalingpinoy.com") as record:
        record(PageFetchResponse(200, {}, b""))


def test_retry_after_http_date_sets_cooldown(db, structured_kawaling_source):
    from datetime import datetime, timedelta, timezone
    from email.utils import format_datetime
    from app.models.publisher_budget import PublisherPacing
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    source_id = structured_kawaling_source.id
    header = format_datetime(datetime.now(timezone.utc) + timedelta(seconds=40), usegmt=True)
    with pytest.raises(PublisherRequestError) as error:
        with PublisherRequestBudget().request(source_id, "www.kawalingpinoy.com") as record:
            record(PageFetchResponse(503, {"Retry-After": header}, b""))
    assert error.value.status_code == 503
    assert int(error.value.headers["Retry-After"]) >= 38
    db.expire_all()
    assert (db.get(PublisherPacing, source_id).next_allowed - datetime.now(timezone.utc)).total_seconds() >= 38


def test_paused_publisher_fails_closed_after_restart(db, structured_kawaling_source):
    from datetime import datetime, timezone
    from app.models.publisher_budget import PublisherBudget, PublisherPacing
    from app.services.publisher_budget import PublisherRequestBudget, PublisherRequestError
    now = datetime.now(timezone.utc)
    db.add(PublisherPacing(source_id=structured_kawaling_source.id, window_started=now,
        window_used=1, next_allowed=now, paused=True))
    db.commit()
    with pytest.raises(PublisherRequestError) as error:
        with PublisherRequestBudget().request(structured_kawaling_source.id, "www.kawalingpinoy.com"):
            pytest.fail("Paused publisher must not send requests")
    assert error.value.status_code == 503
    assert db.get(PublisherBudget, 1) is None


def test_budget_failure_response_is_sanitized_and_sends_nothing(client, db, auth_user, auth_household, structured_kawaling_source):
    from contextlib import contextmanager
    from app.api.v1.endpoints.recipe_sources import get_publisher_budget
    from app.services.publisher_budget import PublisherRequestError
    _grant(db, auth_user, auth_household)
    class Unavailable:
        @contextmanager
        def request(self, source_id, canonical_host):
            raise PublisherRequestError(503, "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE")
            yield
    transport = FakePublisherTransport(_wp_responses())
    fastapi_app.dependency_overrides[get_publisher_budget] = Unavailable
    try:
        response = _preview_with(client, transport)
        assert response.status_code == 503
        assert response.json()["detail"] == "PUBLISHER_REQUEST_BUDGET_UNAVAILABLE"
        assert transport.requests == []
    finally:
        fastapi_app.dependency_overrides.pop(get_publisher_budget, None)


def test_redirect_retry_after_delays_following_robots_request(client, db, auth_user, auth_household, structured_kawaling_source):
    from app.models.publisher_budget import PublisherBudget
    _grant(db, auth_user, auth_household)
    robots = PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")
    redirect = PageFetchResponse(302, {"location": "/another-recipe/", "retry-after": "30"}, b"")
    transport = FakePublisherTransport([robots, redirect, robots])
    response = _preview_with(client, transport)
    assert response.status_code == 429
    assert int(response.headers["retry-after"]) >= 28
    assert len(transport.requests) == 2
    db.expire_all()
    assert db.get(PublisherBudget, 1).used == 2


def test_timeout_sets_cooldown_and_allows_retry_after_expiry(client, db, auth_user, auth_household, structured_kawaling_source):
    from datetime import datetime, timedelta, timezone
    from app.models.publisher_budget import PublisherPacing
    _grant(db, auth_user, auth_household)
    class TimeoutTransport(FakePublisherTransport):
        def fetch_once_pinned(self, url, **kwargs):
            self.requests.append(url)
            raise TimeoutError("timeout")
    transport = TimeoutTransport([])
    assert _preview_with(client, transport).status_code == 504
    db.expire_all()
    state = db.get(PublisherPacing, structured_kawaling_source.id)
    assert (state.next_allowed - datetime.now(timezone.utc)).total_seconds() > 50
    assert _preview_with(client, transport).status_code == 429
    assert len(transport.requests) == 1
    state.next_allowed = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    robots = PageFetchResponse(200, {"content-type": "text/plain"}, b"User-agent: *\nAllow: /\n")
    page = PageFetchResponse(200, {"content-type": "text/html"}, SAMPLE_PANLASANG_HTML.encode())
    assert _preview_with(client, FakePublisherTransport([robots, page])).status_code == 200
