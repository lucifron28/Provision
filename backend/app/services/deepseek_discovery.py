"""Policy-gated recipe search and a pinned, opt-in page fetch boundary.

This module has no default provider or network client. Search providers are
injected, and page transports must resolve and request one pinned IP at a time.
Search snippets and fetched bytes remain untrusted publisher data.
"""

from dataclasses import dataclass
import re
from typing import Literal, Protocol, Sequence
from urllib.parse import urljoin, urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household import HouseholdMembership
from app.models.recipe_source import RecipeSource
from app.models.user import User
from app.schemas.deepseek import (
    DeepSeekFetchRequest,
    DeepSeekFetchResponse,
    DeepSeekSearchRequest,
    DeepSeekSearchResponse,
)
from app.schemas.recipe_source import AccessMode, SourcePolicy, SourceTier
from app.services.privacy import all_active_household_members_consented
from app.services.household_writes import lock_household_write
from app.services.deepseek_provider import DeepSeekProviderError
from app.services.recipe_sources import (
    discovery_plan,
    reference_policy,
    source_approved,
)
from app.services.source_urls import canonical_recipe_url, validate_redirect_hops
from app.services.wikimedia_robots import HOST as WIKIMEDIA_ROBOTS_HOST, wikimedia_robots_allowed


MAX_DISCOVERY_RESULTS = 20
MAX_SEARCH_REQUESTS = 9
MAX_RESULTS_PER_REQUEST = 10
MAX_REDIRECT_URLS = 6
MAX_FETCH_BYTES = 1_000_000
PROVIDER_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class ProviderSearchHit:
    """Small adapter output. Do not include provider content or long summaries."""

    title: str
    url: str
    snippet: str = ""


class DeepSeekRecipeSearchProvider(Protocol):
    """Injected search-only adapter; it must request metadata, never page content."""

    @property
    def max_search_results(self) -> int: ...

    def search(self, request: DeepSeekSearchRequest) -> DeepSeekSearchResponse: ...


class DeepSeekRecipeFetchProvider(Protocol):
    """Fetch API shape, kept injectable so tests can assert the fail-closed path."""

    def fetch(self, request: DeepSeekFetchRequest) -> DeepSeekFetchResponse: ...


@dataclass(frozen=True)
class DiscoveredRecipeLink:
    title: str
    canonical_url: str
    snippet: str
    publisher_name: str
    source_id: int | None
    source_tier: SourceTier
    access_mode: AccessMode
    verified_source: bool
    untrusted_content: Literal[True] = True


@dataclass(frozen=True)
class DiscoveryResponse:
    results: tuple[DiscoveredRecipeLink, ...]
    provider_calls: int
    broader_web_searched: bool
    fetch_performed: Literal[False] = False


@dataclass(frozen=True)
class RecipeFetchAuthorization:
    canonical_url: str
    source_id: int
    source_revision: int
    publisher_name: str
    access_mode: AccessMode
    extraction_methods: tuple[str, ...]
    allowed_hosts: frozenset[str]
    allowed_redirect_hosts: frozenset[str]


@dataclass(frozen=True)
class PageFetchResponse:
    """One HTTP response. The transport must never follow redirects itself."""

    status_code: int
    headers: dict[str, str]
    body: bytes


class PinnedPageTransport(Protocol):
    """Transport contract for future fetch adapters, not an HTTP implementation.

    ``fetch_once_pinned`` must connect directly to ``connect_ip``, retain the
    URL hostname for Host and TLS SNI checks, disable automatic redirects, and
    stop reading after ``max_bytes``. If it decompresses a response, it must
    bound both encoded and decoded bodies and normalize the content encoding.
    It must also bound response headers. The service validates every hop
    before it asks the transport to make the next request.
    """

    @property
    def user_agent(self) -> str: ...

    def resolve(self, hostname: str) -> Sequence[str]: ...

    def fetch_once_pinned(
        self,
        url: str,
        *,
        connect_ip: str,
        timeout_seconds: float,
        max_bytes: int,
    ) -> PageFetchResponse: ...


