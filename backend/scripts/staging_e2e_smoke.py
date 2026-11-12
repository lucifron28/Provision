"""Bounded API smoke checks for one isolated Provision staging test account."""

from __future__ import annotations

import os
import secrets
import sys
import time
import uuid
from urllib.parse import urlsplit

import httpx


def _api_base_url() -> str:
    value = os.environ.get("PROVISION_STAGING_API_BASE_URL", "").strip()
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path.rstrip("/") != "/api/v1"
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "PROVISION_STAGING_API_BASE_URL must be an HTTPS /api/v1 URL without credentials"
        )
    return value.rstrip("/")


def _fixture_token() -> str:
    token = os.environ.get("PROVISION_STAGING_FIXTURE_TOKEN", "")
    if not token:
        raise RuntimeError("PROVISION_STAGING_FIXTURE_TOKEN is required for scoped fixture cleanup")
    return token


def _request(client: httpx.Client, method: str, path: str, **kwargs) -> httpx.Response:
    response = client.request(method, f"{_api_base_url()}{path}", **kwargs)
    if response.is_error:
        raise RuntimeError(f"Staging API request {method} {path} returned HTTP {response.status_code}")
    return response


def _login(client: httpx.Client, email: str, password: str) -> str:
    response = _request(
        client,
        "POST",
        "/auth/login",
        json={"email": email, "password": password},
    )
    access_token = response.json().get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise RuntimeError("Staging login did not return an access token")
    return access_token


def _register(client: httpx.Client, email: str, password: str) -> dict:
    response = _request(
        client,
        "POST",
        "/auth/register",
        json={"email": email, "password": password, "display_name": "Provision E2E"},
    )
    user = response.json()
    if not isinstance(user.get("default_household_id"), int):
        raise RuntimeError("Staging registration did not create a default test household")
    return user


def _cleanup_account(client: httpx.Client, email: str, password: str) -> None:
    try:
        token = _login(client, email, password)
    except RuntimeError as exc:
        if "returned HTTP 401" in str(exc):
            return
        raise
    response = client.delete(
        f"{_api_base_url()}/auth/staging-test-account",
        headers={
            "Authorization": f"Bearer {token}",
            "X-Staging-Test-Token": _fixture_token(),
        },
        timeout=20,
    )
    if response.status_code != 204:
        raise RuntimeError(
            "Staging test-account cleanup refused or failed; it only deletes an empty, owned synthetic household "
            f"(HTTP {response.status_code})"
        )


def prepare() -> None:
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        raise RuntimeError("Run prepare only in the staging GitHub Actions job")
    _fixture_token()
    run_id = uuid.uuid4().hex
    email = f"provision-e2e+{run_id}@example.com"
    password = secrets.token_urlsafe(32)
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        user = _register(client, email, password)
    # Mask values before later steps can print an unexpected command or failure.
    print(f"::add-mask::{email}")
    print(f"::add-mask::{password}")
    with open(env_file, "a", encoding="utf-8") as output:
        output.write(f"PROVISION_STAGING_TEST_EMAIL={email}\n")
        output.write(f"PROVISION_STAGING_TEST_PASSWORD={password}\n")
        output.write(f"PROVISION_STAGING_TEST_HOUSEHOLD_ID={user['default_household_id']}\n")
    print(f"Prepared a synthetic staging account and household {user['default_household_id']}.")


def preflight() -> None:
    expected_commit = os.environ.get("PROVISION_EXPECTED_RENDER_COMMIT", "").lower()
    if len(expected_commit) != 40 or any(character not in "0123456789abcdef" for character in expected_commit):
        raise RuntimeError("PROVISION_EXPECTED_RENDER_COMMIT must be a full 40-character commit SHA")
    base_url = _api_base_url()
    parsed = urlsplit(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    health = ready = None
    with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False) as client:
        for attempt in range(5):
            try:
                health = client.get(f"{origin}/health")
                ready = client.get(f"{origin}/ready")
            except httpx.HTTPError:
                if attempt == 4:
                    raise RuntimeError("Render staging did not respond within five bounded health attempts") from None
            else:
                if health.status_code == 200 and ready.status_code == 200:
                    break
            if attempt < 4:
                time.sleep(5)
    if health is None or ready is None or health.status_code != 200 or ready.status_code != 200:
        health_status = health.status_code if health is not None else "no response"
        ready_status = ready.status_code if ready is not None else "no response"
        raise RuntimeError(
            f"Staging health/readiness checks failed after five bounded attempts (HTTP {health_status}/{ready_status})"
        )
    health_data = health.json()
    if health_data.get("deployment") != "staging":
        raise RuntimeError("The configured service is not marked as staging")
    if health_data.get("revision") != expected_commit:
        raise RuntimeError("Render is not serving the requested commit; deploy the intended SHA manually first")
    print("Staging is healthy, database-ready, and serving the requested commit.")


