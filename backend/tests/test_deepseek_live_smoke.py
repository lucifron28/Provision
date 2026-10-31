"""Explicitly opted-in, bounded DeepSeek transport smoke tests.

Run with PROVISION_DEEPSEEK_LIVE_SMOKE=1 and the normal test database URL.
These tests send no household data and never print the key or response body.
"""

import json
import os

import httpx
import pytest

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
    from app.models.deepseek_budget import DeepSeekBudget
    from app.services.deepseek_budget import PostgresDeepSeekBudget
    from sqlalchemy import func, select
    from test_privacy import _consent

    _headers()
    _consent(db, auth_user, auth_household)
    db.commit()
    config = settings.model_copy(update={"DEEPSEEK_ENABLED": True, "DEEPSEEK_TIMEOUT_SECONDS": 45})
    with DeepSeekProvider(config, budget=PostgresDeepSeekBudget(config)) as provider:
        app.dependency_overrides[get_provider] = lambda: provider
        response = client.post("/api/v1/ai-recipes/generate", json={"dish": "Filipino garlic rice"})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["provenance"] == "AI_ORIGINAL"
    assert result["safety"]["decision"] in {"eligible", "blocked", "review_required"}
    assert db.scalar(select(func.count()).select_from(Recipe)) == 0
    assert db.scalar(select(func.count()).select_from(ShoppingListItem)) == 0
    assert db.scalar(select(DeepSeekBudget.used)) == 1
    print(f"Model: {result['model']}; token usage: {result['usage']}")


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