class RecipeRobotsPolicy(Protocol):
    def __call__(self, url: str, *, transport: PinnedPageTransport) -> bool: ...


@dataclass(frozen=True)
class FetchedRecipePage:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    content_type: str
    content: bytes
    untrusted_content: Literal[True] = True


def _require_member_and_consent(db: Session, household_id: int, actor_id: int) -> None:
    active_member = db.scalar(
        select(HouseholdMembership.id)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(
            HouseholdMembership.household_id == household_id,
            HouseholdMembership.user_id == actor_id,
            User.is_active.is_(True),
        )
        .execution_options(populate_existing=True)
    )
    if active_member is None:
        raise HTTPException(status_code=403, detail="ACTIVE_HOUSEHOLD_MEMBERSHIP_REQUIRED")
    if not all_active_household_members_consented(db, household_id=household_id):
        raise HTTPException(status_code=403, detail="CURRENT_HOUSEHOLD_CONSENT_REQUIRED")


def _registered_hosts(db: Session) -> set[str]:
    hosts: set[str] = set()
    sources = db.scalars(
        select(RecipeSource).order_by(RecipeSource.id).execution_options(populate_existing=True)
    ).all()
    for source in sources:
        policy = SourcePolicy.model_validate(source.policy)
        hosts.add(source.canonical_host)
        hosts.update(policy.allowed_hosts)
        hosts.update(policy.allowed_redirect_hosts)
    return hosts


def _site_host(query: str) -> str | None:
    match = re.search(r"(?:^|\s)site:([a-z0-9.-]+)(?:\s|$)", query)
    return match.group(1) if match else None


def _query_host_is_currently_approved(db: Session, host: str, tier: SourceTier) -> bool:
    try:
        canonical_host = canonical_recipe_url(f"https://{host}/recipe/discovery-query")
    except ValueError:
        return False
    result_host = urlsplit(canonical_host).hostname
    if result_host != host:
        return False
    source, allowed, _label = reference_policy(
        db, canonical_host, broader_permission=False
    )
    if source is None or not allowed or not source_approved(source):
        return False
    policy = SourcePolicy.model_validate(source.policy)
    return policy.review_status == "approved" and policy.tier == tier and host in policy.allowed_hosts


def _clean_display_text(value: str, maximum: int) -> str:
    return "".join(character for character in value if ord(character) >= 32 and ord(character) != 127)[
        :maximum
    ].strip()


def _normalize_hit(
    db: Session,
    hit: ProviderSearchHit,
    *,
    expected_host: str | None,
    allow_broader_web: bool,
    registered_hosts: set[str],
) -> DiscoveredRecipeLink | None:
    if not isinstance(hit, ProviderSearchHit):
        return None
    title = _clean_display_text(hit.title, 300) if isinstance(hit.title, str) else ""
    if not title:
        return None
    try:
        canonical = canonical_recipe_url(hit.url)
    except (TypeError, ValueError):
        return None
    host = urlsplit(canonical).hostname
    if host is None or (expected_host is not None and host != expected_host):
        return None

    source, allowed, _label = reference_policy(
        db, canonical, broader_permission=allow_broader_web
    )
    if not allowed:
        return None
    if source is None:
        if not allow_broader_web or host in registered_hosts:
            return None
        return DiscoveredRecipeLink(
            title=title,
            canonical_url=canonical,
            snippet=_clean_display_text(hit.snippet, 240) if isinstance(hit.snippet, str) else "",
            publisher_name=host,
            source_id=None,
            source_tier="broad_web",
            access_mode="search_link_only",
            verified_source=False,
        )

    if not source_approved(source):
        return None
    policy = SourcePolicy.model_validate(source.policy)
    if policy.review_status != "approved" or host not in policy.allowed_hosts:
        return None
    if policy.tier == "broad_web" and not allow_broader_web:
        return None
    return DiscoveredRecipeLink(
        title=title,
        canonical_url=canonical,
        snippet=_clean_display_text(hit.snippet, 240) if isinstance(hit.snippet, str) else "",
        publisher_name=source.publisher_name,
        source_id=source.id,
        source_tier=policy.tier,
        access_mode=policy.access_mode,
        verified_source=True,
    )


