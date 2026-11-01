"""Robots decision helper for reviewed publisher recipe fetch boundaries.

Evaluates publisher robots.txt rules under RFC 9309 using the pinned transport
and identifying user agent.
"""

from __future__ import annotations

from typing import Protocol, Sequence
from urllib.parse import urlsplit

from app.services.source_urls import canonical_recipe_url, validate_redirect_hops
from app.services.wikimedia_robots import (
    MAX_ROBOTS_BYTES,
    TIMEOUT_SECONDS,
    _PRODUCT,
    _normalize_path,
    _rule_match,
    _rules,
    RobotsPolicyError,
    RobotsResponse,
    RobotsTransport,
)


def publisher_robots_allowed(target_url: str, *, transport: RobotsTransport) -> bool:
    """Return whether current robots.txt rules permit fetching the target recipe URL.

    - Resolves and pins robots.txt destination IP.
    - Honors RFC 9309 status: HTTP 404/410 allows access.
    - Matches User-agent specific rules, falling back to wildcard '*'.
    - Raises RobotsPolicyError on unexpected errors or disallowed content types.
    """
    try:
        canonical = canonical_recipe_url(target_url)
        host = urlsplit(canonical).hostname
        if not host:
            raise RobotsPolicyError("Missing hostname for robots decision")

        agent = transport.user_agent
        match = _PRODUCT.fullmatch(agent) if isinstance(agent, str) and agent.isascii() else None
        if match is None or len(agent) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in agent):
            raise RobotsPolicyError("Invalid transport user agent")

        robots_url = f"https://{host}/robots.txt"
        addresses = tuple(transport.resolve(host))
        validated = validate_redirect_hops({host}, set(), [robots_url], {host: list(addresses)})

        response = transport.fetch_once_pinned(
            robots_url,
            connect_ip=validated[0][1][0],
            timeout_seconds=TIMEOUT_SECONDS,
            max_bytes=MAX_ROBOTS_BYTES,
        )

        if transport.user_agent != agent:
            raise RobotsPolicyError("Transport user agent changed")

        # Under RFC 9309 Section 2.3.1.2: 404 / 410 (Not Found / Gone) means unrestricted access
        if response.status_code in {404, 410}:
            return True

        if response.status_code != 200 or not isinstance(response.body, bytes):
            raise RobotsPolicyError("Robots retrieval failed")

        if len(response.body) > MAX_ROBOTS_BYTES:
            raise RobotsPolicyError("Robots response too large")

        headers: dict[str, str] = {}
        for key, value in response.headers.items():
            if not isinstance(key, str) or not isinstance(value, str) or key.casefold() in headers:
                raise RobotsPolicyError("Ambiguous robots headers")
            headers[key.casefold()] = value

        content_type = headers.get("content-type")
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().casefold() != "text/plain":
            raise RobotsPolicyError("Unsupported robots content type")

        text = response.body.decode("utf-8-sig", errors="strict")
        rules = _rules(text, match.group(1))

        parsed = urlsplit(canonical)
        path = _normalize_path(parsed.path + ("?" + parsed.query if parsed.query else ""))
        matches = [
            (size, allow)
            for allow, rule in rules
            for matched, size in [_rule_match(rule, path)]
            if matched
        ]
        return max(matches)[1] if matches else True
    except RobotsPolicyError:
        raise
    except Exception:
        raise RobotsPolicyError("Robots policy unavailable") from None
