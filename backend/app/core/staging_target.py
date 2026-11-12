"""Safe target and revision checks for manual staging workflows."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx


def validate_staging_api_base_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        hostname = (parsed.hostname or "").lower()
        port = parsed.port
    except (AttributeError, ValueError):
        raise ValueError("Staging API URL must be an HTTPS Render URL ending in /api/v1") from None

    if (
        parsed.scheme.lower() != "https"
        or not hostname.endswith(".onrender.com")
        or hostname == "onrender.com"
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 443}
        or parsed.path.rstrip("/") != "/api/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Staging API URL must be an HTTPS Render URL ending in /api/v1")

    return f"https://{hostname}/api/v1"


def verify_staging_deployment(
    client,
    base_url: str,
    expected_commit: str,
    *,
    attempts: int = 5,
    retry_delay_seconds: float = 5,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    if attempts < 1:
        raise ValueError("Staging preflight must make at least one bounded attempt")
    normalized_base_url = validate_staging_api_base_url(base_url)
    expected = expected_commit.lower()
    if re.fullmatch(r"[0-9a-f]{40}", expected) is None:
        raise RuntimeError("PROVISION_EXPECTED_RENDER_COMMIT must be a full 40-character commit SHA")

    origin = normalized_base_url.removesuffix("/api/v1")
    health = ready = None
    for attempt in range(attempts):
        try:
            health = client.get(f"{origin}/health")
            ready = client.get(f"{origin}/ready")
        except httpx.HTTPError:
            if attempt == attempts - 1:
                raise RuntimeError(
                    f"Render staging did not respond within {attempts} bounded health attempts"
                ) from None
        else:
            if health.status_code == 200 and ready.status_code == 200:
                break
        if attempt < attempts - 1:
            sleep(retry_delay_seconds)

    if health is None or ready is None or health.status_code != 200 or ready.status_code != 200:
        health_status = health.status_code if health is not None else "no response"
        ready_status = ready.status_code if ready is not None else "no response"
        raise RuntimeError(
            f"Staging health/readiness checks failed after bounded attempts (HTTP {health_status}/{ready_status})"
        )

    try:
        health_data = health.json()
        ready_data = ready.json()
    except (TypeError, ValueError):
        raise RuntimeError("Render health or readiness response was not valid JSON") from None
    if not isinstance(health_data, dict) or health_data.get("deployment") != "staging":
        raise RuntimeError("The configured service is not marked as staging")
    if str(health_data.get("revision") or "").lower() != expected:
        raise RuntimeError("Render is not serving the requested commit; deploy the intended SHA manually first")
    if not isinstance(ready_data, dict) or ready_data.get("status") != "ready":
        raise RuntimeError("Render staging database readiness check did not report ready")
