"""Fail-closed robots decisions for direct English Wikibooks requests.

Call immediately before each page request, using the same transport and user
agent. This service neither approves a source nor fetches a recipe page.
"""

from __future__ import annotations

import re
from typing import Protocol, Sequence
from urllib.parse import urlsplit

from app.services.source_urls import canonical_recipe_url, validate_redirect_hops


HOST = "en.wikibooks.org"
ROBOTS_URL = f"https://{HOST}/robots.txt"
MAX_ROBOTS_BYTES = 128 * 1024
TIMEOUT_SECONDS = 8.0
_PRODUCT = re.compile(r"([A-Za-z][A-Za-z0-9._-]*)/[A-Za-z0-9._-]+ \([^\r\n()]+\)\Z")
_HEX = re.compile(r"[0-9A-Fa-f]{2}\Z")
_UNRESERVED = frozenset(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


class RobotsPolicyError(Exception):
    """The current policy or destination could not be verified."""


class RobotsResponse(Protocol):
    status_code: int
    headers: dict[str, str]
    body: bytes


class RobotsTransport(Protocol):
    @property
    def user_agent(self) -> str: ...

    def resolve(self, hostname: str) -> Sequence[str]: ...

    def fetch_once_pinned(
        self, url: str, *, connect_ip: str, timeout_seconds: float, max_bytes: int
    ) -> RobotsResponse: ...


def _normalize_path(value: str) -> str:
    """Normalize UTF-8 and percent encodings while retaining encoded reserved bytes."""
    result: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        if char == "%":
            pair = value[index + 1:index + 3]
            if not _HEX.fullmatch(pair):
                raise RobotsPolicyError("Malformed robots path")
            byte = int(pair, 16)
            result.append(chr(byte) if byte in _UNRESERVED else f"%{byte:02X}")
            index += 3
        elif ord(char) > 127:
            result.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
            index += 1
        elif ord(char) < 33 or ord(char) == 127:
            raise RobotsPolicyError("Invalid robots path")
        else:
            result.append(char)
            index += 1
    return "".join(result)


def _rules(text: str, product: str) -> list[tuple[bool, str]]:
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    rules_started = False
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            raise RobotsPolicyError("Malformed robots policy")
        name, value = (part.strip() for part in line.split(":", 1))
        name = name.casefold()
        if name == "user-agent":
            if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise RobotsPolicyError("Malformed robots user agent")
            if rules_started:
                groups.append((agents, rules))
                agents, rules, rules_started = [], [], False
            agents.append(value.casefold())
        elif name in {"allow", "disallow"}:
            if not agents:
                raise RobotsPolicyError("Robots rule has no user agent")
            rules_started = True
            if value:
                if not value.startswith("/"):
                    raise RobotsPolicyError("Malformed robots rule")
                rules.append((name == "allow", value))
    if agents:
        groups.append((agents, rules))
    if not groups:
        raise RobotsPolicyError("Empty robots policy")
    for group_agents, _ in groups:
        for candidate in group_agents:
            if "*" in candidate and candidate != "*":
                # A wildcard inside an agent name is not an RFC 9309 product
                # token. If it could name this client, do not guess whether the
                # publisher intended the group to apply.
                matches, _ = _rule_match(candidate + "$", product.casefold())
                if matches:
                    raise RobotsPolicyError("Ambiguous robots user-agent wildcard")
    matched = [rules for agents, rules in groups if product.casefold() in agents]
    if not matched:
        matched = [rules for agents, rules in groups if "*" in agents]
    return [rule for group in matched for rule in group]


def _rule_match(pattern: str, path: str) -> tuple[bool, int]:
    anchored = pattern.endswith("$")
    pattern = pattern[:-1] if anchored else pattern
    pieces = pattern.split("*")
    normalized = [_normalize_path(piece) for piece in pieces]
    # Percent escapes represent one octet for specificity.
    size = sum(len(re.sub(r"%[0-9A-F]{2}", "x", piece)) for piece in normalized)
    if not path.startswith(normalized[0]):
        return False, size
    position = len(normalized[0])
    for piece in normalized[1:-1]:
        found = path.find(piece, position)
        if found < 0:
            return False, size
        position = found + len(piece)
    if len(normalized) == 1:
        return (not anchored or position == len(path)), size
    last = normalized[-1]
    if anchored:
        return path.endswith(last) and len(path) - len(last) >= position, size
    return path.find(last, position) >= 0, size


def wikimedia_robots_allowed(target_url: str, *, transport: RobotsTransport) -> bool:
    """Return whether current robots rules permit a canonical Wikibooks URL.

    Raises RobotsPolicyError on any retrieval, parsing, identity, or destination
    failure. The caller must treat both False and this exception as denial.
    No policy is cached, and HTTP redirects for robots.txt are refused.
    """
    try:
        canonical = canonical_recipe_url(target_url)
        if canonical != target_url or urlsplit(canonical).hostname != HOST:
            raise RobotsPolicyError("Unsupported Wikibooks URL")
        agent = transport.user_agent
        match = _PRODUCT.fullmatch(agent) if isinstance(agent, str) and agent.isascii() else None
        if match is None or len(agent) > 512 or any(ord(c) < 32 or ord(c) == 127 for c in agent):
            raise RobotsPolicyError("Invalid transport user agent")
        addresses = tuple(transport.resolve(HOST))
        validated = validate_redirect_hops({HOST}, set(), [ROBOTS_URL], {HOST: list(addresses)})
        response = transport.fetch_once_pinned(
            ROBOTS_URL, connect_ip=validated[0][1][0],
            timeout_seconds=TIMEOUT_SECONDS, max_bytes=MAX_ROBOTS_BYTES,
        )
        if transport.user_agent != agent:
            raise RobotsPolicyError("Transport user agent changed")
        if (type(response.status_code) is not int or response.status_code != 200
                or not isinstance(response.headers, dict) or not isinstance(response.body, bytes)
                or len(response.body) > MAX_ROBOTS_BYTES):
            raise RobotsPolicyError("Robots retrieval failed")
        headers: dict[str, str] = {}
        for key, value in response.headers.items():
            if not isinstance(key, str) or not isinstance(value, str) or key.casefold() in headers:
                raise RobotsPolicyError("Ambiguous robots headers")
            headers[key.casefold()] = value
        content_type = headers.get("content-type")
        if not isinstance(content_type, str) or content_type.split(";", 1)[0].strip().casefold() != "text/plain":
            raise RobotsPolicyError("Unsupported robots content type")
        encoding = headers.get("content-encoding", "identity")
        if not isinstance(encoding, str) or encoding.strip().casefold() != "identity":
            raise RobotsPolicyError("Unsupported robots encoding")
        text = response.body.decode("utf-8-sig", errors="strict")
        rules = _rules(text, match.group(1))
        parsed = urlsplit(canonical)
        path = _normalize_path(parsed.path + ("?" + parsed.query if parsed.query else ""))
        matches = [(size, allow) for allow, rule in rules
                   for matched, size in [_rule_match(rule, path)] if matched]
        return max(matches)[1] if matches else True
    except RobotsPolicyError:
        raise
    except Exception:
        raise RobotsPolicyError("Robots policy unavailable") from None