def _provider_hits(
    provider: DeepSeekRecipeSearchProvider,
    query: str,
    *,
    count: int,
) -> Sequence[ProviderSearchHit]:
    """Request metadata only and discard long summaries/provider-only fields."""
    configured_limit = provider.max_search_results
    if type(configured_limit) is not int or configured_limit < 1:
        raise ValueError("Invalid provider search-result limit")
    response = provider.search(
        DeepSeekSearchRequest(query=query, count=min(count, configured_limit))
    )
    if not isinstance(response, DeepSeekSearchResponse):
        raise TypeError("Unexpected DeepSeek search response")
    return tuple(
        ProviderSearchHit(title=result.title, url=result.url, snippet=result.snippet)
        for result in response.results
        if not result.content
    )


def _discovery_provider_error(error: DeepSeekProviderError) -> HTTPException:
    if error.code in {"rate_limited", "request_budget_exhausted"}:
        status = 429
    elif error.code == "timeout":
        status = 504
    elif error.code in {"disabled", "configuration", "budget_unavailable"}:
        status = 503
    else:
        status = 502
    return HTTPException(status_code=status, detail={"code": error.code})


def discover_recipes(
    db: Session,
    household_id: int,
    actor_id: int,
    query: str,
    *,
    allow_broader_web: bool = False,
    provider: DeepSeekRecipeSearchProvider | None,
    max_results: int = 10,
) -> DiscoveryResponse:
    """Search reviewed publisher hosts first, then opt-in broader web.

    This only returns bounded, untrusted links and snippets. It never fetches a
    page, invokes a model, ranks allergy suitability, or writes to the database.
    """
    _require_member_and_consent(db, household_id, actor_id)
    # Consent and membership changes use this same household lock. Recheck
    # after acquiring it in case either changed between the two operations.
    lock_household_write(db, household_id, actor_id=actor_id)
    _require_member_and_consent(db, household_id, actor_id)
    if type(allow_broader_web) is not bool:
        raise HTTPException(status_code=422, detail="INVALID_BROADER_WEB_OPT_IN")
    if not isinstance(query, str) or len(query) > 512:
        raise HTTPException(status_code=422, detail="INVALID_RECIPE_QUERY")
    if type(max_results) is not int or not 1 <= max_results <= MAX_DISCOVERY_RESULTS:
        raise HTTPException(status_code=422, detail="INVALID_DISCOVERY_RESULT_LIMIT")

    base_plan = discovery_plan(db, query, allow_broader_web=False, include_general=False)
    results: list[DiscoveredRecipeLink] = []
    seen_urls: set[str] = set()
    calls = 0
    registered_hosts = _registered_hosts(db)
    restricted_call_limit = MAX_SEARCH_REQUESTS - int(allow_broader_web)

    def run_restricted_queries(queries: Sequence[str], tier: SourceTier) -> None:
        nonlocal calls
        for provider_query in queries:
            if calls >= restricted_call_limit or len(results) >= max_results:
                return
            host = _site_host(provider_query)
            if host is None or not _query_host_is_currently_approved(db, host, tier):
                continue
            _require_member_and_consent(db, household_id, actor_id)
            if provider is None:
                raise HTTPException(status_code=503, detail="RECIPE_DISCOVERY_PROVIDER_DISABLED")
            count = min(MAX_RESULTS_PER_REQUEST, max_results - len(results))
            try:
                hits = _provider_hits(provider, provider_query, count=count)
            except DeepSeekProviderError as error:
                raise _discovery_provider_error(error) from None
            except Exception:
                raise HTTPException(
                    status_code=503, detail="RECIPE_DISCOVERY_PROVIDER_UNAVAILABLE"
                ) from None
            calls += 1
            if not isinstance(hits, Sequence) or isinstance(hits, (str, bytes)):
                continue
            for hit in hits[:MAX_RESULTS_PER_REQUEST]:
                candidate = _normalize_hit(
                    db,
                    hit,
                    expected_host=host,
                    allow_broader_web=False,
                    registered_hosts=registered_hosts,
                )
                if candidate is not None and candidate.canonical_url not in seen_urls:
                    results.append(candidate)
                    seen_urls.add(candidate.canonical_url)
                    if len(results) >= max_results:
                        return

    run_restricted_queries(base_plan["priority_queries"], "filipino_priority")

    if len(results) < max_results and calls < restricted_call_limit:
        general_plan = discovery_plan(db, query, include_general=True)
        run_restricted_queries(general_plan["general_queries"], "reviewed_general")

    broader_searched = False
    if allow_broader_web and len(results) < max_results and calls < MAX_SEARCH_REQUESTS:
        broad_plan = discovery_plan(
            db, query, allow_broader_web=True, include_general=True
        )
        broader_query = broad_plan["broader_query"]
        if broader_query:
            _require_member_and_consent(db, household_id, actor_id)
            if provider is None:
                raise HTTPException(status_code=503, detail="RECIPE_DISCOVERY_PROVIDER_DISABLED")
            try:
                hits = _provider_hits(
                    provider,
                    broader_query,
                    count=min(MAX_RESULTS_PER_REQUEST, max_results - len(results)),
                )
            except DeepSeekProviderError as error:
                raise _discovery_provider_error(error) from None
            except Exception:
                raise HTTPException(
                    status_code=503, detail="RECIPE_DISCOVERY_PROVIDER_UNAVAILABLE"
                ) from None
            calls += 1
            broader_searched = True
            if isinstance(hits, Sequence) and not isinstance(hits, (str, bytes)):
                for hit in hits[:MAX_RESULTS_PER_REQUEST]:
                    candidate = _normalize_hit(
                        db,
                        hit,
                        expected_host=None,
                        allow_broader_web=True,
                        registered_hosts=registered_hosts,
                    )
                    if candidate is not None and candidate.canonical_url not in seen_urls:
                        results.append(candidate)
                        seen_urls.add(candidate.canonical_url)
                        if len(results) >= max_results:
                            break

    _require_member_and_consent(db, household_id, actor_id)
    return DiscoveryResponse(
        results=tuple(results),
        provider_calls=calls,
        broader_web_searched=broader_searched,
    )


