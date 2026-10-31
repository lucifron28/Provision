from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.core.config import Settings
from app.schemas.deepseek import (
    DeepSeekChatMessage,
    DeepSeekChatRequest,
    DeepSeekFetchRequest,
    DeepSeekSearchRequest,
)
from app.services.deepseek_provider import (
    DeepSeekConfigurationError,
    DeepSeekDisabledError,
    DeepSeekHTTPError,
    DeepSeekInvalidResponse,
    DeepSeekOutputTruncated,
    DeepSeekProvider,
    DeepSeekRateLimitError,
    DeepSeekRequestBudgetExceeded,
    DeepSeekRequestLimitError,
    DeepSeekResponseTooLarge,
    DeepSeekTimeoutError,
)


TEST_TOKEN = "unit-test-only-token"


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "JWT_SECRET_KEY": "unit-test-jwt-secret",
        "DEEPSEEK_API_KEY": SecretStr(TEST_TOKEN),
        "DEEPSEEK_ENABLED": True,
        "DEEPSEEK_TIMEOUT_SECONDS": 2,
        "DEEPSEEK_MAX_OUTPUT_TOKENS": 1024,
        "DEEPSEEK_MAX_PROMPT_CHARACTERS": 24000,
        "DEEPSEEK_REQUESTS_PER_MINUTE": 10,
        "DEEPSEEK_REQUEST_BUDGET": 100,
        "DEEPSEEK_MAX_RESPONSE_BYTES": 1000000,
        "DEEPSEEK_MAX_SEARCH_RESULTS": 10,
        "DEEPSEEK_MAX_FETCH_CHARACTERS": 50000,
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def usage_wire(prompt: int = 59, completion: int = 287) -> dict[str, object]:
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": prompt + completion,
        "prompt_tokens_details": {"cached_tokens": 0},
        "completion_tokens_details": {"reasoning_tokens": 0},
    }


def chat_wire(
    content: str = '{"ok":true}',
    *,
    finish_reason: str = "stop",
    usage: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "model": "deepseek-flash",
        "choices": [
            {
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        "usage": usage if usage is not None else usage_wire(),
    }


def make_provider(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    settings: Settings | None = None,
    clock: Callable[[], float] | None = None,
) -> DeepSeekProvider:
    kwargs = {"transport": httpx.MockTransport(handler)}
    if clock is not None:
        kwargs["_clock"] = clock
    return DeepSeekProvider(settings or make_settings(), **kwargs)


def test_disabled_provider_never_sends_request_even_with_configured_key() -> None:
    calls: list[httpx.Request] = []
    settings = make_settings(DEEPSEEK_ENABLED=False)
    provider = make_provider(
        lambda request: (calls.append(request), httpx.Response(200, json={}))[1],
        settings=settings,
    )
    try:
        with pytest.raises(DeepSeekDisabledError):
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert calls == []


def test_enabled_provider_without_key_fails_before_network() -> None:
    calls: list[httpx.Request] = []
    settings = make_settings(DEEPSEEK_API_KEY=None)
    provider = make_provider(
        lambda request: (calls.append(request), httpx.Response(200, json={}))[1],
        settings=settings,
    )
    try:
        with pytest.raises(DeepSeekConfigurationError):
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert calls == []


def test_chat_uses_json_mode_disabled_thinking_token_bound_and_reports_usage() -> None:
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json=chat_wire())

    provider = make_provider(handle)
    try:
        result = provider.chat_json(
            DeepSeekChatRequest(
                messages=[DeepSeekChatMessage(role="user", content="return a JSON object")],
                max_tokens=512,
            )
        )
    finally:
        provider.close()

    assert len(requests) == 1
    sent = requests[0]
    assert sent.url.path == "/chat/completions"
    assert sent.headers["authorization"] == f"Bearer {TEST_TOKEN}"
    payload = json.loads(sent.content)
    assert payload["thinking"] == {"type": "disabled"}
    assert payload["max_tokens"] == 512
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    assert result.json_object == {"ok": True}
    assert result.usage.prompt_tokens == 59
    assert result.usage.completion_tokens == 287
    assert result.usage.total_tokens == 346


def test_configured_thinking_mode_is_sent_but_still_token_bounded() -> None:
    requests: list[httpx.Request] = []
    settings = make_settings(DEEPSEEK_THINKING_MODE="enabled")
    provider = make_provider(
        lambda request: (
            requests.append(request),
            httpx.Response(200, json=chat_wire()),
        )[1],
        settings=settings,
    )
    try:
        provider.chat_json(
            DeepSeekChatRequest(
                messages=[DeepSeekChatMessage(role="user", content="json")],
                max_tokens=128,
            )
        )
    finally:
        provider.close()
    payload = json.loads(requests[0].content)
    assert payload["thinking"] == {"type": "enabled"}
    assert payload["max_tokens"] == 128


@pytest.mark.parametrize("content", ["", "   ", "not json", "[1,2]"])
def test_chat_rejects_blank_malformed_or_non_object_json(content: str) -> None:
    provider = make_provider(lambda _: httpx.Response(200, json=chat_wire(content)))
    try:
        with pytest.raises(DeepSeekInvalidResponse) as caught:
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="json please")]
                )
            )
    finally:
        provider.close()
    assert caught.value.usage is not None
    assert TEST_TOKEN not in str(caught.value)


