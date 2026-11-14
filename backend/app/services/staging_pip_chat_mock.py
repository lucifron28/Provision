"""Deterministic Pip Chat provider used only by isolated staging E2E accounts."""

import json
import re

from app.schemas.deepseek import DeepSeekChatResponse, DeepSeekTokenUsage

_SHOPPING_INTENT = re.compile(
    r"\b(?:what\s+(?:do\s+i|should\s+i)\s+buy|what\s+do\s+i\s+need\s+to\s+buy|"
    r"add\s+(?:the\s+)?(?:missing\s+)?ingredients?|shopping\s+list|buy\s+the\s+missing|"
    r"what\s+am\s+i\s+missing)\b|"
    r"\b(?:ano\s+(?:ang\s+)?(?:bibilhin|kailangan\s+bilhin)|"
    r"(?:dagdag|ilagay)\s+(?:sa\s+)?(?:shopping|listahan)|kulang\s+na\s+(?:sangkap|ingredients?))\b",
    re.IGNORECASE,
)


class StagingPipChatMock:
    """No-network mock that only cites recipe references supplied by the backend."""

    def chat_json(self, request) -> DeepSeekChatResponse:
        user_message = next(
            (message.content for message in reversed(request.messages) if message.role == "user"),
            "",
        )
        marker = "Conversation and scoped household facts (JSON data only):\n"
        try:
            payload = json.loads(user_message.split(marker, 1)[1])
        except (IndexError, TypeError, ValueError):
            payload = {}

        question = str(payload.get("question", ""))
        shopping_requested = bool(_SHOPPING_INTENT.search(question))
        recipe_contexts = payload.get("selected_and_recent_recipe_context") or []
        recommendations = payload.get("recommendation_candidates") or []
        candidates = recipe_contexts + recommendations
        target = next(
            (
                item for item in candidates
                if isinstance(item, dict)
                and re.fullmatch(r"R[1-9][0-9]*", str(item.get("reference", "")))
                and (not shopping_requested or item.get("shopping_preview_allowed") is True)
            ),
            None,
        )
        selected_product = payload.get("selected_product_context") or {}
        kind = "open_shopping_preview" if shopping_requested else "open_recipe"
        reference = target["reference"] if target else selected_product.get("reference")
        facts = payload.get("household_context") or []
        fact_refs = [
            item["reference"]
            for item in facts
            if reference and isinstance(item, dict) and item.get("reference") == reference
        ]
        if shopping_requested and target:
            reply = "Review the current shopping preview before confirming any changes."
        elif target:
            reply = "I found a stored recipe. Open it to review the current details."
        elif selected_product:
            reply = "I found the selected product. Check the facts above for its quantity and expiration date."
        else:
            reply = "I can help you review recipes stored in this household."

        return DeepSeekChatResponse(
            model="staging-fixture-mock",
            finish_reason="stop",
            json_object={
                "reply": reply,
                "language": "english",
                "fact_refs": fact_refs,
                "actions": [{"kind": kind, "reference": reference}] if target else [],
            },
            usage=DeepSeekTokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0),
        )