def authorize_recipe_fetch(
    db: Session,
    url: str,
    *,
    allow_broader_web: bool = False,
) -> RecipeFetchAuthorization:
    """Return fetch policy for an explicitly approved source; never fetch here."""
    if type(allow_broader_web) is not bool:
        raise HTTPException(status_code=422, detail="INVALID_BROADER_WEB_OPT_IN")
    try:
        canonical = canonical_recipe_url(url)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="INVALID_RECIPE_URL") from exc
    source, allowed, _label = reference_policy(
        db, canonical, broader_permission=allow_broader_web
    )
    if source is None or not allowed or not source_approved(source):
        raise HTTPException(status_code=403, detail="RECIPE_FETCH_NOT_AUTHORIZED")
    policy = SourcePolicy.model_validate(source.policy)
    host = urlsplit(canonical).hostname
    if (
        policy.review_status != "approved"
        or host not in policy.allowed_hosts
        or policy.access_mode not in {"structured_recipe_fetch", "licensed_full"}
        or not policy.extraction_methods
        or (policy.tier == "broad_web" and not allow_broader_web)
    ):
        raise HTTPException(status_code=403, detail="RECIPE_FETCH_NOT_AUTHORIZED")
    return RecipeFetchAuthorization(
        canonical_url=canonical,
        source_id=source.id,
        source_revision=source.revision,
        publisher_name=source.publisher_name,
        access_mode=policy.access_mode,
        extraction_methods=tuple(policy.extraction_methods),
        allowed_hosts=frozenset(policy.allowed_hosts),
        allowed_redirect_hosts=frozenset(policy.allowed_redirect_hosts),
    )


