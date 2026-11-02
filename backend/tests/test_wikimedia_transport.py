from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from app.services.wikimedia_transport import BudgetedWikimediaTransport, WikimediaRateLimited, REVIEWED_RECIPE_URL


class Budget:
    def __init__(self):
        self.calls = 0
        self.error = None

    @contextmanager
    def request(self):
        self.calls += 1
        try:
            yield
        except Exception as error:
            self.error = error
            raise


class Transport:
    user_agent = "ProvisionBot/1.0 (operator@example.com)"

    def __init__(self, status=200, headers=None):
        self.status = status
        self.headers = headers or {}
        self.calls = 0

    def fetch_once_pinned(self, url, **kwargs):
        self.calls += 1
        return SimpleNamespace(status_code=self.status, headers=self.headers, body=b"")


def test_budget_covers_robots_and_page_requests():
    budget, transport = Budget(), Transport()
    wrapped = BudgetedWikimediaTransport(transport, budget)
    for url in ("https://en.wikibooks.org/robots.txt", REVIEWED_RECIPE_URL):
        wrapped.fetch_once_pinned(url,
                                  connect_ip="1.1.1.1", timeout_seconds=1, max_bytes=10)
    assert budget.calls == transport.calls == 2


def test_rate_limit_reaches_budget_before_it_exits():
    budget, transport = Budget(), Transport(429, {"Retry-After": "120"})
    wrapped = BudgetedWikimediaTransport(transport, budget)
    with pytest.raises(WikimediaRateLimited) as error:
        wrapped.fetch_once_pinned("https://en.wikibooks.org/robots.txt",
                                  connect_ip="1.1.1.1", timeout_seconds=1, max_bytes=10)
    assert budget.error is error.value and error.value.retry_after == "120"


def test_unreviewed_redirect_is_rejected_before_request():
    budget, transport = Budget(), Transport()
    wrapped = BudgetedWikimediaTransport(transport, budget)
    with pytest.raises(ValueError):
        wrapped.fetch_once_pinned("https://en.wikibooks.org/wiki/Cookbook:Other",
                                  connect_ip="1.1.1.1", timeout_seconds=1, max_bytes=10)
    assert budget.calls == transport.calls == 0