def test_chat_rejects_truncated_output_and_retains_sanitized_usage() -> None:
    provider = make_provider(
        lambda _: httpx.Response(
            200, json=chat_wire('{"partial":', finish_reason="length")
        )
    )
    try:
        with pytest.raises(DeepSeekOutputTruncated) as caught:
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="json please")]
                )
            )
    finally:
        provider.close()
    assert caught.value.usage is not None
    assert caught.value.usage.total_tokens == 346
    assert TEST_TOKEN not in str(caught.value)


def test_chat_rejects_other_finish_reasons_and_missing_usage() -> None:
    provider = make_provider(
        lambda _: httpx.Response(
            200,
            json=chat_wire(finish_reason="content_filter"),
        )
    )
    try:
        with pytest.raises(DeepSeekInvalidResponse):
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="json please")]
                )
            )
    finally:
        provider.close()

    provider = make_provider(lambda _: httpx.Response(200, json=chat_wire(usage={})))
    try:
        with pytest.raises(DeepSeekInvalidResponse) as caught:
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="json please")]
                )
            )
    finally:
        provider.close()
    assert caught.value.usage is None


def test_chat_rejects_excess_tokens_and_prompt_before_network() -> None:
    calls: list[httpx.Request] = []
    settings = make_settings(
        DEEPSEEK_MAX_OUTPUT_TOKENS=64,
        DEEPSEEK_MAX_PROMPT_CHARACTERS=70,
    )
    provider = make_provider(
        lambda request: (calls.append(request), httpx.Response(200, json=chat_wire()))[1],
        settings=settings,
    )
    try:
        with pytest.raises(DeepSeekRequestLimitError):
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="json")],
                    max_tokens=65,
                )
            )
        with pytest.raises(DeepSeekRequestLimitError):
            provider.chat_json(
                DeepSeekChatRequest(
                    messages=[DeepSeekChatMessage(role="user", content="x" * 20)],
                    max_tokens=32,
                )
            )
    finally:
        provider.close()
    assert calls == []


def search_wire(*, content: str = "") -> dict[str, object]:
    return {
        "results": [
            {
                "rerank_score": 2.4,
                "title": "Example",
                "url": "https://example.com/recipe",
                "snippet": "A short excerpt",
                "summary": "A longer summary",
                "content": content,
                "site_name": "Example",
                "site_icon": None,
                "date": None,
                "authority": 3,
            }
        ]
    }


def test_search_forces_content_off_and_returns_typed_results() -> None:
    requests: list[httpx.Request] = []
    provider = make_provider(
        lambda request: (
            requests.append(request),
            httpx.Response(200, json=search_wire()),
        )[1]
    )
    try:
        result = provider.search(
            DeepSeekSearchRequest(query="bicol express", count=3, ori_question="dinner")
        )
    finally:
        provider.close()
    assert requests[0].url.path == "/v1/tools/search"
    payload = json.loads(requests[0].content)
    assert payload == {
        "query": "bicol express",
        "count": 3,
        "need_content": False,
        "ori_question": "dinner",
    }
    assert result.results[0].content == ""
    assert result.results[0].authority == 3


def test_search_rejects_content_and_count_over_configured_cap() -> None:
    calls: list[httpx.Request] = []
    provider = make_provider(
        lambda request: (
            calls.append(request),
            httpx.Response(200, json=search_wire(content="unexpected page text")),
        )[1],
        settings=make_settings(DEEPSEEK_MAX_SEARCH_RESULTS=2),
    )
    try:
        with pytest.raises(DeepSeekInvalidResponse):
            provider.search(DeepSeekSearchRequest(query="recipe", count=2))
        with pytest.raises(DeepSeekRequestLimitError):
            provider.search(DeepSeekSearchRequest(query="recipe", count=3))
    finally:
        provider.close()
    assert len(calls) == 1


def test_fetch_uses_official_endpoint_and_enforces_content_budget() -> None:
    requests: list[httpx.Request] = []
    provider = make_provider(
        lambda request: (
            requests.append(request),
            httpx.Response(
                200, json={"title": "A page", "content": "# Page\ncontent"}
            ),
        )[1]
    )
    try:
        result = provider.fetch(DeepSeekFetchRequest(url="https://example.com/page"))
    finally:
        provider.close()
    assert requests[0].url.path == "/v1/tools/fetch"
    assert json.loads(requests[0].content) == {"url": "https://example.com/page"}
    assert result.title == "A page"

    provider = make_provider(
        lambda _: httpx.Response(
            200, json={"title": "A page", "content": "x" * 51}
        ),
        settings=make_settings(DEEPSEEK_MAX_FETCH_CHARACTERS=50),
    )
    try:
        with pytest.raises(DeepSeekResponseTooLarge):
            provider.fetch(DeepSeekFetchRequest(url="https://example.com/page"))
    finally:
        provider.close()


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "https:///missing-host",
        "https://user:password@example.com/",
        "https://example.com:invalid/path",
    ],
)
def test_fetch_request_rejects_invalid_or_credentialed_urls(url: str) -> None:
    with pytest.raises(ValidationError):
        DeepSeekFetchRequest(url=url)


