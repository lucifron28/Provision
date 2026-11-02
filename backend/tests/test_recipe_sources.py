from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
import json
from threading import Barrier

from fastapi import HTTPException
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

import scripts.review_recipe_source as review_cli
from app.models.recipe import Recipe
from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.schemas.recipe_source import SourcePolicy, SourceReferenceInput, SourceReviewInput
from app.services.recipe_sources import remove_reference, write_reference, write_source_review
from test_food_safety import catalog, declare


def _policy(
    hosts: list[str],
    *,
    status: str = "candidate",
    tier: str = "filipino_priority",
    expires_at: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = dict(
        review_status=status,
        tier=tier,
        enabled=status == "approved",
        allowed_hosts=hosts,
        allowed_redirect_hosts=[],
        access_mode="search_link_only",
        extraction_methods=[],
        cuisine_tags=["Filipino"],
        disabled_reason=None if status == "approved" else "Synthetic fixture only",
    )
    if status == "approved":
        payload.update(
            terms_reference="Synthetic terms review for tests",
            terms_reviewed_at=(now - timedelta(days=2)).isoformat(),
            last_audited_at=(now - timedelta(days=1)).isoformat(),
            review_expires_at=(expires_at or now + timedelta(days=30)).isoformat(),
        )
    return payload


def _review(db, host: str, policy: dict, *, expected_revision: int | None = None):
    request = SourceReviewInput(
        expected_revision=expected_revision,
        canonical_host=host,
        publisher_name="Synthetic example source",
        reviewed_by="Test maintainer",
        policy=policy,
    )
    return write_source_review(db, request)


def _recipe_payload(title: str, ingredient: str = "rice", unit: str = "g") -> dict:
    return dict(
        title=title,
        cuisine="Filipino",
        content_permission="OWNED_OR_PERMISSION_GRANTED",
        ph_regions=["region_unknown"],
        servings=2,
        prep_minutes=5,
        cook_minutes=10,
        instructions=["Prepare the measured ingredients."],
        ingredients=[dict(display_name=ingredient, amount="10", unit=unit)],
    )


def _create_recipe(client, title: str, ingredient: str = "rice", unit: str = "g") -> dict:
    response = client.post("/api/v1/recipes/", json=_recipe_payload(title, ingredient, unit))
    assert response.status_code == 201, response.text
    return response.json()


def _link_reference(client, recipe_id: int, url: str, *, broader: bool = False, revision=None):
    return client.put(
        f"/api/v1/recipe-sources/recipes/{recipe_id}/reference",
        json=dict(
            expected_revision=revision,
            expected_recipe_revision=1,
            url=url,
            author="Synthetic test author",
            allow_broader_web=broader,
        ),
    )


def _run_cli(monkeypatch, db, path):
    class ReusedSession:
        def __enter__(self):
            return db

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr(review_cli, "SessionLocal", lambda: ReusedSession())
    monkeypatch.setattr("sys.argv", ["review_recipe_source.py", str(path)])
    review_cli.main()


def test_recipe_source_http_requires_authentication(unauthed_client):
    assert unauthed_client.get("/api/v1/recipe-sources/").status_code == 401
    assert unauthed_client.post(
        "/api/v1/recipe-sources/discovery-plan", json={"query": "adobo"}
    ).status_code == 401


def test_registry_http_is_read_only_and_candidates_stay_unapproved(client, db):
    host = "candidate.synthetic.example.com"
    created = _review(db, host, _policy([host]))
    before_reviews = db.scalar(select(func.count()).select_from(RecipeSourceReview))

    listed = client.get("/api/v1/recipe-sources/")
    assert listed.status_code == 200
    assert listed.headers["cache-control"] == "no-store"
    record = next(item for item in listed.json() if item["id"] == created.id)
    assert record["review_status"] == "candidate"
    assert record["currently_approved"] is False
    assert record["live_fetch_enabled"] is False

    plan = client.post(
        "/api/v1/recipe-sources/discovery-plan",
        json={"query": "sinigang"},
    )
    assert plan.status_code == 200
    assert host not in str(plan.json())
    assert plan.json()["provider_enabled"] is False
    assert plan.json()["fetch_enabled"] is False
    assert plan.json()["executed"] is False
    assert plan.json()["results"] == []
    assert plan.json()["broader_query"] is None

    assert client.post("/api/v1/recipe-sources/reviews", json={}).status_code == 404
    assert db.scalar(select(func.count()).select_from(RecipeSourceReview)) == before_reviews


def test_discovery_requires_explicit_broad_web_opt_in_and_never_calls_provider(client, db):
    filipino_host = "priority.synthetic.example.com"
    general_host = "general.synthetic.example.com"
    _review(db, filipino_host, _policy([filipino_host], status="approved"))
    _review(
        db,
        general_host,
        _policy([general_host], status="approved", tier="reviewed_general"),
    )

    default = client.post("/api/v1/recipe-sources/discovery-plan", json={"query": "adobo"})
    assert default.status_code == 200
    default_plan = default.json()
    assert [f"site:{filipino_host}" in query for query in default_plan["priority_queries"]] == [True]
    assert default_plan["general_queries"] == []
    assert default_plan["broader_query"] is None

    opted_in = client.post(
        "/api/v1/recipe-sources/discovery-plan",
        json={"query": "adobo", "allow_broader_web": True, "include_reviewed_general": True},
    )
    assert opted_in.status_code == 200
    plan = opted_in.json()
    assert plan["priority_queries"]
    assert plan["general_queries"]
    assert f"site:{filipino_host}" in plan["priority_queries"][0]
    assert f"site:{general_host}" in plan["general_queries"][0]
    assert plan["broader_query"] == '"adobo" recipe'
    assert plan["provider_enabled"] is False and plan["fetch_enabled"] is False
    assert plan["executed"] is False and plan["results"] == []


def test_cli_records_synthetic_maintainer_review_and_enforces_revision(
    tmp_path, monkeypatch, db, capsys
):
    host = "review.synthetic.example.com"
    candidate = dict(
        canonical_host=host,
        publisher_name="Synthetic example source",
        reviewed_by="Test maintainer",
        expected_revision=None,
        policy=_policy([host]),
    )
    review_file = tmp_path / "candidate-review.json"
    review_file.write_text(json.dumps(candidate), encoding="utf-8")
    _run_cli(monkeypatch, db, review_file)
    assert "revision 1: candidate" in capsys.readouterr().out

    source = db.scalar(select(RecipeSource).where(RecipeSource.canonical_host == host))
    assert source is not None and source.revision == 1
    assert db.scalar(
        select(func.count()).select_from(RecipeSourceReview).where(RecipeSourceReview.source_id == source.id)
    ) == 1

    approval = {
        **candidate,
        "expected_revision": 1,
        "policy": _policy([host], status="approved"),
    }
    approval["policy"]["terms_reference"] = "PRIVATE_PERMISSION_DOCUMENT_SENTINEL"
    review_file.write_text(json.dumps(approval), encoding="utf-8")
    _run_cli(monkeypatch, db, review_file)
    assert "revision 2: approved" in capsys.readouterr().out
    db.refresh(source)
    assert source.revision == 2
    assert SourcePolicy.model_validate(source.policy).review_status == "approved"

    review_file.write_text(json.dumps(approval), encoding="utf-8")
    with pytest.raises(SystemExit) as conflict:
        _run_cli(monkeypatch, db, review_file)
    assert conflict.value.code == 2
    error_text = capsys.readouterr().err
    assert "current revision" in error_text
    assert "PRIVATE_PERMISSION_DOCUMENT_SENTINEL" not in error_text
    db.refresh(source)
    assert source.revision == 2


def test_cli_rejects_approval_without_current_terms_and_audit_evidence(
    tmp_path, monkeypatch, db, capsys
):
    host = "incomplete.synthetic.example.com"
    request = dict(
        canonical_host=host,
        publisher_name="Synthetic example source",
        reviewed_by="Test maintainer",
        expected_revision=None,
        policy=dict(
            review_status="approved",
            tier="filipino_priority",
            enabled=True,
            allowed_hosts=[host],
            access_mode="search_link_only",
            terms_reference="PRIVATE_PERMISSION_DOCUMENT_SENTINEL",
        ),
    )
    review_file = tmp_path / "incomplete-review.json"
    review_file.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        _run_cli(monkeypatch, db, review_file)
    assert error.value.code == 2
    error_text = capsys.readouterr().err
    assert "Review fields are missing or invalid" in error_text
    assert "PRIVATE_PERMISSION_DOCUMENT_SENTINEL" not in error_text
    assert db.scalar(select(func.count()).select_from(RecipeSource)) == 0
    assert db.scalar(select(func.count()).select_from(RecipeSourceReview)) == 0


@pytest.mark.parametrize("target_kind", ["missing", "directory"])
def test_cli_reports_missing_or_unreadable_review_file(tmp_path, monkeypatch, capsys, target_kind):
    review_file = tmp_path / "missing-review.json" if target_kind == "missing" else tmp_path
    monkeypatch.setattr("sys.argv", ["review_recipe_source.py", str(review_file)])
    with pytest.raises(SystemExit) as error:
        review_cli.main()
    assert error.value.code == 2
    error_text = capsys.readouterr().err
    expected = "does not exist" if target_kind == "missing" else "could not be read"
    assert expected in error_text
    assert str(review_file) not in error_text


def test_cli_reports_invalid_json_without_echoing_contents(tmp_path, monkeypatch, capsys):
    review_file = tmp_path / "invalid-review.json"
    review_file.write_text('{"permission": "PRIVATE_PERMISSION_DOCUMENT_SENTINEL",', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["review_recipe_source.py", str(review_file)])
    with pytest.raises(SystemExit) as error:
        review_cli.main()
    assert error.value.code == 2
    error_text = capsys.readouterr().err
    assert "not valid JSON" in error_text
    assert "PRIVATE_PERMISSION_DOCUMENT_SENTINEL" not in error_text


def test_cli_rejects_oversized_review_file_without_echoing_contents(tmp_path, monkeypatch, capsys):
    review_file = tmp_path / "oversized-review.json"
    review_file.write_bytes(b"PRIVATE_PERMISSION_DOCUMENT_SENTINEL" * 3000)
    monkeypatch.setattr("sys.argv", ["review_recipe_source.py", str(review_file)])
    with pytest.raises(SystemExit) as error:
        review_cli.main()
    assert error.value.code == 2
    error_text = capsys.readouterr().err
    assert "64 KiB" in error_text
    assert "PRIVATE_PERMISSION_DOCUMENT_SENTINEL" not in error_text


def test_cli_reports_expired_policy_rejection_without_private_evidence(tmp_path, monkeypatch, db, capsys):
    host = "expired-review.synthetic.example.com"
    request = dict(
        canonical_host=host,
        publisher_name="Synthetic example source",
        reviewed_by="Test maintainer",
        expected_revision=None,
        policy=_policy(
            [host],
            status="approved",
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        ),
    )
    request["policy"]["terms_reference"] = "PRIVATE_PERMISSION_DOCUMENT_SENTINEL"
    review_file = tmp_path / "expired-review.json"
    review_file.write_text(json.dumps(request), encoding="utf-8")
    with pytest.raises(SystemExit) as error:
        _run_cli(monkeypatch, db, review_file)
    assert error.value.code == 2
    error_text = capsys.readouterr().err
    assert "policy or evidence was rejected" in error_text
    assert "PRIVATE_PERMISSION_DOCUMENT_SENTINEL" not in error_text
    assert db.scalar(select(func.count()).select_from(RecipeSource)) == 0


def test_broader_web_reference_requires_explicit_user_choice_and_is_a_tombstone(client, db):
    recipe = _create_recipe(client, "Synthetic link-only recipe")
    url = "https://other.synthetic.example.com/recipes/adobo"
    denied = _link_reference(client, recipe["id"], url)
    assert denied.status_code == 409

    linked = _link_reference(client, recipe["id"], url, broader=True)
    assert linked.status_code == 200, linked.text
    assert linked.headers["cache-control"] == "no-store"
    reference = linked.json()
    assert reference["revision"] == 1
    assert reference["currently_allowed"] is True
    assert reference["source_label"] == "Other website, verify details"
    assert reference["copied_publisher_content"] is False
    assert reference["live_fetch_enabled"] is False
    assert db.scalar(select(func.count()).select_from(RecipeSourceReference)) == 1

    read = client.get(f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference")
    assert read.status_code == 200 and read.headers["cache-control"] == "no-store"
    removed = client.delete(
        f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference?expected_revision=1"
    )
    assert removed.status_code == 204
    tombstone = client.get(f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference").json()
    assert tombstone["revision"] == 2
    assert tombstone["is_active"] is False
    assert tombstone["currently_allowed"] is False
    assert tombstone["source_label"] == "Inactive reference"
    assert client.delete(
        f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference?expected_revision=1"
    ).status_code == 409

    relink = _link_reference(client, recipe["id"], url, broader=True, revision=2)
    assert relink.status_code == 200
    assert relink.json()["revision"] == 3 and relink.json()["is_active"] is True


@pytest.mark.parametrize("status", ["suspended", "rejected"])
def test_suspended_or_rejected_source_cannot_use_broader_opt_in(client, db, status):
    host = f"{status}.synthetic.example.com"
    approved = _review(db, host, _policy([host], status="approved"))
    recipe = _create_recipe(client, f"{status} synthetic recipe")
    linked = _link_reference(
        client, recipe["id"], f"https://{host}/recipes/dish", broader=True
    )
    assert linked.status_code == 200

    _review(db, host, _policy([host], status=status), expected_revision=approved.revision)
    response = client.get(f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference")
    assert response.status_code == 200
    assert response.json()["currently_allowed"] is False
    assert response.json()["source_label"] == "Unavailable reference"
    retry = _link_reference(
        client,
        recipe["id"],
        f"https://{host}/recipes/dish",
        broader=True,
        revision=1,
    )
    assert retry.status_code == 409


def test_expired_approved_source_cannot_use_broader_opt_in(client, db):
    host = "expired.synthetic.example.com"
    expired_policy = _policy(
        [host],
        status="approved",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    source = RecipeSource(
        canonical_host=host,
        publisher_name="Expired synthetic source",
        revision=1,
        policy=SourcePolicy.model_validate(expired_policy).model_dump(mode="json"),
    )
    db.add(source)
    db.commit()
    recipe = _create_recipe(client, "Expired source recipe")
    denied = _link_reference(
        client, recipe["id"], f"https://{host}/recipes/dish", broader=True
    )
    assert denied.status_code == 409


def test_removed_alias_stays_revoked_for_an_existing_bound_reference(client, db):
    canonical = "publisher.synthetic.example.com"
    alias = "old-alias.synthetic.example.com"
    created = _review(db, canonical, _policy([canonical, alias], status="approved"))
    recipe = _create_recipe(client, "Alias bound recipe")
    linked = _link_reference(client, recipe["id"], f"https://{alias}/recipes/dish")
    assert linked.status_code == 200 and linked.json()["currently_allowed"] is True

    _review(db, canonical, _policy([canonical], status="approved"), expected_revision=created.revision)
    response = client.get(f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference")
    assert response.status_code == 200
    assert response.json()["currently_allowed"] is False
    assert response.json()["source_label"] == "Unavailable reference"


def test_removed_alias_cannot_be_rebound_through_broader_opt_in(client, db):
    canonical = "publisher2.synthetic.example.com"
    alias = "removed2.synthetic.example.com"
    created = _review(db, canonical, _policy([canonical, alias], status="approved"))
    recipe = _create_recipe(client, "Alias rebinding recipe")
    linked = _link_reference(client, recipe["id"], f"https://{alias}/recipes/dish")
    assert linked.status_code == 200
    _review(db, canonical, _policy([canonical], status="approved"), expected_revision=created.revision)

    response = _link_reference(
        client,
        recipe["id"],
        f"https://{alias}/recipes/dish",
        broader=True,
        revision=1,
    )
    assert response.status_code == 409
    current = db.scalar(
        select(RecipeSourceReference).where(
            RecipeSourceReference.recipe_id == recipe["id"]
        )
    )
    assert current.source_id is not None
    assert current.revision == 1


def test_reference_routes_are_household_scoped_and_recipe_revision_checked(client, db):
    foreign_recipe = Recipe(
        household_id=999999,
        title="Foreign synthetic recipe",
        cuisine="Filipino",
        content={},
        revision=1,
        is_active=True,
    )
    # A real foreign household is required for the recipe FK.
    from app.models.household import Household

    foreign_household = Household(name="Foreign", slug="foreign-source-test")
    db.add(foreign_household)
    db.flush()
    foreign_recipe.household_id = foreign_household.id
    db.add(foreign_recipe)
    db.commit()
    assert client.get(
        f"/api/v1/recipe-sources/recipes/{foreign_recipe.id}/reference"
    ).status_code == 404
    assert _link_reference(
        client,
        foreign_recipe.id,
        "https://other.synthetic.example.com/recipes/dish",
        broader=True,
    ).status_code == 404

    local_recipe = _create_recipe(client, "Revision guarded reference")
    stale = client.put(
        f"/api/v1/recipes/{local_recipe['id']}",
        json={**_recipe_payload("Updated recipe"), "expected_revision": 1},
    )
    assert stale.status_code == 200
    stale_reference = _link_reference(
        client,
        local_recipe["id"],
        "https://other.synthetic.example.com/recipes/dish",
        broader=True,
    )
    assert stale_reference.status_code == 409


def test_source_tier_ranking_happens_after_the_allergy_gate(client, db, catalog):
    declare(client, "egg")
    preferred_host = "filipino.synthetic.example.com"
    general_host = "broad.synthetic.example.com"
    blocked_host = "blocked.synthetic.example.com"
    _review(db, preferred_host, _policy([preferred_host], status="approved"))
    _review(db, general_host, _policy([general_host], status="approved", tier="broad_web"))
    _review(db, blocked_host, _policy([blocked_host], status="approved"))

    blocked = _create_recipe(client, "Egg recipe", "egg", "count")
    preferred = _create_recipe(client, "Preferred rice", "rice", "g")
    broad = _create_recipe(client, "Broad ginger", "ginger", "g")
    assert _link_reference(
        client, blocked["id"], f"https://{blocked_host}/recipes/egg"
    ).status_code == 200
    assert _link_reference(
        client, preferred["id"], f"https://{preferred_host}/recipes/rice"
    ).status_code == 200
    assert _link_reference(
        client,
        broad["id"],
        f"https://{general_host}/recipes/ginger",
        broader=True,
    ).status_code == 200

    response = client.post("/api/v1/recipes/recommendations", json={"mode": "all"})
    assert response.status_code == 200, response.text
    result = response.json()
    names = [item["recipe"]["title"] for item in result["items"]]
    assert "Egg recipe" not in names
    assert result["excluded_blocked"] == 1
    assert names.index("Preferred rice") < names.index("Broad ginger")


def test_source_reference_list_and_plan_do_not_mutate_reference_rows(client, db):
    recipe = _create_recipe(client, "Read-only registry recipe")
    assert _link_reference(
        client,
        recipe["id"],
        "https://other2.synthetic.example.com/recipes/dish",
        broader=True,
    ).status_code == 200
    before = db.scalar(select(func.count()).select_from(RecipeSourceReference))
    for _ in range(2):
        assert client.get("/api/v1/recipe-sources/").status_code == 200
        assert client.get(
            f"/api/v1/recipe-sources/recipes/{recipe['id']}/reference"
        ).status_code == 200
        assert client.post(
            "/api/v1/recipe-sources/discovery-plan",
            json={"query": "kangkong", "allow_broader_web": True},
        ).status_code == 200
    assert db.scalar(select(func.count()).select_from(RecipeSourceReference)) == before
    assert db.scalar(select(func.count()).select_from(Recipe)) == 1


def test_concurrent_reference_update_and_unlink_accept_one_revision(
    client, db, engine, auth_household, auth_user
):
    recipe = _create_recipe(client, "Concurrent reference revision")
    original_url = "https://original.synthetic.example.com/recipes/dish"
    assert _link_reference(client, recipe["id"], original_url, broader=True).status_code == 200

    household_id = auth_household.id
    actor_id = auth_user.id
    recipe_id = recipe["id"]
    update_request = SourceReferenceInput(
        expected_revision=1,
        expected_recipe_revision=1,
        url="https://updated.synthetic.example.com/recipes/dish",
        allow_broader_web=True,
    )
    barrier = Barrier(2)

    def update_reference():
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                result = write_reference(
                    independent, household_id, actor_id, recipe_id, update_request
                )
                return ("updated", result.revision)
            except HTTPException as exc:
                independent.rollback()
                return ("conflict", exc.status_code)

    def unlink_reference():
        with Session(engine) as independent:
            barrier.wait(timeout=10)
            try:
                remove_reference(independent, household_id, actor_id, recipe_id, 1)
                return ("removed", 204)
            except HTTPException as exc:
                independent.rollback()
                return ("conflict", exc.status_code)

    db.rollback()
    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(update_reference), workers.submit(unlink_reference)]
        outcomes = [future.result() for future in futures]

    assert [outcome[0] for outcome in outcomes].count("conflict") == 1
    assert sum(outcome[0] in {"updated", "removed"} for outcome in outcomes) == 1
    assert next(outcome for outcome in outcomes if outcome[0] == "conflict")[1] == 409

    final = client.get(f"/api/v1/recipe-sources/recipes/{recipe_id}/reference")
    assert final.status_code == 200
    reference = final.json()
    assert reference["revision"] == 2
    if reference["is_active"]:
        assert any(outcome[0] == "updated" for outcome in outcomes)
        assert reference["canonical_url"] == update_request.url
    else:
        assert any(outcome[0] == "removed" for outcome in outcomes)
        assert reference["canonical_url"] == original_url