def fetch_recipe_with_deepseek(
    db: Session,
    household_id: int,
    actor_id: int,
    url: str,
    *,
    provider: DeepSeekRecipeFetchProvider | None,
    allow_broader_web: bool = False,
) -> None:
    """Fail closed: DeepSeek Fetch does not return redirect or final-host evidence.

    The Fetch API response contains only a title and Markdown content. It does
    not identify the final URL, redirect chain, or resolved destination, so a
    caller cannot enforce the publisher registry's per-hop host policy. Keep
    this gate explicit until the provider offers verifiable destination data.
    """
    _require_member_and_consent(db, household_id, actor_id)
    authorize_recipe_fetch(db, url, allow_broader_web=allow_broader_web)
    # Keep the provider argument in the contract for a future safe adapter,
    # but never call it while its redirect destination cannot be verified.
    _ = provider
    raise HTTPException(
        status_code=501,
        detail="DEEPSEEK_FETCH_REDIRECT_EVIDENCE_UNAVAILABLE",
    )


def _same_fetch_authorization(
    db: Session,
    original: RecipeFetchAuthorization,
    *,
    allow_broader_web: bool,
) -> bool:
    try:
        current = authorize_recipe_fetch(
            db, original.canonical_url, allow_broader_web=allow_broader_web
        )
    except HTTPException:
        return False
    return current == original


def _header(headers: dict[str, str], name: str) -> str | None:
    for key, value in headers.items():
        if isinstance(key, str) and key.casefold() == name.casefold() and isinstance(value, str):
            return value
    return None


