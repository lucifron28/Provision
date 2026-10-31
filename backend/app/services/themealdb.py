"""Bounded access to TheMealDB's documented educational API.

This low-level client does not grant permission to use recipe text and is not
an application endpoint. Callers must apply source review and household consent.
"""

import re
from urllib.parse import urlencode

import httpx

from app.services.pinned_page_transport import PinnedTLSTransport
from app.services.source_urls import validate_redirect_hops


_HOST = "www.themealdb.com"
_BASE = f"https://{_HOST}/api/json/v1/1/"
_MAX_BYTES = 500_000
_TIMEOUT = 10.0


class MealDBError(Exception):
    """The API could not be reached or returned an invalid response."""


class _PinnedTransport(httpx.BaseTransport):
    def __init__(self, transport: PinnedTLSTransport):
        self._transport = transport

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        if request.method != "GET" or request.url.host != _HOST or request.url.scheme != "https":
            raise MealDBError("Invalid API destination")
        url = str(request.url)
        try:
            addresses = self._transport.resolve(_HOST)
            validated = validate_redirect_hops({_HOST}, set(), [url], {_HOST: list(addresses)})
            response = self._transport.fetch_once_pinned(
                url, connect_ip=validated[0][1][0], timeout_seconds=_TIMEOUT, max_bytes=_MAX_BYTES
            )
        except Exception:
            raise MealDBError("TheMealDB is unavailable") from None
        return httpx.Response(response.status_code, headers=response.headers, content=response.body, request=request)


class MealDBClient:
    """Fetch official API responses; automatic redirects and environment proxies are disabled."""

    def __init__(self, transport: PinnedTLSTransport):
        self._client = httpx.Client(
            transport=_PinnedTransport(transport), follow_redirects=False, trust_env=False, timeout=_TIMEOUT
        )

    def close(self) -> None:
        self._client.close()

    def lookup(self, meal_id: str) -> dict | None:
        if not isinstance(meal_id, str) or not re.fullmatch(r"[0-9]{1,12}", meal_id):
            raise ValueError("Invalid meal ID")
        return self._get("lookup.php", {"i": meal_id})

    def _get(self, endpoint: str, params: dict[str, str]) -> dict | None:
        url = _BASE + endpoint + "?" + urlencode(params)
        try:
            response = self._client.get(url)
            if response.status_code != 200 or response.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                raise MealDBError("TheMealDB returned an unsupported response")
            data = response.json()
        except (ValueError, httpx.HTTPError):
            raise MealDBError("TheMealDB returned an invalid response") from None
        if not isinstance(data, dict) or set(data) != {"meals"}:
            raise MealDBError("TheMealDB returned an invalid response")
        meals = data["meals"]
        if meals is None:
            return None
        if not isinstance(meals, list) or len(meals) != 1 or not isinstance(meals[0], dict):
            raise MealDBError("TheMealDB returned an invalid response")
        if meals[0].get("idMeal") != params["i"]:
            raise MealDBError("TheMealDB returned a different meal")
        return meals[0]