def api_smoke() -> None:
    email = os.environ["PROVISION_STAGING_TEST_EMAIL"]
    password = os.environ["PROVISION_STAGING_TEST_PASSWORD"]
    household_id = int(os.environ["PROVISION_STAGING_TEST_HOUSEHOLD_ID"])
    run_id = uuid.uuid4().hex
    second_email = f"provision-e2e+{run_id}@example.com"
    second_password = secrets.token_urlsafe(32)
    product_id: int | None = None
    shopping_id: int | None = None

    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        first_token = _login(client, email, password)
        second_user = _register(client, second_email, second_password)
        second_token = _login(client, second_email, second_password)
        first_headers = {
            "Authorization": f"Bearer {first_token}",
            "X-Household-ID": str(household_id),
        }
        second_headers = {
            "Authorization": f"Bearer {second_token}",
            "X-Household-ID": str(second_user["default_household_id"]),
        }
        product_name = f"Synthetic pantry item {run_id}"
        try:
            created = _request(
                client,
                "POST",
                "/products/",
                headers=first_headers,
                json={"name": product_name, "category": "E2E test"},
            ).json()
            product_id = created["id"]
            updated_name = f"{product_name} edited"
            updated = _request(
                client,
                "PATCH",
                f"/products/{product_id}",
                headers=first_headers,
                json={"name": updated_name},
            ).json()
            assert updated["name"] == updated_name
            listed = _request(client, "GET", "/products/", headers=first_headers).json()
            assert any(item["id"] == product_id and item["name"] == updated_name for item in listed)

            denied = client.get(
                f"{_api_base_url()}/products/",
                headers={
                    **second_headers,
                    "X-Household-ID": str(household_id),
                },
                timeout=20,
            )
            assert denied.status_code == 403, "A second test user accessed the first household"

            shopping_name = f"Synthetic shopping item {run_id}"
            shopping = _request(
                client,
                "POST",
                "/shopping-list/",
                headers=first_headers,
                json={"name": shopping_name, "quantity": "0.750000", "unit": "count"},
            ).json()
            shopping_id = shopping["id"]
            assert float(shopping["quantity"]) == 0.75
            read_back = _request(client, "GET", "/shopping-list/", headers=first_headers).json()
            assert any(
                item["id"] == shopping_id and float(item["quantity"]) == 0.75
                for item in read_back
            )
            _request(client, "PATCH", f"/shopping-list/{shopping_id}", headers=first_headers,
                     json={"quantity": "0.500000"})
            updated_list = _request(client, "GET", "/shopping-list/", headers=first_headers).json()
            assert any(
                item["id"] == shopping_id and float(item["quantity"]) == 0.5
                for item in updated_list
            )
        finally:
            if shopping_id is not None:
                client.delete(
                    f"{_api_base_url()}/shopping-list/{shopping_id}",
                    headers=first_headers,
                    timeout=20,
                )
            if product_id is not None:
                client.delete(
                    f"{_api_base_url()}/products/{product_id}",
                    headers=first_headers,
                    timeout=20,
                )
            _cleanup_account(client, second_email, second_password)

    print(
        "Staging API smoke passed: registration/login, household authorization, product create/edit/read/delete, "
        "and exact shopping quantity persistence."
    )


def cleanup() -> None:
    email = os.environ.get("PROVISION_STAGING_TEST_EMAIL")
    password = os.environ.get("PROVISION_STAGING_TEST_PASSWORD")
    if not email or not password:
        print("No staging E2E account was created; nothing to clean up.")
        return
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        _cleanup_account(client, email, password)
    print("The owned, empty synthetic staging household was cleaned up.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in {"preflight", "prepare", "api-smoke", "cleanup"}:
        raise SystemExit("Usage: staging_e2e_smoke.py preflight|prepare|api-smoke|cleanup")
    try:
        {
            "preflight": preflight,
            "prepare": prepare,
            "api-smoke": api_smoke,
            "cleanup": cleanup,
        }[sys.argv[1]]()
    except (httpx.HTTPError, KeyError, RuntimeError, AssertionError, ValueError) as error:
        # Do not emit request bodies, credentials, prompts, or database URLs.
        print(f"Staging E2E failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
