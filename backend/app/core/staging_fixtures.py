"""Exact identifiers reserved for synthetic staging E2E accounts."""

import re

_STAGING_TEST_EMAIL = re.compile(
    r"^provision-e2e\+(?:[0-9a-f]{32}|[0-9]+-[0-9]+-[0-9a-f]{32})@example\.com$",
    re.IGNORECASE,
)


def is_staging_test_account(email: str) -> bool:
    return _STAGING_TEST_EMAIL.fullmatch(email) is not None
