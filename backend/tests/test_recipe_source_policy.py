from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.recipe_source import RecipeSource, RecipeSourceReview
from app.schemas.recipe_source import SourcePolicy, SourceReviewInput
from app.services.recipe_sources import (
    discovery_plan,
    reference_policy,
    write_source_review,
)


def _policy_payload(
    host: str,
    *,
    status: str = "approved",
    tier: str = "filipino_priority",
    access_mode: str = "search_link_only",
    extraction_methods: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    allowed_redirect_hosts: list[str] | None = None,
    expires_at: datetime | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "review_status": status,
        "tier": tier,
        "enabled": status == "approved",
        "allowed_hosts": allowed_hosts or [host],
        "allowed_redirect_hosts": allowed_redirect_hosts or [],
        "access_mode": access_mode,
        "extraction_methods": extraction_methods or [],
        "cuisine_tags": ["Filipino"],
        "disabled_reason": None if status == "approved" else "Synthetic test policy",
    }
    if status == "approved":
        payload.update(
            terms_reference="Synthetic terms evidence",
            terms_reviewed_at=(now - timedelta(days=3)).isoformat(),
            last_audited_at=(now - timedelta(days=2)).isoformat(),
            review_expires_at=(expires_at or now + timedelta(days=30)).isoformat(),
        )
        if access_mode in {"structured_recipe_fetch", "licensed_full"}:
            payload.update(
                robots_reference="Synthetic robots evidence",
                robots_reviewed_at=(now - timedelta(days=3)).isoformat(),
                license_reference="Synthetic permission evidence",
            )
    return payload


def _review(
    db,
    host: str,
    payload: dict,
    *,
    expected_revision: int | None = None,
    publisher_name: str = "Synthetic source",
):
    request = SourceReviewInput(
        expected_revision=expected_revision,
        canonical_host=host,
        publisher_name=publisher_name,
        reviewed_by="Synthetic test maintainer",
        policy=payload,
    )
    return write_source_review(db, request)


def test_approval_requires_terms_review_to_be_covered_by_the_audit() -> None:
    now = datetime.now(timezone.utc)
    payload = _policy_payload("policy.synthetic.example.com")
    payload["terms_reviewed_at"] = (now - timedelta(hours=1)).isoformat()
    payload["last_audited_at"] = (now - timedelta(hours=2)).isoformat()
    payload["review_expires_at"] = (now + timedelta(days=1)).isoformat()

    with pytest.raises(ValidationError, match="audit must include the current terms review"):
        SourcePolicy.model_validate(payload)


@pytest.mark.parametrize(
    ("access_mode", "methods"),
    [
        ("search_link_only", ["json_ld"]),
        ("metadata_only", ["json_ld"]),
        ("metadata_only", ["api_json"]),
        ("structured_recipe_fetch", ["full_text"]),
    ],
    ids=["link-only", "metadata-only", "metadata-only-api", "full-text-needs-license"],
)
def test_access_mode_rejects_unapproved_extraction(
    access_mode: str, methods: list[str]
) -> None:
    payload = _policy_payload(
        "access.synthetic.example.com",
        access_mode=access_mode,
        extraction_methods=methods,
    )

    with pytest.raises(ValidationError):
        SourcePolicy.model_validate(payload)


def test_api_json_approval_requires_fetch_evidence():
    payload = _policy_payload(
        "api.synthetic.example.com", access_mode="structured_recipe_fetch", extraction_methods=["api_json"]
    )
    assert SourcePolicy.model_validate(payload).extraction_methods == ["api_json"]
    payload["license_reference"] = None
    with pytest.raises(ValidationError):
        SourcePolicy.model_validate(payload)


def test_structured_fetch_approval_requires_current_robots_and_permission_evidence() -> None:
    host = "fetch.synthetic.example.com"
    payload = _policy_payload(
        host,
        access_mode="structured_recipe_fetch",
        extraction_methods=["json_ld"],
    )
    payload["robots_reviewed_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    payload["last_audited_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=2)
    ).isoformat()

    with pytest.raises(ValidationError, match="audit must include the current robots review"):
        SourcePolicy.model_validate(payload)


def test_source_host_aliases_are_normalized_and_duplicates_rejected() -> None:
    payload = _policy_payload(
        "publisher.synthetic.example.com",
        allowed_hosts=[
            "publisher.synthetic.example.com",
            "WWW.SYNTHETIC.EXAMPLE.COM",
        ],
    )
    policy = SourcePolicy.model_validate(payload)

    assert policy.allowed_hosts == [
        "publisher.synthetic.example.com",
        "www.synthetic.example.com",
    ]
    payload["allowed_hosts"] = [
        "www.synthetic.example.com",
        "WWW.SYNTHETIC.EXAMPLE.COM",
    ]
    with pytest.raises(ValidationError, match="cannot contain duplicates"):
        SourcePolicy.model_validate(payload)


