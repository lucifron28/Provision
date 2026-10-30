from datetime import datetime, timezone
import unicodedata
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import or_, select, text

from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.schemas.recipe_source import SourcePolicy, SourceRead, SourceReferenceRead
from app.services.recipes import _lock_member, get_recipe
from app.services.source_urls import canonical_recipe_url


def source_approved(source):
    policy = SourcePolicy.model_validate(source.policy)
    return bool(policy.review_status == "approved" and policy.enabled and policy.review_expires_at
        and policy.review_expires_at > datetime.now(timezone.utc))


def source_read(source):
    policy = SourcePolicy.model_validate(source.policy)
    return SourceRead(id=source.id, publisher_name=source.publisher_name, canonical_host=source.canonical_host,
        revision=source.revision, review_status=policy.review_status, tier=policy.tier,
        access_mode=policy.access_mode, currently_approved=source_approved(source))


def write_source_review(db, request):
    """Maintainer-only entry point. Not exposed through the household HTTP API."""
    db.execute(text("SELECT pg_advisory_xact_lock(734962181)"))
    sources = db.scalars(
        select(RecipeSource)
        .order_by(RecipeSource.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).all()
    current = next((source for source in sources if source.canonical_host == request.canonical_host), None)
    if request.expected_revision != (current.revision if current else None):
        raise HTTPException(409, "SOURCE_REVISION_CONFLICT")
    requested_hosts = set(request.policy.allowed_hosts) | set(request.policy.allowed_redirect_hosts)
    for source in sources:
        if source is current:
            continue
        policy = SourcePolicy.model_validate(source.policy)
        if requested_hosts & (set(policy.allowed_hosts) | set(policy.allowed_redirect_hosts)):
            raise HTTPException(409, "SOURCE_HOST_ALREADY_REGISTERED")
    if request.policy.review_status == "approved" and request.policy.review_expires_at <= datetime.now(timezone.utc):
        raise HTTPException(422, "SOURCE_REVIEW_ALREADY_EXPIRED")
    if current is None:
        current = RecipeSource(canonical_host=request.canonical_host, publisher_name=request.publisher_name,
            revision=1, policy=request.policy.model_dump(mode="json"))
        db.add(current)
        db.flush()
    else:
        current.publisher_name = request.publisher_name
        current.revision += 1
        current.policy = request.policy.model_dump(mode="json")
    db.add(RecipeSourceReview(source_id=current.id, revision=current.revision, reviewed_by=request.reviewed_by,
        recorded_at=datetime.now(timezone.utc), snapshot=request.model_dump(mode="json")))
    db.commit()
    return source_read(current)


def _source_for_host(db, host, *, lock=False):
    statement = select(RecipeSource).order_by(RecipeSource.id)
    if lock:
        statement = statement.with_for_update()
    sources = db.scalars(statement.execution_options(populate_existing=True)).all()
    matches = [source for source in sources
        if host in SourcePolicy.model_validate(source.policy).allowed_hosts]
    if len(matches) > 1:
        raise HTTPException(409, "AMBIGUOUS_SOURCE_HOST")
    return matches[0] if matches else None


def _host_was_registered(db, host):
    """Check current and legacy review snapshot shapes for retired aliases."""
    snapshots = RecipeSourceReview.snapshot
    host_list = [host]
    return db.scalar(
        select(RecipeSourceReview.id)
        .where(
            or_(
                snapshots["policy"]["allowed_hosts"].contains(host_list),
                snapshots["policy"]["allowed_redirect_hosts"].contains(host_list),
                snapshots["allowed_hosts"].contains(host_list),
                snapshots["allowed_redirect_hosts"].contains(host_list),
            )
        )
        .limit(1)
    ) is not None


def reference_policy(db, url, broader_permission, bound_source_id=None, *, lock=False):
    canonical = canonical_recipe_url(url)
    host = urlsplit(canonical).hostname
    if bound_source_id is not None:
        statement = select(RecipeSource).where(RecipeSource.id == bound_source_id)
        if lock:
            statement = statement.with_for_update()
        source = db.scalar(statement.execution_options(populate_existing=True))
    else:
        source = _source_for_host(db, host, lock=lock)
    if bound_source_id is not None and (source is None or host not in SourcePolicy.model_validate(source.policy).allowed_hosts):
        return source, False, "Unavailable reference"
    if source is None and _host_was_registered(db, host):
        return None, False, "Unavailable reference"
    if source:
        policy = SourcePolicy.model_validate(source.policy)
        if policy.review_status in {"suspended", "rejected"}:
            return source, False, "Unavailable reference"
        if policy.review_status == "approved":
            if not source_approved(source):
                return source, False, "Unavailable reference"
            if policy.tier != "broad_web":
                label = "Reference to reviewed Filipino publisher" if policy.tier == "filipino_priority" else "Reference to reviewed publisher"
                return source, True, label
    return source, bool(broader_permission), "Other website, verify details"


def _reference(db, household_id, recipe_id, *, lock=False):
    statement = select(RecipeSourceReference).where(
        RecipeSourceReference.household_id == household_id,
        RecipeSourceReference.recipe_id == recipe_id,
    )
    if lock:
        statement = statement.with_for_update()
    return db.scalar(statement.execution_options(populate_existing=True))


def reference_read(db, reference):
    source, allowed, label = reference_policy(db, reference.canonical_url, reference.broader_web_permission, reference.source_id)
    return SourceReferenceRead(recipe_id=reference.recipe_id, revision=reference.revision, is_active=reference.is_active,
        canonical_url=reference.canonical_url, author=reference.author,
        publisher_name=source.publisher_name if source else urlsplit(reference.canonical_url).hostname,
        source_label=label if reference.is_active else "Inactive reference", currently_allowed=allowed and reference.is_active,
        linked_at=reference.created_at)


def read_reference(db, household_id, recipe_id):
    get_recipe(db, household_id, recipe_id)
    reference = _reference(db, household_id, recipe_id)
    if reference is None:
        raise HTTPException(404, "Recipe source reference not found")
    return reference_read(db, reference)


def write_reference(db, household_id, actor_id, recipe_id, request):
    _lock_member(db, household_id, actor_id)
    recipe = get_recipe(db, household_id, recipe_id, lock=True)
    if recipe.revision != request.expected_recipe_revision or not recipe.is_active:
        raise HTTPException(409, "RECIPE_REVISION_CONFLICT")
    current = _reference(db, household_id, recipe_id, lock=True)
    if request.expected_revision != (current.revision if current else None):
        raise HTTPException(409, "SOURCE_REFERENCE_REVISION_CONFLICT")
    try:
        canonical = canonical_recipe_url(request.url)
        source, allowed, _ = reference_policy(
            db, canonical, request.allow_broader_web, lock=True
        )
    except ValueError as exc:
        raise HTTPException(422, "Invalid public recipe URL") from exc
    if not allowed:
        raise HTTPException(409, "SOURCE_NOT_APPROVED_OR_BROADER_PERMISSION_REQUIRED")
    if current is None:
        current = RecipeSourceReference(household_id=household_id, recipe_id=recipe_id, revision=1)
        db.add(current)
    else:
        current.revision += 1
    current.source_id = source.id if source else None
    current.canonical_url, current.author = canonical, request.author
    current.broader_web_permission, current.is_active = request.allow_broader_web, True
    current.linked_by_user_id = actor_id
    db.commit()
    return reference_read(db, current)


def remove_reference(db, household_id, actor_id, recipe_id, expected_revision):
    _lock_member(db, household_id, actor_id)
    get_recipe(db, household_id, recipe_id, lock=True)
    reference = _reference(db, household_id, recipe_id, lock=True)
    if reference is None or reference.revision != expected_revision or not reference.is_active:
        raise HTTPException(409, "SOURCE_REFERENCE_REVISION_CONFLICT")
    reference.is_active = False
    reference.revision += 1
    db.commit()


def recipe_source_context(db, household_id, recipe_id):
    reference = _reference(db, household_id, recipe_id)
    if reference is None or not reference.is_active:
        return True, 0, None
    source, allowed, _ = reference_policy(db, reference.canonical_url, reference.broader_web_permission, reference.source_id)
    if not allowed:
        return False, 0, reference_read(db, reference)
    if source and source_approved(source):
        tier = SourcePolicy.model_validate(source.policy).tier
        return True, {"filipino_priority": 2, "reviewed_general": 1, "broad_web": 0}[tier], reference_read(db, reference)
    return True, 0, reference_read(db, reference)


def discovery_plan(db, query, allow_broader_web=False, include_general=False):
    """Return a bounded offline plan, never execute a search or fabricate results."""
    sources = [
        source
        for source in db.scalars(
            select(RecipeSource)
            .order_by(RecipeSource.id)
            .execution_options(populate_existing=True)
        ).all()
        if source_approved(source)
    ]
    priority, general = [], []
    for source in sources:
        policy = SourcePolicy.model_validate(source.policy)
        if policy.tier == "filipino_priority":
            priority.append(source.canonical_host)
        elif policy.tier == "reviewed_general" and include_general:
            general.append(source.canonical_host)
    # A quoted phrase cannot inject search operators. One host per bounded query.
    clean_query = "".join(
        " " if unicodedata.category(char) == "Cc" else char for char in query
    )
    phrase = " ".join(clean_query.replace('"', " ").replace("\\", " ").split())[:64]
    if not phrase:
        raise HTTPException(422, "A recipe search phrase is required")
    def queries(hosts):
        result = []
        for host in hosts[:20]:
            budget = 128 - len(f'"" recipe site:{host}')
            if budget > 0:
                result.append(f'"{phrase[:budget]}" recipe site:{host}')
        return result
    return dict(priority_queries=queries(priority), general_queries=queries(general),
        broader_query=f'"{phrase}" recipe' if allow_broader_web else None,
        provider_enabled=False, fetch_enabled=False, executed=False, results=[])
