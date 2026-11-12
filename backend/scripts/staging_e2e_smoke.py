"""Bounded API smoke checks for one isolated Provision staging test account."""

from __future__ import annotations

import os
import secrets
import sys
import uuid
from datetime import date, timedelta
from decimal import Decimal

import httpx

from app.core.staging_target import validate_staging_api_base_url, verify_staging_deployment


def _api_base_url() -> str:
    value = os.environ.get("PROVISION_STAGING_API_BASE_URL", "").strip()
    try:
        return validate_staging_api_base_url(value)
    except ValueError:
        raise RuntimeError("PROVISION_STAGING_API_BASE_URL must be an HTTPS Render /api/v1 URL") from None


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


def _remember_account(email: str, password: str, *, slot: str = "", household_id: int | None = None) -> None:
    env_file = os.environ.get("GITHUB_ENV")
    if not env_file:
        raise RuntimeError("Synthetic staging accounts can only be created by the GitHub Actions workflow")

    suffix = f"_{slot}" if slot else ""
    lines = []
    if household_id is None:
        print(f"::add-mask::{email}")
        print(f"::add-mask::{password}")
        lines.extend(
            [
                f"PROVISION_STAGING_TEST_EMAIL{suffix}={email}",
                f"PROVISION_STAGING_TEST_PASSWORD{suffix}={password}",
            ]
        )
    else:
        lines.append(f"PROVISION_STAGING_TEST_HOUSEHOLD_ID{suffix}={household_id}")
    with open(env_file, "a", encoding="utf-8") as output:
        output.write("\n".join(lines) + "\n")


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
            "Staging test-account cleanup refused or failed; it only deletes a unique single-member synthetic "
            "household and its scoped data "
            f"(HTTP {response.status_code})"
        )


