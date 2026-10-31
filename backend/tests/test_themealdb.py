import json
import os

import pytest

from app.services.deepseek_discovery import PageFetchResponse
from app.services.pinned_page_transport import PinnedTLSTransport
from app.services.themealdb import MealDBClient, MealDBError


class FakeTransport:
    def __init__(self, *, status=200, body=None, addresses=("93.184.216.34",), content_type="application/json"):
        self.status = status
        self.body = body if body is not None else json.dumps({"meals": [{"idMeal": "123", "strMeal": "Adobo"}]}).encode()
        self.addresses = addresses
        self.content_type = content_type
        self.requests = []

    def resolve(self, hostname):
        assert hostname == "www.themealdb.com"
        return self.addresses

    def fetch_once_pinned(self, url, **kwargs):
        self.requests.append((url, kwargs))
        return PageFetchResponse(self.status, {"content-type": self.content_type}, self.body)


def test_lookup_uses_fixed_api_endpoint_and_public_pinned_address():
    transport = FakeTransport()
    client = MealDBClient(transport)
    try:
        assert client.lookup("123")["strMeal"] == "Adobo"
        url, options = transport.requests[0]
        assert url == "https://www.themealdb.com/api/json/v1/1/lookup.php?i=123"
        assert options == {"connect_ip": "93.184.216.34", "timeout_seconds": 10.0, "max_bytes": 500_000}
    finally:
        client.close()


@pytest.mark.parametrize("meal_id", ["", "../123", "123&x=1", "1" * 13, None])
def test_lookup_rejects_invalid_ids_without_network(meal_id):
    transport = FakeTransport()
    client = MealDBClient(transport)
    with pytest.raises(ValueError):
        client.lookup(meal_id)
    assert not transport.requests
    client.close()


@pytest.mark.parametrize("transport", [
    FakeTransport(addresses=("127.0.0.1",)),
    FakeTransport(status=302),
    FakeTransport(content_type="text/html"),
    FakeTransport(body=b"not json"),
    FakeTransport(body=b'{"meals":[{"idMeal":"456"}]}'),
])
def test_lookup_fails_closed_on_unsafe_or_invalid_responses(transport):
    client = MealDBClient(transport)
    with pytest.raises(MealDBError):
        client.lookup("123")
    client.close()


def test_lookup_allows_no_results():
    client = MealDBClient(FakeTransport(body=b'{"meals":null}'))
    assert client.lookup("123") is None
    client.close()


@pytest.mark.skipif(os.getenv("PROVISION_MEALDB_LIVE_SMOKE") != "1", reason="live API test requires explicit opt-in")
def test_live_official_lookup_returns_requested_id():
    transport = PinnedTLSTransport(user_agent="ProvisionBot/1.0 (https://github.com/lucifron28/Provision)")
    client = MealDBClient(transport)
    try:
        result = client.lookup("53073")
        assert result is not None and result.get("idMeal") == "53073"
    finally:
        client.close()
