"""Apply a shared request budget to every Wikimedia HTTP request."""

REVIEWED_RECIPE_URL = "https://en.wikibooks.org/wiki/Cookbook:Adobo_Chicken_(Philippine)"
ROBOTS_URL = "https://en.wikibooks.org/robots.txt"


class WikimediaRateLimited(Exception):
    """A Wikimedia request was rate limited; retry information is untrusted."""

    def __init__(self, retry_after: str | None):
        super().__init__("Wikimedia rate limited the request")
        self.retry_after = retry_after


class BudgetedWikimediaTransport:
    """Wrap a pinned transport with a budget shared by all its callers.

    The budget must reserve a request before yielding, persist retry deadlines,
    and fail closed on errors. This wrapper does not approve a source.
    """

    def __init__(self, transport, budget):
        self.transport = transport
        self.budget = budget

    @property
    def user_agent(self):
        return self.transport.user_agent

    def resolve(self, hostname):
        return self.transport.resolve(hostname)

    def fetch_once_pinned(self, url, *, connect_ip, timeout_seconds, max_bytes):
        if url not in {REVIEWED_RECIPE_URL, ROBOTS_URL}:
            raise ValueError("Unsupported Wikimedia destination")
        with self.budget.request():
            response = self.transport.fetch_once_pinned(
                url, connect_ip=connect_ip, timeout_seconds=timeout_seconds, max_bytes=max_bytes
            )
            if response.status_code == 429:
                values = [value for key, value in response.headers.items()
                          if isinstance(key, str) and key.casefold() == "retry-after"]
                retry_after = values[0] if len(values) == 1 and isinstance(values[0], str) else None
                raise WikimediaRateLimited(retry_after)
            return response


def fetch_reviewed_wikibooks(db, household_id, actor_id, url, *, transport, budget, allow_broader_web=False):
    """Fetch an authorized Wikibooks page through a shared request budget."""
    from app.services.deepseek_discovery import fetch_recipe_page

    if url != REVIEWED_RECIPE_URL:
        raise ValueError("Unsupported Wikimedia destination")
    return fetch_recipe_page(
        db, household_id, actor_id, url,
        transport=BudgetedWikimediaTransport(transport, budget),
        allow_broader_web=allow_broader_web,
    )
