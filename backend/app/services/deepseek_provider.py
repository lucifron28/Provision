"""Bounded, server-side DeepSeek API client.

Keep one provider instance for the process so its request budgets are shared.
Search and fetch results are untrusted source material: callers must apply the
recipe source registry and URL policy before deciding whether to use them.
"""

from __future__ import annotations

import json
import math
import weakref
from collections import deque
from threading import Lock
from time import monotonic
from typing import Any, Callable

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.deepseek import (
    DeepSeekChatRequest,
    DeepSeekChatResponse,
    DeepSeekFetchRequest,
    DeepSeekFetchResponse,
    DeepSeekSearchRequest,
    DeepSeekSearchResponse,
    DeepSeekTokenUsage,
)


class DeepSeekProviderError(RuntimeError):
    """Sanitized provider failure; never includes a request or response body."""

    def __init__(
        self,
        message: str,
        *,
        operation: str,
        code: str,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
        usage: DeepSeekTokenUsage | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.code = code
        self.status_code = status_code
        self.retry_after_seconds = retry_after_seconds
        self.usage = usage


class DeepSeekDisabledError(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek provider is disabled.", operation=operation, code="disabled"
        )


class DeepSeekConfigurationError(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek provider configuration is incomplete.",
            operation=operation,
            code="configuration",
        )


class DeepSeekRequestBudgetExceeded(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek request budget is exhausted.",
            operation=operation,
            code="request_budget_exhausted",
        )


class DeepSeekRequestLimitError(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek request exceeds a configured limit.",
            operation=operation,
            code="request_limit",
        )


class DeepSeekRateLimitError(DeepSeekProviderError):
    def __init__(
        self,
        operation: str,
        *,
        status_code: int | None = None,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(
            "DeepSeek request was rate limited.",
            operation=operation,
            code="rate_limited",
            status_code=status_code,
            retry_after_seconds=retry_after_seconds,
        )


class DeepSeekTimeoutError(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek request timed out.", operation=operation, code="timeout"
        )


class DeepSeekTransportError(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek request could not be completed.",
            operation=operation,
            code="transport_error",
        )


class DeepSeekHTTPError(DeepSeekProviderError):
    def __init__(self, operation: str, status_code: int) -> None:
        super().__init__(
            "DeepSeek returned an unsuccessful response.",
            operation=operation,
            code="http_error",
            status_code=status_code,
        )


class DeepSeekResponseTooLarge(DeepSeekProviderError):
    def __init__(self, operation: str) -> None:
        super().__init__(
            "DeepSeek response exceeded the configured size limit.",
            operation=operation,
            code="response_too_large",
        )


class DeepSeekOutputTruncated(DeepSeekProviderError):
    def __init__(
        self, operation: str, *, usage: DeepSeekTokenUsage | None = None
    ) -> None:
        super().__init__(
            "DeepSeek output was truncated by its token limit.",
            operation=operation,
            code="output_truncated",
            usage=usage,
        )


class DeepSeekInvalidResponse(DeepSeekProviderError):
    def __init__(
        self, operation: str, *, usage: DeepSeekTokenUsage | None = None
    ) -> None:
        super().__init__(
            "DeepSeek returned an invalid response.",
            operation=operation,
            code="invalid_response",
            usage=usage,
        )


class _RequestBudget:
    """Thread-safe process budget for one Settings object."""

    def __init__(
        self,
        *,
        requests_per_minute: int,
        total_requests: int,
        clock: Callable[[], float],
    ) -> None:
        self._requests_per_minute = requests_per_minute
        self._total_requests = total_requests
        self._clock = clock
        self._timestamps: deque[float] = deque()
        self._used = 0
        self._lock = Lock()

    def consume(self, operation: str) -> None:
        with self._lock:
            now = self._clock()
            while self._timestamps and now - self._timestamps[0] >= 60:
                self._timestamps.popleft()
            if self._used >= self._total_requests:
                raise DeepSeekRequestBudgetExceeded(operation)
            if len(self._timestamps) >= self._requests_per_minute:
                wait = max(0.0, 60.0 - (now - self._timestamps[0]))
                raise DeepSeekRateLimitError(
                    operation, retry_after_seconds=wait
                )
            self._used += 1
            self._timestamps.append(now)


_PROCESS_BUDGETS: dict[int, tuple[weakref.ReferenceType[Settings], _RequestBudget]] = {}
_PROCESS_BUDGETS_LOCK = Lock()


def _remove_process_budget(
    key: int, reference: weakref.ReferenceType[Settings]
) -> None:
    with _PROCESS_BUDGETS_LOCK:
        current = _PROCESS_BUDGETS.get(key)
        if current is not None and current[0] is reference:
            _PROCESS_BUDGETS.pop(key, None)


def _get_process_budget(
    settings: Settings, clock: Callable[[], float]
) -> _RequestBudget:
    key = id(settings)
    with _PROCESS_BUDGETS_LOCK:
        current = _PROCESS_BUDGETS.get(key)
        if current is not None and current[0]() is settings:
            return current[1]
        reference = weakref.ref(
            settings, lambda ref, budget_key=key: _remove_process_budget(budget_key, ref)
        )
        budget = _RequestBudget(
            requests_per_minute=settings.DEEPSEEK_REQUESTS_PER_MINUTE,
            total_requests=settings.DEEPSEEK_REQUEST_BUDGET,
            clock=clock,
        )
        _PROCESS_BUDGETS[key] = (reference, budget)
        return budget


class DeepSeekProvider:
    """Synchronous adapter for bounded chat, search, and fetch requests.

    Budget counters are shared by instances that use the same Settings object.
    Reuse the application's settings singleton to enforce one process budget.
    No method retries: a retry could duplicate a billable provider operation.
    """

    def __init__(
        self,
        settings: Settings,
        *,
        transport: httpx.BaseTransport | None = None,
        _clock: Callable[[], float] = monotonic,
    ) -> None:
        self._settings = settings
        self._clock = _clock
        self._client = httpx.Client(
            timeout=httpx.Timeout(settings.DEEPSEEK_TIMEOUT_SECONDS),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
        )
        self._budget = _get_process_budget(settings, _clock)

    def chat_json(self, request: DeepSeekChatRequest) -> DeepSeekChatResponse:
        operation = "chat"
        self._validate_chat_request(request, operation)
        messages = [
            {
                "role": "system",
                "content": "Return exactly one valid JSON object. Do not use markdown fences.",
            },
            *[message.model_dump() for message in request.messages],
        ]
        payload = {
            "model": self._settings.DEEPSEEK_MODEL,
            "messages": messages,
            "max_tokens": request.max_tokens,
            "thinking": {"type": self._settings.DEEPSEEK_THINKING_MODE},
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        wire = self._post_json("/chat/completions", payload, operation)
        usage = self._usage_from_wire(wire)
        choices = wire.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            raise DeepSeekInvalidResponse(operation, usage=usage)
        choice = choices[0]
        finish_reason = choice.get("finish_reason")
        if finish_reason == "length":
            raise DeepSeekOutputTruncated(operation, usage=usage)
        if finish_reason != "stop":
            raise DeepSeekInvalidResponse(operation, usage=usage)
        message = choice.get("message")
        if not isinstance(message, dict) or not isinstance(message.get("content"), str):
            raise DeepSeekInvalidResponse(operation, usage=usage)
        if usage is None:
            raise DeepSeekInvalidResponse(operation)
        content = message["content"].strip()
        if not content:
            raise DeepSeekInvalidResponse(operation, usage=usage)
        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise DeepSeekInvalidResponse(operation, usage=usage) from None
        if not isinstance(parsed, dict):
            raise DeepSeekInvalidResponse(operation, usage=usage)
        model = wire.get("model")
        if not isinstance(model, str) or not model.strip():
            model = self._settings.DEEPSEEK_MODEL
        try:
            return DeepSeekChatResponse.model_validate(
                {
                    "model": model,
                    "finish_reason": finish_reason,
                    "json_object": parsed,
                    "usage": usage,
                }
            )
        except ValidationError:
            raise DeepSeekInvalidResponse(operation, usage=usage) from None

    def search(self, request: DeepSeekSearchRequest) -> DeepSeekSearchResponse:
        operation = "search"
        if request.count > self._settings.DEEPSEEK_MAX_SEARCH_RESULTS:
            raise DeepSeekRequestLimitError(operation)
        payload: dict[str, Any] = {
            "query": request.query,
            "count": request.count,
            "need_content": False,
        }
        if request.ori_question is not None:
            payload["ori_question"] = request.ori_question
        wire = self._post_json("/v1/tools/search", payload, operation)
        try:
            parsed = DeepSeekSearchResponse.model_validate(wire)
        except ValidationError:
            raise DeepSeekInvalidResponse(operation) from None
        if any(result.content for result in parsed.results):
            raise DeepSeekInvalidResponse(operation)
        if len(parsed.results) > request.count:
            parsed.results = parsed.results[: request.count]
        return parsed

    def fetch(self, request: DeepSeekFetchRequest) -> DeepSeekFetchResponse:
        operation = "fetch"
        wire = self._post_json(
            "/v1/tools/fetch", {"url": request.url}, operation
        )
        try:
            parsed = DeepSeekFetchResponse.model_validate(wire)
        except ValidationError:
            raise DeepSeekInvalidResponse(operation) from None
        if len(parsed.content) > self._settings.DEEPSEEK_MAX_FETCH_CHARACTERS:
            raise DeepSeekResponseTooLarge(operation)
        return parsed

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DeepSeekProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _validate_chat_request(
        self, request: DeepSeekChatRequest, operation: str
    ) -> None:
        if request.max_tokens > self._settings.DEEPSEEK_MAX_OUTPUT_TOKENS:
            raise DeepSeekRequestLimitError(operation)
        prompt_characters = sum(len(message.content) for message in request.messages)
        prompt_characters += len(
            "Return exactly one valid JSON object. Do not use markdown fences."
        )
        if prompt_characters > self._settings.DEEPSEEK_MAX_PROMPT_CHARACTERS:
            raise DeepSeekRequestLimitError(operation)

    def _post_json(
        self, path: str, payload: dict[str, Any], operation: str
    ) -> dict[str, Any]:
        self._require_enabled(operation)
        self._budget.consume(operation)
        api_key = self._settings.DEEPSEEK_API_KEY
        assert api_key is not None  # Checked by _require_enabled.
        started_at = self._clock()
        try:
            with self._client.stream(
                "POST",
                f"{self._settings.DEEPSEEK_BASE_URL}{path}",
                json=payload,
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value().strip()}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                },
                follow_redirects=False,
            ) as response:
                self._check_deadline(started_at, operation)
                if response.status_code == 429:
                    retry_after = self._retry_after(response.headers.get("Retry-After"))
                    raise DeepSeekRateLimitError(
                        operation,
                        status_code=response.status_code,
                        retry_after_seconds=retry_after,
                    )
                if not 200 <= response.status_code < 300:
                    raise DeepSeekHTTPError(operation, response.status_code)
                content_encoding = response.headers.get("Content-Encoding", "identity")
                if content_encoding.strip().lower() not in {"", "identity"}:
                    raise DeepSeekInvalidResponse(operation)
                content_length = response.headers.get("Content-Length")
                if content_length is not None:
                    try:
                        if int(content_length) > self._settings.DEEPSEEK_MAX_RESPONSE_BYTES:
                            raise DeepSeekResponseTooLarge(operation)
                    except ValueError:
                        pass
                body = bytearray()
                if response.is_stream_consumed:
                    # MockTransport and buffering middleware may return a cached body.
                    # Keep this path bounded; real network responses use iter_raw below.
                    cached_body = response.content
                    if len(cached_body) > self._settings.DEEPSEEK_MAX_RESPONSE_BYTES:
                        raise DeepSeekResponseTooLarge(operation)
                    body.extend(cached_body)
                else:
                    for chunk in response.iter_raw():
                        self._check_deadline(started_at, operation)
                        if len(body) + len(chunk) > self._settings.DEEPSEEK_MAX_RESPONSE_BYTES:
                            raise DeepSeekResponseTooLarge(operation)
                        body.extend(chunk)
        except DeepSeekProviderError:
            raise
        except httpx.TimeoutException:
            raise DeepSeekTimeoutError(operation) from None
        except httpx.HTTPError:
            raise DeepSeekTransportError(operation) from None
        try:
            decoded = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            raise DeepSeekInvalidResponse(operation) from None
        if not isinstance(decoded, dict):
            raise DeepSeekInvalidResponse(operation)
        return decoded

    def _check_deadline(self, started_at: float, operation: str) -> None:
        if self._clock() - started_at >= self._settings.DEEPSEEK_TIMEOUT_SECONDS:
            raise DeepSeekTimeoutError(operation)

    def _require_enabled(self, operation: str) -> None:
        if not self._settings.DEEPSEEK_ENABLED:
            raise DeepSeekDisabledError(operation)
        key = self._settings.DEEPSEEK_API_KEY
        if key is None or not key.get_secret_value().strip():
            raise DeepSeekConfigurationError(operation)

    @staticmethod
    def _retry_after(value: str | None) -> float | None:
        if value is None:
            return None
        try:
            seconds = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(seconds) or seconds < 0:
            return None
        return min(seconds, 3600.0)

    @staticmethod
    def _usage_from_wire(wire: dict[str, Any]) -> DeepSeekTokenUsage | None:
        raw = wire.get("usage")
        if not isinstance(raw, dict):
            return None
        details = raw.get("completion_tokens_details")
        reasoning_tokens = details.get("reasoning_tokens") if isinstance(details, dict) else None
        candidate: dict[str, Any] = {
            "prompt_tokens": raw.get("prompt_tokens"),
            "completion_tokens": raw.get("completion_tokens"),
            "total_tokens": raw.get("total_tokens"),
        }
        if reasoning_tokens is not None:
            candidate["reasoning_tokens"] = reasoning_tokens
        try:
            return DeepSeekTokenUsage.model_validate(candidate)
        except ValidationError:
            return None