def test_registered_source_host_alias_cannot_collide_with_another_source(db) -> None:
    first_host = "publisher-one.synthetic.example.com"
    shared_alias = "www.synthetic.example.com"
    _review(
        db,
        first_host,
        _policy_payload(
            first_host,
            status="candidate",
            allowed_hosts=[first_host, shared_alias],
        ),
    )
    review_count = db.scalar(select(func.count()).select_from(RecipeSourceReview))

    second_host = "publisher-two.synthetic.example.com"
    with pytest.raises(HTTPException) as conflict:
        _review(
            db,
            second_host,
            _policy_payload(
                second_host,
                status="candidate",
                allowed_hosts=[second_host, shared_alias],
            ),
        )

    assert conflict.value.status_code == 409
    assert db.scalar(select(func.count()).select_from(RecipeSource)) == 1
    assert db.scalar(select(func.count()).select_from(RecipeSourceReview)) == review_count


@pytest.mark.parametrize("status", ["suspended", "rejected", "expired-approved"])
def test_revoked_or_expired_source_stays_blocked_with_broader_opt_in(db, status: str) -> None:
    host = f"{status}.synthetic.example.com"
    if status == "expired-approved":
        payload = _policy_payload(
            host,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
    else:
        payload = _policy_payload(host, status=status)
    source = RecipeSource(
        canonical_host=host,
        publisher_name="Synthetic source",
        revision=1,
        policy=SourcePolicy.model_validate(payload).model_dump(mode="json"),
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    matched_source, allowed, label = reference_policy(
        db,
        f"https://{host}/recipe/adobo",
        broader_permission=True,
        bound_source_id=source.id,
    )

    assert matched_source.id == source.id
    assert allowed is False
    assert label == "Unavailable reference"


def test_removed_bound_alias_does_not_fall_through_to_broader_opt_in(db) -> None:
    host = "publisher.synthetic.example.com"
    alias = "www.publisher.synthetic.example.com"
    source = _review(
        db,
        host,
        _policy_payload(host, allowed_hosts=[host, alias]),
    )

    _review(
        db,
        host,
        _policy_payload(host, allowed_hosts=[host]),
        expected_revision=source.revision,
    )
    matched_source, allowed, label = reference_policy(
        db,
        f"https://{alias}/recipe/adobo",
        broader_permission=True,
        bound_source_id=source.id,
    )

    assert matched_source.id == source.id
    assert allowed is False
    assert label == "Unavailable reference"


def test_source_review_refreshes_stale_identity_before_revision_check(db, engine) -> None:
    host = "revision.synthetic.example.com"
    created = _review(db, host, _policy_payload(host))
    stale_source = db.get(RecipeSource, created.id)
    assert stale_source is not None and stale_source.revision == 1

    with Session(engine) as concurrent_session:
        updated = _review(
            concurrent_session,
            host,
            _policy_payload(host, tier="reviewed_general"),
            expected_revision=1,
            publisher_name="Updated synthetic source",
        )
        assert updated.revision == 2

    with pytest.raises(HTTPException) as conflict:
        _review(
            db,
            host,
            _policy_payload(host, tier="filipino_priority"),
            expected_revision=1,
        )

    assert conflict.value.status_code == 409
    assert stale_source.revision == 2


def test_discovery_plan_is_bounded_offline_and_keeps_user_terms_inside_quotes(db) -> None:
    sources = []
    for index in range(22):
        host = f"priority-{index:02}.synthetic.example.com"
        policy = SourcePolicy.model_validate(_policy_payload(host))
        sources.append(
            RecipeSource(
                canonical_host=host,
                publisher_name=f"Synthetic source {index}",
                revision=1,
                policy=policy.model_dump(mode="json"),
            )
        )
    general_host = "general.synthetic.example.com"
    sources.append(
        RecipeSource(
            canonical_host=general_host,
            publisher_name="Synthetic general source",
            revision=1,
            policy=SourcePolicy.model_validate(
                _policy_payload(general_host, tier="reviewed_general")
            ).model_dump(mode="json"),
        )
    )
    db.add_all(sources)
    db.commit()

    plan = discovery_plan(
        db,
        '  rice" OR site:outside.example.com \\ adobo\x00  ',
        allow_broader_web=False,
        include_general=True,
    )

    assert len(plan["priority_queries"]) == 20
    assert len(plan["general_queries"]) == 1
    assert all(len(query) <= 128 and query.count('"') == 2 for query in plan["priority_queries"])
    assert all("\x00" not in query for query in plan["priority_queries"])
    assert plan["broader_query"] is None
    assert plan["provider_enabled"] is False
    assert plan["fetch_enabled"] is False
    assert plan["executed"] is False
    assert plan["results"] == []
