from datetime import datetime, timezone
import unicodedata
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import or_, select, text

from app.models.recipe import Recipe, RecipeRevision
from app.models.recipe_source import RecipeSource, RecipeSourceReference, RecipeSourceReview
from app.schemas.recipe_source import SourcePolicy, SourceRead, SourceReferenceRead
from app.services.recipes import _lock_member, get_recipe
from app.services.source_urls import canonical_recipe_url


_MAX_ADAPTATION_DEPTH = 4
_OWNED_PERMISSION = "OWNED_OR_PERMISSION_GRANTED"


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


def _adaptation_parent(snapshot):
    if not isinstance(snapshot, dict):
        return False
    parent_id = snapshot.get("adapted_from_recipe_id")
    parent_revision = snapshot.get("adapted_from_recipe_revision")
    if parent_id is None and parent_revision is None:
        return None
    if type(parent_id) is not int or parent_id <= 0 or type(parent_revision) is not int or parent_revision < 1:
        return False
    return parent_id, parent_revision


def _parent_chain_is_allowed(db, household_id, parent_id, parent_revision, seen_ids, depth):
    if depth > _MAX_ADAPTATION_DEPTH or parent_id in seen_ids:
        return False
    parent = db.scalar(
        select(Recipe)
        .where(Recipe.household_id == household_id, Recipe.id == parent_id)
        .execution_options(populate_existing=True)
    )
    if (
        parent is None
        or not parent.is_active
        or parent.content.get("content_permission") != _OWNED_PERMISSION
    ):
        return False
    if db.scalar(
        select(RecipeSourceReference.id)
        .where(
            RecipeSourceReference.household_id == household_id,
            RecipeSourceReference.recipe_id == parent_id,
        )
        .limit(1)
    ) is not None:
        return False

    pinned = db.scalar(
        select(RecipeRevision)
        .where(
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == parent_id,
            RecipeRevision.revision == parent_revision,
        )
        .execution_options(populate_existing=True)
    )
    if (
        pinned is None
        or pinned.snapshot.get("content_permission") != _OWNED_PERMISSION
        or pinned.snapshot.get("provenance", "USER_ENTERED") != "USER_ENTERED"
    ):
        return False

    seen_ids.add(parent_id)
    ancestor = _adaptation_parent(pinned.snapshot)
    if ancestor is False:
        return False
    if ancestor is None:
        return True
    return _parent_chain_is_allowed(
        db, household_id, ancestor[0], ancestor[1], seen_ids, depth + 1
    )


def recipe_origin_context(db, household_id, recipe_id, recipe_revision=None):
    """Check the immutable user-authored parent chain against current policy."""
    recipe = db.scalar(
        select(Recipe)
        .where(Recipe.household_id == household_id, Recipe.id == recipe_id)
        .execution_options(populate_existing=True)
    )
    if recipe is None:
        return False

    if recipe_revision is None:
        snapshot = recipe.content
    else:
        revision = db.scalar(
            select(RecipeRevision)
            .where(
                RecipeRevision.household_id == household_id,
                RecipeRevision.recipe_id == recipe_id,
                RecipeRevision.revision == recipe_revision,
            )
            .execution_options(populate_existing=True)
        )
        if revision is None:
            return False
        snapshot = revision.snapshot

    parent = _adaptation_parent(snapshot)
    if parent is False:
        return False
    if parent is None:
        return True
    return _parent_chain_is_allowed(
        db, household_id, parent[0], parent[1], {recipe_id}, 1
    )


def validate_adaptation_parent(
    db, household_id, child_recipe_id, parent_recipe_id, parent_revision
):
    """Reject an unusable parent before a new recipe revision is written."""
    if child_recipe_id is not None and parent_recipe_id == child_recipe_id:
        raise HTTPException(status_code=422, detail="ADAPTATION_PARENT_UNAVAILABLE")
    parent = db.scalar(
        select(Recipe)
        .where(
            Recipe.household_id == household_id,
            Recipe.id == parent_recipe_id,
        )
        .execution_options(populate_existing=True)
    )
    if parent is None:
        raise HTTPException(status_code=404, detail="ADAPTATION_PARENT_NOT_FOUND")
    pinned = db.scalar(
        select(RecipeRevision)
        .where(
            RecipeRevision.household_id == household_id,
            RecipeRevision.recipe_id == parent_recipe_id,
            RecipeRevision.revision == parent_revision,
        )
        .execution_options(populate_existing=True)
    )
    if pinned is None:
        raise HTTPException(status_code=404, detail="ADAPTATION_PARENT_REVISION_NOT_FOUND")
    if not _parent_chain_is_allowed(
        db,
        household_id,
        parent_recipe_id,
        parent_revision,
        {child_recipe_id} if child_recipe_id is not None else set(),
        1,
    ):
        raise HTTPException(status_code=422, detail="ADAPTATION_PARENT_UNAVAILABLE")


def recipe_source_context(db, household_id, recipe_id, recipe_revision=None):
    if not recipe_origin_context(db, household_id, recipe_id, recipe_revision):
        return False, 0, None
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
