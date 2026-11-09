"""Explicitly opted-in, bounded DeepSeek transport smoke tests.

Run with PROVISION_DEEPSEEK_LIVE_SMOKE=1 and the normal test database URL.
These tests send no household data and never print the key or response body.
"""

import json
import os
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.ai_recipe import AIRecipeProposal
from app.schemas.deepseek import DeepSeekChatMessage, DeepSeekChatRequest, DeepSeekSearchRequest
from app.services.deepseek_provider import DeepSeekProvider


pytestmark = pytest.mark.skipif(
    os.getenv("PROVISION_DEEPSEEK_LIVE_SMOKE") != "1",
    reason="live DeepSeek smoke tests require explicit opt-in",
)


def _headers():
    key = settings.DEEPSEEK_API_KEY
    if key is None or not key.get_secret_value().strip() or key.get_secret_value().startswith("replace-with"):
        pytest.skip("a non-placeholder DeepSeek key is required")
    return {"Authorization": f"Bearer {key.get_secret_value()}"}


def _write_live_evidence(record: dict[str, object]) -> None:
    target = os.getenv("PROVISION_DEEPSEEK_LIVE_EVIDENCE_PATH")
    if not target:
        return
    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_live_deepseek_authentication():
    response = httpx.get("https://api.deepseek.com/models", headers=_headers(), timeout=15)
    assert response.status_code == 200
    assert isinstance(response.json().get("data"), list)


def test_live_deepseek_original_recipe_json():
    payload = {
        "model": "deepseek-flash",
        "messages": [
            {"role": "system", "content": "Return valid JSON only, without explanation."},
            {"role": "user", "content": "Return JSON containing one original Filipino-inspired garlic rice recipe: title, servings, ingredients, steps. Do not cite sources."},
        ],
        "response_format": {"type": "json_object"},
        "thinking": {"type": "disabled"},
        "temperature": 0,
        "max_tokens": 512,
    }
    response = httpx.post("https://api.deepseek.com/chat/completions", headers=_headers(), json=payload, timeout=45)
    assert response.status_code == 200
    data = response.json()
    assert data["choices"][0]["finish_reason"] == "stop"
    result = json.loads(data["choices"][0]["message"]["content"])
    assert isinstance(result, dict)
    assert {"title", "servings", "ingredients", "steps"} <= result.keys()


def test_live_provider_returns_validated_original_recipe():
    _headers()
    config = settings.model_copy(update={"DEEPSEEK_ENABLED": True, "DEEPSEEK_TIMEOUT_SECONDS": 45})
    prompt = (
        "Create one original Filipino garlic rice recipe as JSON with title, servings, "
        "ingredients and steps. Each ingredient must have name, numeric amount, unit "
        "(g, kg, ml, l, or count), and required boolean. Steps must be strings. "
        "No extra fields or source claims."
    )
    with DeepSeekProvider(config) as provider:
        response = provider.chat_json(DeepSeekChatRequest(
            messages=[DeepSeekChatMessage(role="user", content=prompt)], max_tokens=512
        ))
    proposal = AIRecipeProposal.model_validate(response.json_object)
    assert proposal.ingredients and proposal.steps
    print(f"Model: {response.model}; token usage: {response.usage.model_dump()}")