def test_http_429_is_sanitized_and_exposes_retry_after() -> None:
    provider = make_provider(
        lambda _: httpx.Response(
            429,
            headers={"Retry-After": "12"},
            text="private response body",
        )
    )
    try:
        with pytest.raises(DeepSeekRateLimitError) as caught:
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert caught.value.status_code == 429
    assert caught.value.retry_after_seconds == 12
    assert "private response body" not in str(caught.value)
    assert TEST_TOKEN not in str(caught.value)


def test_http_error_and_timeout_do_not_expose_provider_details() -> None:
    provider = make_provider(
        lambda _: httpx.Response(503, text="private response body")
    )
    try:
        with pytest.raises(DeepSeekHTTPError) as caught:
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert caught.value.status_code == 503
    assert "private response body" not in str(caught.value)

    provider = make_provider(
        lambda _: (_ for _ in ()).throw(httpx.ReadTimeout("private timeout detail"))
    )
    try:
        with pytest.raises(DeepSeekTimeoutError) as caught:
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert "private timeout detail" not in str(caught.value)
    assert TEST_TOKEN not in str(caught.value)


def test_redirects_are_not_followed_and_total_deadline_is_enforced() -> None:
    calls: list[httpx.Request] = []
    redirecting = make_provider(
        lambda request: (
            calls.append(request),
            httpx.Response(
                302,
                headers={"Location": "https://other.example/private"},
            ),
        )[1]
    )
    try:
        with pytest.raises(DeepSeekHTTPError) as caught:
            redirecting.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        redirecting.close()
    assert caught.value.status_code == 302
    assert len(calls) == 1

    now = [0.0]
    settings = make_settings(DEEPSEEK_TIMEOUT_SECONDS=2)

    def slow_response(_: httpx.Request) -> httpx.Response:
        now[0] = 3.0
        return httpx.Response(200, json=search_wire())

    provider = make_provider(slow_response, settings=settings, clock=lambda: now[0])
    try:
        with pytest.raises(DeepSeekTimeoutError):
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()


def test_response_byte_limit_is_enforced_before_json_parsing() -> None:
    provider = make_provider(
        lambda _: httpx.Response(200, content=b" " * 1025),
        settings=make_settings(DEEPSEEK_MAX_RESPONSE_BYTES=1024),
    )
    try:
        with pytest.raises(DeepSeekResponseTooLarge):
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()


def test_streaming_response_byte_limit_is_enforced_incrementally() -> None:
    yielded: list[int] = []

    class ChunkedBody(httpx.SyncByteStream):
        def __iter__(self):
            for index, chunk in enumerate((b" " * 700, b" " * 400, b"ignored")):
                yielded.append(index)
                yield chunk

        def close(self) -> None:
            return None

    provider = make_provider(
        lambda _: httpx.Response(200, stream=ChunkedBody()),
        settings=make_settings(DEEPSEEK_MAX_RESPONSE_BYTES=1024),
    )
    try:
        with pytest.raises(DeepSeekResponseTooLarge):
            provider.search(DeepSeekSearchRequest(query="recipe"))
    finally:
        provider.close()
    assert yielded == [0, 1]


def test_process_budget_is_shared_and_has_minute_and_total_caps() -> None:
    now = [100.0]
    settings = make_settings(
        DEEPSEEK_REQUESTS_PER_MINUTE=1,
        DEEPSEEK_REQUEST_BUDGET=2,
    )
    calls: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=search_wire())

    first = make_provider(handle, settings=settings, clock=lambda: now[0])
    second = make_provider(handle, settings=settings, clock=lambda: now[0])
    try:
        first.search(DeepSeekSearchRequest(query="one"))
        with pytest.raises(DeepSeekRateLimitError) as caught:
            second.search(DeepSeekSearchRequest(query="two"))
        assert caught.value.retry_after_seconds == 60
        now[0] += 60
        second.search(DeepSeekSearchRequest(query="three"))
        with pytest.raises(DeepSeekRequestBudgetExceeded):
            first.search(DeepSeekSearchRequest(query="four"))
    finally:
        first.close()
        second.close()
    assert len(calls) == 2


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.deepseek.com",
        "https://user:password@api.deepseek.com",
        "https://api.deepseek.com/v1",
        "https://api.deepseek.com?debug=true",
        "https://api.deepseek.com:invalid",
    ],
)
def test_config_rejects_non_origin_or_non_https_base_urls(base_url: str) -> None:
    with pytest.raises(ValidationError):
        make_settings(DEEPSEEK_BASE_URL=base_url)
