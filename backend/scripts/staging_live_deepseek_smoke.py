"""Make exactly one explicitly confirmed DeepSeek request to Provision staging."""

from __future__ import annotations

import os
import sys

import httpx
from pydantic import ValidationError

from app.core.staging_target import validate_staging_api_base_url, verify_staging_deployment
from app.schemas.ai_recipe import AIRecipeProposal


CONFIRMATION = "RUN_ONE_SYNTHETIC_DEEPSEEK_REQUEST"


def _request(client: httpx.Client, method: str, base_url: str, path: str, **kwargs):
    response = client.request(method, f"{base_url}{path}", **kwargs)
    if response.is_error:
        raise RuntimeError(f"Staging request {method} {path} returned HTTP {response.status_code}")
    return response


def run_one_request() -> None:
    if os.environ.get("PROVISION_LIVE_DEEPSEEK_ENABLED") != "true":
        raise RuntimeError("Live DeepSeek testing remains disabled until staging is explicitly validated")
    if os.environ.get("PROVISION_LIVE_DEEPSEEK_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError("Live DeepSeek requires the exact one-request confirmation")

    try:
        base_url = validate_staging_api_base_url(os.environ.get("PROVISION_STAGING_API_BASE_URL", ""))
    except ValueError:
        raise RuntimeError("A valid HTTPS Render staging API URL is required") from None
    expected_commit = os.environ.get("PROVISION_EXPECTED_RENDER_COMMIT", "")
    email = os.environ.get("PROVISION_STAGING_TEST_EMAIL", "")
    password = os.environ.get("PROVISION_STAGING_TEST_PASSWORD", "")
    household_id = os.environ.get("PROVISION_STAGING_TEST_HOUSEHOLD_ID", "")
    if not all((email, password, household_id)):
        raise RuntimeError("A staging API URL and run-specific synthetic account are required")

    # Trust no proxy from the runner environment and do not configure retries.
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

        consent = _request(client, "GET", base_url, "/privacy/consent", headers=headers).json()
        if not consent.get("provider_enabled"):
            raise RuntimeError("DeepSeek is disabled on staging; no provider request was sent")

        before = {
            "products": _request(client, "GET", base_url, "/products/", headers=headers).json(),
            "batches": _request(client, "GET", base_url, "/batches/", headers=headers).json(),
            "recipes": _request(client, "GET", base_url, "/recipes/", headers=headers).json(),
            "shopping": _request(client, "GET", base_url, "/shopping-list/", headers=headers).json(),
        }
        policy_version = consent.get("policy_version")
        if not isinstance(policy_version, str) or not policy_version:
            raise RuntimeError("Staging consent policy version is missing")
        consent_granted = False
        try:
            _request(
                client,
                "PUT",
                base_url,
                "/privacy/consent",
                headers=headers,
                json={"policy_version": policy_version, "granted": True},
            )
            consent_granted = True

            # This is the only DeepSeek-backed API call in this script. The dish is
            # synthetic; the app's privacy policy excludes household data from it.
            response = _request(
                client,
                "POST",
                base_url,
                "/ai-recipes/generate",
                headers=headers,
                json={"dish": "Filipino garlic rice"},
            ).json()
            if response.get("provenance") != "AI_ORIGINAL":
                raise RuntimeError("The live proposal did not carry AI_ORIGINAL provenance")
            try:
                proposal = AIRecipeProposal.model_validate(response.get("proposal"))
            except ValidationError:
                raise RuntimeError("Live provider output did not match the recipe schema") from None
            if not proposal.ingredients or not proposal.steps:
                raise RuntimeError("Live provider output was incomplete")

            safety = response.get("safety")
            if not isinstance(safety, dict) or safety.get("decision") not in {
                "eligible",
                "blocked",
                "review_required",
            }:
                raise RuntimeError("The deterministic safety evaluator returned an invalid decision")
            if len(safety.get("ingredients", [])) != len(proposal.ingredients):
                raise RuntimeError("The safety evaluator did not assess every generated ingredient")

            usage = response.get("usage", {})
            total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
            if not isinstance(total_tokens, int) or total_tokens <= 0 or total_tokens > 2048:
                raise RuntimeError("The one-call response exceeded the configured smoke-test token ceiling")

            after = {
                "products": _request(client, "GET", base_url, "/products/", headers=headers).json(),
                "batches": _request(client, "GET", base_url, "/batches/", headers=headers).json(),
                "recipes": _request(client, "GET", base_url, "/recipes/", headers=headers).json(),
                "shopping": _request(client, "GET", base_url, "/shopping-list/", headers=headers).json(),
            }
            if before != after:
                raise RuntimeError("The generated proposal mutated household inventory, recipes, or shopping data")
        finally:
            if consent_granted:
                client.delete(
                    f"{base_url}/privacy/consent",
                    headers=headers,
                    timeout=20,
                )

    print(
        "One live DeepSeek request passed schema, provenance, deterministic safety, token-ceiling, "
        f"and no-write checks; tokens={total_tokens}, safety={safety['decision']}."
    )


if __name__ == "__main__":
    try:
        run_one_request()
    except (httpx.HTTPError, RuntimeError, ValueError) as error:
        # Do not include prompt text, response content, account credentials, or URLs.
        print(f"Live DeepSeek smoke failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