def test_live_generation_api_with_consented_test_household(client, db, auth_user, auth_household):
    from app.api.v1.endpoints.ai_recipes import get_provider
    from app.main import app
    from app.models.recipe import Recipe
    from app.models.shopping import ShoppingListItem
    from app.models.batch import InventoryBatch
    from app.models.event import InventoryEvent
    from app.models.deepseek_budget import DeepSeekBudget, HouseholdDeepSeekBudget
    from app.services.deepseek_budget import PostgresDeepSeekBudget
    from sqlalchemy import func, select
    from test_privacy import _consent

    evidence: dict[str, object] = {
        "scenario": "synthetic Filipino recipe generation",
        "fixtureStatus": "synthetic_fixture",
        "householdData": "synthetic",
        "liveProviderUsed": True,
        "provider": "DeepSeek",
        "status": "started",
        "failureStage": None,
        "failureType": None,
        "model": None,
        "httpStatus": None,
        "tokenUsage": None,
        "schemaValidation": "not_checked",
        "quantityValidation": "not_checked",
        "safetyValidation": "not_checked",
        "safetyDecision": None,
        "databaseMutationCheck": "not_checked",
        "persisted": False,
        "providerRequestCount": 0,
        "globalRequestBudgetUsed": None,
        "householdRequestBudgetUsed": None,
        "requestBudgetValidation": "not_checked",
    }
    stage = "consent_and_fixture_setup"
    try:
        _headers()
        _consent(db, auth_user, auth_household)
        db.commit()
        before = {
            "recipes": db.scalar(select(func.count()).select_from(Recipe).where(Recipe.household_id == auth_household.id)),
            "shopping_items": db.scalar(select(func.count()).select_from(ShoppingListItem).where(ShoppingListItem.household_id == auth_household.id)),
            "inventory_batches": db.scalar(select(func.count()).select_from(InventoryBatch).where(InventoryBatch.household_id == auth_household.id)),
            "inventory_events": db.scalar(
                select(func.count()).select_from(InventoryEvent).join(
                    InventoryBatch, InventoryEvent.batch_id == InventoryBatch.id
                ).where(InventoryBatch.household_id == auth_household.id)
            ),
        }
        config = settings.model_copy(update={"DEEPSEEK_ENABLED": True, "DEEPSEEK_TIMEOUT_SECONDS": 45})
        evidence["model"] = config.DEEPSEEK_MODEL
        budget = PostgresDeepSeekBudget(config, household_id=auth_household.id)
        budget.prepare_household()
        stage = "provider_request"
        with DeepSeekProvider(config, budget=budget) as provider:
            app.dependency_overrides[get_provider] = lambda: provider
            evidence["providerRequestCount"] = 1
            response = client.post("/api/v1/ai-recipes/generate", json={"dish": "Filipino garlic rice"})
        evidence["httpStatus"] = response.status_code
        if response.status_code != 200:
            evidence["status"] = "provider_error"
            pytest.fail(f"Synthetic recipe request failed with HTTP {response.status_code}", pytrace=False)

        result = response.json()
        evidence["model"] = result.get("model")
        usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
        evidence["tokenUsage"] = {
            key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        assert result["provenance"] == "AI_ORIGINAL"
        stage = "recipe_schema_validation"
        try:
            proposal = AIRecipeProposal.model_validate(result["proposal"])
        except ValidationError:
            evidence["schemaValidation"] = "failed"
            pytest.fail("Provider output did not match the recipe schema.", pytrace=False)
        evidence["schemaValidation"] = "passed"
        assert proposal.title.strip()
        assert proposal.servings.is_finite() and proposal.servings > 0
        assert proposal.ingredients and all(
            item.amount.is_finite() and item.amount > 0 for item in proposal.ingredients
        )
        assert proposal.steps and all(step.strip() for step in proposal.steps)
        evidence["quantityValidation"] = "passed"
        stage = "safety_validation"
        safety = result["safety"]
        assert safety["decision"] in {"eligible", "blocked", "review_required"}
        assert isinstance(safety["reasons"], list)
        assert len(safety["ingredients"]) == len(proposal.ingredients)
        assert all(item["decision"] in {"eligible", "blocked", "review_required"} for item in safety["ingredients"])
        assert len(safety["availability"]["requirements"]) == len(proposal.ingredients)
        evidence["safetyDecision"] = safety["decision"]
        evidence["safetyValidation"] = "passed"

        stage = "database_mutation_check"
        db.expire_all()
        after = {
            "recipes": db.scalar(select(func.count()).select_from(Recipe).where(Recipe.household_id == auth_household.id)),
            "shopping_items": db.scalar(select(func.count()).select_from(ShoppingListItem).where(ShoppingListItem.household_id == auth_household.id)),
            "inventory_batches": db.scalar(select(func.count()).select_from(InventoryBatch).where(InventoryBatch.household_id == auth_household.id)),
            "inventory_events": db.scalar(
                select(func.count()).select_from(InventoryEvent).join(
                    InventoryBatch, InventoryEvent.batch_id == InventoryBatch.id
                ).where(InventoryBatch.household_id == auth_household.id)
            ),
        }
        evidence["databaseMutationCheck"] = "passed" if after == before else "failed"
        evidence["persisted"] = after != before
        assert after == before
        evidence["globalRequestBudgetUsed"] = db.scalar(select(DeepSeekBudget.used))
        evidence["householdRequestBudgetUsed"] = db.scalar(select(HouseholdDeepSeekBudget.used))
        evidence["requestBudgetValidation"] = (
            "passed"
            if evidence["globalRequestBudgetUsed"] == 1 and evidence["householdRequestBudgetUsed"] == 1
            else "failed"
        )
        assert evidence["globalRequestBudgetUsed"] == 1
        assert evidence["householdRequestBudgetUsed"] == 1

        evidence["status"] = "passed"
        print(
            "Live recipe generation passed; "
            f"model={result['model']}; prompt_tokens={usage['prompt_tokens']}; "
            f"completion_tokens={usage['completion_tokens']}; total_tokens={usage['total_tokens']}; "
            f"safety={safety['decision']}; schema=valid; persisted=false"
        )
    except BaseException as error:
        if evidence["status"] == "started":
            evidence["status"] = "failed"
        evidence["failureStage"] = stage
        evidence["failureType"] = type(error).__name__
        raise
    finally:
        _write_live_evidence(evidence)


@pytest.mark.skipif(
    os.getenv("PROVISION_DEEPSEEK_LIVE_SEARCH") != "1",
    reason="live broader-web search requires separate explicit opt-in",
)
def test_live_deepseek_filipino_search_metadata():
    _headers()
    config = settings.model_copy(update={"DEEPSEEK_ENABLED": True})
    with DeepSeekProvider(config) as provider:
        response = provider.search(DeepSeekSearchRequest(query='"chicken adobo" recipe', count=2))
    assert response.results
    for result in response.results:
        print(f"Search result: {result.title} | {result.url}")
