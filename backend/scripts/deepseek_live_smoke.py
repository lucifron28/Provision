"""Make one small, manual-only request to verify the configured DeepSeek API."""

from app.core.config import settings
from app.schemas.deepseek import DeepSeekChatMessage, DeepSeekChatRequest
from app.services.deepseek_provider import DeepSeekProvider


def main() -> None:
    if not settings.DEEPSEEK_ENABLED or settings.DEEPSEEK_API_KEY is None:
        raise SystemExit("DeepSeek is not configured for this live smoke run.")

    request = DeepSeekChatRequest(
        messages=[
            DeepSeekChatMessage(
                role="user",
                content='Return exactly this JSON object: {"status":"ok"}.',
            )
        ],
        max_tokens=64,
    )
    with DeepSeekProvider(settings) as provider:
        response = provider.chat_json(request)

    if response.json_object.get("status") != "ok":
        raise SystemExit("DeepSeek returned a valid response with an unexpected payload.")

    print(
        "DeepSeek live smoke passed. "
        f"Model: {response.model}. Tokens: {response.usage.total_tokens}."
    )


if __name__ == "__main__":
    main()
