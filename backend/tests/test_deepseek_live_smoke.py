"""Explicitly opted-in, bounded DeepSeek transport smoke tests.

Run with PROVISION_DEEPSEEK_LIVE_SMOKE=1 and the normal test database URL.
These tests send no household data and never print the key or response body.
"""

import json
import os

import httpx
import pytest

from app.core.config import settings
from app.schemas.deepseek import DeepSeekSearchRequest
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
