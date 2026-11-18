"""Verify one real Pip Chat provider response with a run-owned synthetic account."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import httpx

from app.core.staging_target import (
    validate_staging_api_base_url,
    verify_staging_deployment,
)
from app.schemas.pip_chat import PIP_CHAT_POLICY_VERSION

CONFIRMATION = "RUN_ONE_SYNTHETIC_PIP_CHAT_REQUEST"
DEMO_PRODUCT_NAME = "Fresh Kangkong"


def _request(client: httpx.Client, method: str, base_url: str, path: str, **kwargs):
    response = client.request(method, f"{base_url}{path}", **kwargs)
    if response.is_error:
        raise RuntimeError(f"Staging request {method} {path} returned HTTP {response.status_code}")
    return response


def _snapshot(client: httpx.Client, base_url: str, headers: dict[str, str]) -> dict[str, object]:
    return {
        "products": _request(client, "GET", base_url, "/products/", headers=headers).json(),
        "batches": _request(client, "GET", base_url, "/batches/", headers=headers).json(),
        "recipes": _request(client, "GET", base_url, "/recipes/", headers=headers).json(),
        "shopping": _request(client, "GET", base_url, "/shopping-list/", headers=headers).json(),
    }


def _share_product_id(product_id: int) -> None:
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        raise RuntimeError("The synthetic product can only be prepared by the GitHub Actions workflow")
    with open(env_file, "a", encoding="utf-8") as output:
        output.write(f"PROVISION_STAGING_TEST_PRODUCT_ID={product_id}\n")
        output.write(f"PROVISION_STAGING_TEST_PRODUCT_NAME={DEMO_PRODUCT_NAME}\n")


def run_one_request() -> None:
    if os.environ.get("PROVISION_LIVE_DEEPSEEK_ENABLED") != "true":
        raise RuntimeError("Live DeepSeek testing is not enabled for this workflow")
    if os.environ.get("PROVISION_LIVE_DEEPSEEK_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError("The exact one-request Pip Chat confirmation is required")

    try:
        base_url = validate_staging_api_base_url(os.environ.get("PROVISION_STAGING_API_BASE_URL", ""))
    except ValueError:
        raise RuntimeError("A valid HTTPS Render staging API URL is required") from None

    expected_commit = os.environ.get("PROVISION_EXPECTED_RENDER_COMMIT", "")
    email = os.environ.get("PROVISION_STAGING_TEST_EMAIL", "")
    password = os.environ.get("PROVISION_STAGING_TEST_PASSWORD", "")
    household_id = os.environ.get("PROVISION_STAGING_TEST_HOUSEHOLD_ID", "")
    if not all((expected_commit, email, password, household_id)):
        raise RuntimeError("The expected staging commit and run-owned synthetic account are required")

    with httpx.Client(timeout=45, follow_redirects=False, trust_env=False) as client:
        verify_staging_deployment(client, base_url, expected_commit)
        login = _request(
            client,
            "POST",
            base_url,
            "/auth/login",
            json={"email": email, "password": password},
        ).json()
        token = login.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("Staging login did not return an access token")

        headers = {
            "Authorization": f"Bearer {token}",
            "X-Household-ID": household_id,
        }

        product = _request(
            client,
            "POST",
            base_url,
            "/products/",
            headers=headers,
            json={"name": DEMO_PRODUCT_NAME, "category": "Fresh Produce", "unit": "kg"},
        ).json()
        product_id = product.get("id")
        if not isinstance(product_id, int) or product_id <= 0:
            raise RuntimeError("The synthetic household product could not be created")
        _request(
            client,
            "POST",
            base_url,
            "/batches/",
            headers=headers,
            json={
                "product_id": product_id,
                "original_quantity": "0.5",
                "unit_price": "60.00",
                "expiration_date": (date.today() + timedelta(days=2)).isoformat(),
            },
        )
        _share_product_id(product_id)

        consent = _request(client, "GET", base_url, "/privacy/pip-chat-consent", headers=headers).json()
        if consent.get("provider_enabled") is not True:
            raise RuntimeError("Pip Chat is disabled on staging; no provider request was sent")
        if consent.get("allergy_sharing_granted") is True:
            raise RuntimeError("The synthetic account unexpectedly granted separate allergy sharing")

        if consent.get("all_active_members_chat_granted") is not True:
            consent = _request(
                client,
                "PUT",
                base_url,
                "/privacy/pip-chat-consent",
                headers=headers,
                json={
                    "purpose": "pip_chat_v1",
                    "policy_version": PIP_CHAT_POLICY_VERSION,
                    "granted": True,
                },
            ).json()
        if consent.get("all_active_members_chat_granted") is not True:
            raise RuntimeError("The synthetic household did not grant Pip Chat consent")

        before = _snapshot(client, base_url, headers)
        result = _request(
            client,
            "POST",
            base_url,
            "/pip/chat",
            headers=headers,
            json={
                "message": "How much fresh kangkong do I have, and what recipes could use it?",
                "context": {"kind": "product", "id": product_id},
            },
        ).json()

        model = result.get("model")
        usage = result.get("usage", {})
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        reply = result.get("reply")
        if not isinstance(model, str) or not model.startswith("deepseek-"):
            raise RuntimeError("Pip Chat did not report a DeepSeek model")
        if not isinstance(reply, str) or not reply.strip() or result.get("local_guidance") is True:
            raise RuntimeError("Pip Chat did not return a provider-generated response")
        if not isinstance(total_tokens, int) or total_tokens <= 0 or total_tokens > 4096:
            raise RuntimeError("Pip Chat returned invalid provider token usage")
        facts = result.get("facts", [])
        if not isinstance(facts, list) or not any(
            isinstance(fact, dict)
            and fact.get("kind") == "inventory"
            and DEMO_PRODUCT_NAME.casefold() in str(fact.get("label", "")).casefold()
            for fact in facts
        ):
            raise RuntimeError("Pip Chat did not return the synthetic household inventory fact")
        if _snapshot(client, base_url, headers) != before:
            raise RuntimeError("Pip Chat changed household products, inventory, recipes, or shopping data")

    print(
        "One live Pip Chat API request passed; "
        f"model={model}, total_tokens={total_tokens}. Response text was withheld from logs."
    )


if __name__ == "__main__":
    try:
        run_one_request()
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        print(f"Live Pip Chat smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