def _expect(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def prepare() -> None:
    if not os.environ.get("GITHUB_ENV"):
        raise RuntimeError("Run prepare only in the staging GitHub Actions job")
    preflight()
    _fixture_token()
    run_id = uuid.uuid4().hex
    email = f"provision-e2e+{run_id}@example.com"
    password = secrets.token_urlsafe(32)
    _remember_account(email, password)
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        user = _register(client, email, password)
    _remember_account(email, password, household_id=user["default_household_id"])
    print(f"Prepared a synthetic staging account and household {user['default_household_id']}.")


def preflight() -> None:
    expected_commit = os.environ.get("PROVISION_EXPECTED_RENDER_COMMIT", "").lower()
    base_url = _api_base_url()
    with httpx.Client(timeout=httpx.Timeout(30, connect=10), follow_redirects=False, trust_env=False) as client:
        verify_staging_deployment(client, base_url, expected_commit)
    print("Staging is healthy, database-ready, and serving the requested commit.")


def api_smoke() -> None:
    preflight()
    email = os.environ["PROVISION_STAGING_TEST_EMAIL"]
    password = os.environ["PROVISION_STAGING_TEST_PASSWORD"]
    household_id = int(os.environ["PROVISION_STAGING_TEST_HOUSEHOLD_ID"])
    run_id = uuid.uuid4().hex
    second_email = f"provision-e2e+{run_id}@example.com"
    second_password = secrets.token_urlsafe(32)

    product_name = f"Synthetic pantry item {run_id}"
    second_registered = False
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        first_token = _login(client, email, password)
        primary_households = _request(
            client, "GET", "/households/", headers={"Authorization": f"Bearer {first_token}"}
        ).json()
        _expect(
            len(primary_households) == 1
            and primary_households[0]["id"] == household_id
            and primary_households[0]["is_default"],
            "The registered account did not retain its isolated default household",
        )
        try:
            _remember_account(second_email, second_password, slot="2")
            second_user = _register(client, second_email, second_password)
            second_registered = True
            _remember_account(
                second_email,
                second_password,
                slot="2",
                household_id=second_user["default_household_id"],
            )
            second_token = _login(client, second_email, second_password)
            first_headers = {
                "Authorization": f"Bearer {first_token}",
                "X-Household-ID": str(household_id),
            }
            second_headers = {
                "Authorization": f"Bearer {second_token}",
                "X-Household-ID": str(second_user["default_household_id"]),
            }
            current_household = _request(
                client, "GET", "/households/current", headers=first_headers
            ).json()
            _expect(current_household.get("id") == household_id, "Household selection returned the wrong household")

            recommendations = _request(
                client,
                "POST",
                "/recipes/recommendations",
                headers=first_headers,
                json={"mode": "all", "priority": "pantry_first"},
            ).json()
            _expect(
                recommendations.get("provider_enabled") is False,
                "Cook with Pip recommendations unexpectedly enabled a provider",
            )

            safety = _request(
                client,
                "POST",
                "/food-safety/evaluate",
                headers=first_headers,
                json={
                    "recipe_servings": "1",
                    "servings": "1",
                    "requirements": [{"display_name": "milk", "amount": "1", "unit": "cup"}],
                },
            ).json()
            _expect(
                safety.get("decision") == "review_required",
                "Food safety did not require review when allergy information was absent",
            )

            ingredient_lookup = _request(
                client, "GET", "/ingredients/?query=garlic", headers=first_headers
            ).json()
            ingredient = next(
                (item for item in ingredient_lookup.get("results", []) if item.get("canonical_name") == "garlic"),
                None,
            )
            _expect(ingredient is not None, "The staging ingredient catalog did not return garlic")
            ingredient_id = ingredient["id"]

            created = _request(
                client,
                "POST",
                "/products/",
                headers=first_headers,
                json={"name": product_name, "category": "E2E test", "unit": "g"},
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
            _expect(updated["name"] == updated_name, "Product edit did not persist")
            listed = _request(client, "GET", "/products/", headers=first_headers).json()
            _expect(
                any(item["id"] == product_id and item["name"] == updated_name for item in listed),
                "Product readback did not return the edited product",
            )

            mapping = _request(
                client,
                "PUT",
                f"/ingredients/products/{product_id}/mapping",
                headers=first_headers,
                json={
                    "mode": "DIRECT",
                    "ingredient_id": ingredient_id,
                    "verified": True,
                    "unknown_composition": False,
                    "method": "Synthetic staging label review",
                },
            ).json()
            _expect(mapping.get("version") == 1, "Product ingredient mapping did not persist")
            product_detail = _request(
                client, "GET", f"/products/{product_id}", headers=first_headers
            ).json()
            label = _request(
                client,
                "PUT",
                f"/food-safety/products/{product_id}/label",
                headers=first_headers,
                json={
                    "expected_mapping_version": mapping["version"],
                    "expected_product_updated_at": product_detail["updated_at"],
                    "reviewed": True,
                    "composition_known": True,
                    "declared_allergens": [],
                    "possible_allergens": [],
                    "custom_allergens": [],
                    "source_reference": "Synthetic staging label fixture: garlic",
                },
            ).json()
            _expect(label.get("current_for_product") is True, "Reviewed product label did not persist")

            expiration_date = (date.today() + timedelta(days=30)).isoformat()
            batch = _request(
                client,
                "POST",
                "/batches/",
                headers=first_headers,
                json={
                    "product_id": product_id,
                    "original_quantity": "8",
                    "unit_price": "1.25",
                    "expiration_date": expiration_date,
                },
            ).json()
            _expect(
                batch.get("expiration_date") == expiration_date
                and Decimal(str(batch.get("remaining_quantity"))) == Decimal("8"),
                "Inventory quantity or expiration date did not persist",
            )
            listed_batches = _request(
                client, "GET", f"/batches/?product_id={product_id}", headers=first_headers
            ).json()
            _expect(
                any(item.get("id") == batch["id"] and item.get("expiration_date") == expiration_date
                    for item in listed_batches),
                "Inventory readback did not return the batch expiration date",
            )

            denied = client.get(
                f"{_api_base_url()}/products/",
                headers={
                    **second_headers,
                    "X-Household-ID": str(household_id),
                },
                timeout=20,
            )
            _expect(denied.status_code == 403, "A second test user accessed the first household")
            second_households = _request(
                client, "GET", "/households/", headers={"Authorization": f"Bearer {second_token}"}
            ).json()
            _expect(
                len(second_households) == 1
                and second_households[0]["id"] == second_user["default_household_id"],
                "Household listing exposed another test user's household",
            )

            recipe = _request(
                client,
                "POST",
                "/recipes/",
                headers=first_headers,
                json={
                    "title": f"Synthetic garlic rice {run_id}",
                    "cuisine": "Filipino",
                    "content_permission": "OWNED_OR_PERMISSION_GRANTED",
                    "ph_regions": ["region_unknown"],
                    "servings": "1",
                    "instructions": ["Mix the synthetic ingredients."],
                    "ingredients": [{"ingredient_id": ingredient_id, "amount": "10", "unit": "g"}],
                },
            ).json()
            detail = _request(
                client, "GET", f"/recipes/{recipe['id']}", headers=first_headers
            ).json()
            _expect(
                detail.get("revision") == recipe.get("revision")
                and detail.get("ingredients", [{}])[0].get("ingredient_id") == ingredient_id,
                "Recipe detail did not persist the synthetic recipe",
            )
            evaluation = _request(
                client,
                "POST",
                f"/recipes/{recipe['id']}/evaluate",
                headers=first_headers,
                json={"expected_recipe_revision": recipe["revision"], "servings": "1"},
            ).json()
            requirement = evaluation.get("result", {}).get("availability", {}).get("requirements", [{}])[0]
            _expect(
                Decimal(str(requirement.get("shortfall"))) == Decimal("2"),
                "Recipe evaluation did not reflect the persisted pantry quantity",
            )

            _request(client, "GET", "/food-profiles/me", headers=first_headers)
            declared = _request(
                client,
                "PUT",
                "/food-profiles/me",
                headers=first_headers,
                json={
                    "allergy_status": "DECLARED",
                    "allergies": [{"allergen_code": "egg", "severity": "severe"}],
                },
            ).json()
            egg_safety = _request(
                client,
                "POST",
                "/food-safety/evaluate",
                headers=first_headers,
                json={
                    "recipe_servings": "1",
                    "servings": "1",
                    "requirements": [{"display_name": "egg", "amount": "1", "unit": "piece"}],
                },
            ).json()
            _expect(egg_safety.get("decision") == "blocked", "A declared egg allergy did not block evaluation")
            _request(
                client,
                "PUT",
                "/food-profiles/me",
                headers=first_headers,
                json={
                    "expected_revision": declared["revision"],
                    "allergy_status": "NONE_DECLARED",
                    "allergies": [],
                },
            )

            preview = _request(
                client,
                "POST",
                "/recipe-shopping/preview",
                headers=first_headers,
                json={
                    "recipe_id": recipe["id"],
                    "expected_recipe_revision": recipe["revision"],
                    "servings": "1",
                    "include_optional": False,
                },
            ).json()
            _expect(preview.get("safety", {}).get("decision") == "eligible", "Shopping preview was not safety eligible")
            _expect(
                Decimal(str(preview.get("lines", [{}])[0].get("shortage"))) == Decimal("2"),
                "Shopping preview did not preserve the exact inventory shortage",
            )
            confirm_payload = {
                "preview_id": preview["preview_id"],
                "idempotency_key": f"provision-staging-{run_id}",
                "expected_revision": preview["shopping_revision"],
                "accepted_lines": [
                    {
                        "ingredient_id": ingredient_id,
                        "target_quantity": "2",
                        "consolidate_existing": False,
                    }
                ],
            }
            confirmed = _request(
                client, "POST", "/recipe-shopping/confirm", headers=first_headers, json=confirm_payload
            ).json()
            replay = _request(
                client, "POST", "/recipe-shopping/confirm", headers=first_headers, json=confirm_payload
            ).json()
            _expect(confirmed == replay, "Retrying a confirmed shopping preview was not idempotent")
            _expect(
                len(confirmed.get("created", [])) == 1
                and Decimal(str(confirmed["created"][0].get("quantity"))) == Decimal("2"),
                "Shopping confirmation did not create the exact accepted quantity",
            )
            shopping_items = _request(client, "GET", "/shopping-list/", headers=first_headers).json()
            _expect(
                len(shopping_items) == 1
                and Decimal(str(shopping_items[0].get("quantity"))) == Decimal("2")
                and shopping_items[0].get("origin_recipe_id") == recipe["id"],
                "Confirmed shopping quantity did not persist through the API",
            )
        finally:
            if second_registered:
                _cleanup_account(client, second_email, second_password)

    print(
        "Staging API smoke passed: registration/login, household selection and isolation, product mapping and label "
        "review, inventory expiration and quantity, recipe detail and availability, allergy review and blocking, "
        "provider-disabled recommendations, and explicit idempotent shopping confirmation."
    )


def cleanup() -> None:
    accounts = []
    for number in range(1, 11):
        suffix = "" if number == 1 else f"_{number}"
        email = os.environ.get(f"PROVISION_STAGING_TEST_EMAIL{suffix}")
        password = os.environ.get(f"PROVISION_STAGING_TEST_PASSWORD{suffix}")
        if email and password:
            accounts.append((email, password))
    if not accounts:
        print("No staging E2E account was created; nothing to clean up.")
        return
    preflight()
    with httpx.Client(timeout=20, follow_redirects=False, trust_env=False) as client:
        for email, password in accounts:
            _cleanup_account(client, email, password)
    print("Run-owned synthetic staging households were cleaned up.")


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