def fetch_recipe_page(
    db: Session,
    household_id: int,
    actor_id: int,
    url: str,
    *,
    transport: PinnedPageTransport,
    allow_broader_web: bool = False,
    robots_policy: RecipeRobotsPolicy | None = None,
) -> FetchedRecipePage:
    """Fetch only under explicit registry rights, validating every pinned hop.

    This is a local transport seam, not a DeepSeek Fetch adapter. The transport
    has no redirect-following method and receives a validated destination IP.
    Each hop requires a current robots decision using the same transport.
    """
    _require_member_and_consent(db, household_id, actor_id)
    authorization = authorize_recipe_fetch(
        db, url, allow_broader_web=allow_broader_web
    )
    if not set(authorization.extraction_methods) & {"json_ld", "full_text"}:
        raise HTTPException(status_code=403, detail="RECIPE_FETCH_METHOD_NOT_AUTHORIZED")
    chain = [authorization.canonical_url]
    addresses_by_host: dict[str, Sequence[str]] = {}

    while True:
        _require_member_and_consent(db, household_id, actor_id)
        if not _same_fetch_authorization(
            db, authorization, allow_broader_web=allow_broader_web
        ):
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_NOT_AUTHORIZED")
        current_url = chain[-1]
        host = urlsplit(current_url).hostname
        if host is None:
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_DESTINATION_BLOCKED")
        if host not in authorization.allowed_hosts and host not in authorization.allowed_redirect_hosts:
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_DESTINATION_BLOCKED")
        if robots_policy is None and host != WIKIMEDIA_ROBOTS_HOST:
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_ROBOTS_UNSUPPORTED_HOST")
        if robots_policy is None:
            parts = urlsplit(current_url)
            if not parts.path.startswith("/wiki/Cookbook:") or parts.query:
                raise HTTPException(status_code=403, detail="RECIPE_FETCH_PATH_NOT_REVIEWED")
        if host not in addresses_by_host:
            try:
                addresses_by_host[host] = tuple(transport.resolve(host))
            except Exception:
                raise HTTPException(status_code=502, detail="RECIPE_FETCH_UNAVAILABLE") from None
        try:
            validated = validate_redirect_hops(
                set(authorization.allowed_hosts),
                set(authorization.allowed_redirect_hosts),
                chain,
                {key: list(values) for key, values in addresses_by_host.items()},
            )
        except (TypeError, ValueError):
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_DESTINATION_BLOCKED") from None
        pinned_ip = validated[-1][1][0]
        try:
            original_agent = transport.user_agent
            policy = wikimedia_robots_allowed if robots_policy is None else robots_policy
            decision = policy(current_url, transport=transport)
        except Exception:
            raise HTTPException(status_code=503, detail="RECIPE_FETCH_ROBOTS_UNAVAILABLE") from None
        if decision is not True:
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_ROBOTS_DENIED")
        # Consent and source permissions can change while robots.txt is fetched.
        _require_member_and_consent(db, household_id, actor_id)
        if not _same_fetch_authorization(db, authorization, allow_broader_web=allow_broader_web):
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_NOT_AUTHORIZED")
        try:
            agent_changed = transport.user_agent != original_agent
        except Exception:
            raise HTTPException(status_code=503, detail="RECIPE_FETCH_ROBOTS_UNAVAILABLE") from None
        if agent_changed:
            raise HTTPException(status_code=503, detail="RECIPE_FETCH_ROBOTS_UNAVAILABLE")
        try:
            response = transport.fetch_once_pinned(
                current_url,
                connect_ip=pinned_ip,
                timeout_seconds=PROVIDER_TIMEOUT_SECONDS,
                max_bytes=MAX_FETCH_BYTES,
            )
        except Exception:
            raise HTTPException(status_code=502, detail="RECIPE_FETCH_UNAVAILABLE") from None
        if (
            not isinstance(response, PageFetchResponse)
            or type(response.status_code) is not int
            or not isinstance(response.headers, dict)
            or not isinstance(response.body, bytes)
        ):
            raise HTTPException(status_code=502, detail="RECIPE_FETCH_UNAVAILABLE")

        if response.status_code in {301, 302, 303, 307, 308}:
            location = _header(response.headers, "location")
            if not location or len(chain) >= MAX_REDIRECT_URLS:
                raise HTTPException(status_code=502, detail="RECIPE_FETCH_REDIRECT_LIMIT")
            try:
                next_url = canonical_recipe_url(urljoin(current_url, location))
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=403, detail="RECIPE_FETCH_DESTINATION_BLOCKED") from exc
            next_host = urlsplit(next_url).hostname
            if next_host not in authorization.allowed_hosts | authorization.allowed_redirect_hosts:
                raise HTTPException(status_code=403, detail="RECIPE_FETCH_DESTINATION_BLOCKED")
            chain.append(next_url)
            continue

        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="RECIPE_FETCH_UNAVAILABLE")
        if len(response.body) > MAX_FETCH_BYTES:
            raise HTTPException(status_code=413, detail="RECIPE_FETCH_RESPONSE_TOO_LARGE")
        content_type = (_header(response.headers, "content-type") or "").split(";", 1)[0].strip().casefold()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise HTTPException(status_code=415, detail="RECIPE_FETCH_CONTENT_TYPE_UNSUPPORTED")
        content_encoding = (_header(response.headers, "content-encoding") or "identity").strip().casefold()
        if content_encoding != "identity":
            raise HTTPException(status_code=415, detail="RECIPE_FETCH_CONTENT_ENCODING_UNSUPPORTED")
        if not _same_fetch_authorization(
            db, authorization, allow_broader_web=allow_broader_web
        ):
            raise HTTPException(status_code=403, detail="RECIPE_FETCH_NOT_AUTHORIZED")
        _require_member_and_consent(db, household_id, actor_id)
        return FetchedRecipePage(
            requested_url=authorization.canonical_url,
            final_url=current_url,
            redirect_chain=tuple(chain),
            content_type=content_type,
            content=response.body,
        )
