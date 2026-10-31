from types import SimpleNamespace

import pytest
from app.services.wikimedia_robots import (
    HOST,
    MAX_ROBOTS_BYTES,
    ROBOTS_URL,
    RobotsPolicyError,
    wikimedia_robots_allowed,
)


TARGET = "https://en.wikibooks.org/wiki/Cookbook:Adobo"
USER_AGENT = "ProvisionBot/1.0 (operator@example.com)"


class FakeTransport:
    def __init__(self, body=b"User-agent: *\nDisallow: /w/\n", *, status=200,
                 headers=None, addresses=("93.184.216.34",)):
        self.user_agent = USER_AGENT
        self.body = body
        self.status = status
        self.headers = headers if headers is not None else {"content-type": "text/plain; charset=utf-8"}
        self.addresses = addresses
        self.requests = []
        self.resolutions = []

    def resolve(self, host):
        self.resolutions.append(host)
        return self.addresses

    def fetch_once_pinned(self, url, *, connect_ip, timeout_seconds, max_bytes):
        self.requests.append((url, connect_ip, timeout_seconds, max_bytes))
        return SimpleNamespace(status_code=self.status, headers=self.headers, body=self.body)


def test_current_robots_are_fetched_for_every_decision_with_public_pinned_ip():
    transport = FakeTransport()
    assert wikimedia_robots_allowed(TARGET, transport=transport)
    transport.body = b"User-agent: *\nDisallow: /wiki/Cookbook:\n"
    assert not wikimedia_robots_allowed(TARGET, transport=transport)
    assert transport.resolutions == [HOST, HOST]
    assert len(transport.requests) == 2
    assert transport.requests[0] == (ROBOTS_URL, "93.184.216.34", 8.0, MAX_ROBOTS_BYTES)


def test_specific_agent_groups_are_combined_and_wildcard_is_fallback():
    transport = FakeTransport(
        b"User-agent: *\nDisallow: /\n"
        b"User-agent: provisionbot\nDisallow: /wiki/secret\n"
        b"User-agent: PROVISIONBOT\nAllow: /wiki/Cookbook:\n"
    )
    assert wikimedia_robots_allowed(TARGET, transport=transport)
    assert not wikimedia_robots_allowed(
        "https://en.wikibooks.org/wiki/secret", transport=transport
    )
    transport.user_agent = "OtherBot/1.0 (operator@example.com)"
    assert not wikimedia_robots_allowed(TARGET, transport=transport)


@pytest.mark.parametrize("product", ["ProvisionBot2", "Provision.Bot", "Provision_2-Bot"])
def test_transport_product_names_with_digits_and_periods_match_own_groups(product):
    transport = FakeTransport(
        f"User-agent: *\nDisallow: /\nUser-agent: {product.lower()}\nAllow: /wiki/\n".encode()
    )
    transport.user_agent = f"{product}/1.0 (operator@example.com)"
    assert wikimedia_robots_allowed(TARGET, transport=transport)


@pytest.mark.parametrize("product", ["Mediapartners-Google", "Mediapartners-GoogleBot"])
def test_matching_wildcard_agent_group_fails_closed(product):
    transport = FakeTransport(
        b"User-agent: Mediapartners-Google*\nDisallow: /\n"
        b"User-agent: *\nAllow: /wiki/\n"
    )
    transport.user_agent = f"{product}/1.0 (operator@example.com)"
    with pytest.raises(RobotsPolicyError, match="Ambiguous robots user-agent wildcard"):
        wikimedia_robots_allowed(TARGET, transport=transport)


def test_unrelated_wildcard_agent_group_does_not_block_provision_bot():
    transport = FakeTransport(
        b"User-agent: Mediapartners-Google*\nDisallow: /\n"
        b"User-agent: *\nAllow: /wiki/\n"
    )
    assert wikimedia_robots_allowed(TARGET, transport=transport)


@pytest.mark.parametrize(
    ("rules", "target", "expected"),
    [
        (b"Disallow: /wiki/\nAllow: /wiki/Cookbook:\n", TARGET, True),
        (b"Allow: /wiki/Cookbook:\nDisallow: /wiki/Cookbook:\n", TARGET, True),
        (b"Disallow: /wiki/*Adobo$\n", TARGET, False),
        (b"Disallow: /wiki/*Adobo$\n", TARGET + "_Chicken", True),
        (b"Disallow: /wiki/*ook*Adobo$\n", TARGET, False),
        (b"Disallow: /wiki/cookbook:\n", TARGET, True),
        (b"Disallow: /wiki/Cookbook:%E3%83%84\n", "https://en.wikibooks.org/wiki/Cookbook:%E3%83%84", False),
        (b"Disallow: /wiki/Cookbook:Adobo?x=1\n", TARGET + "?x=1", False),
    ],
)
def test_longest_rules_wildcards_case_percent_encoding_and_query(rules, target, expected):
    transport = FakeTransport(b"User-agent: *\n" + rules)
    assert wikimedia_robots_allowed(target, transport=transport) is expected


@pytest.mark.parametrize("status", [301, 302, 403, 404, 429, 500])
def test_unavailable_robots_and_redirects_fail_closed(status):
    transport = FakeTransport(status=status)
    with pytest.raises(RobotsPolicyError):
        wikimedia_robots_allowed(TARGET, transport=transport)
    assert len(transport.requests) == 1


@pytest.mark.parametrize(
    ("body", "headers"),
    [
        (b"", {"content-type": "text/plain"}),
        (b"User-agent: *\nDisallow: %wrong\n", {"content-type": "text/plain"}),
        (b"\xff", {"content-type": "text/plain"}),
        (b"x" * (MAX_ROBOTS_BYTES + 1), {"content-type": "text/plain"}),
        (b"User-agent: *\n", {"content-type": "text/html"}),
        (b"User-agent: *\n", {"content-type": "text/plain", "content-encoding": "gzip"}),
        (b"User-agent: *\n", {"Content-Type": "text/plain", "content-type": "text/html"}),
    ],
)
def test_invalid_or_oversized_policy_fails_closed(body, headers):
    with pytest.raises(RobotsPolicyError):
        wikimedia_robots_allowed(TARGET, transport=FakeTransport(body, headers=headers))


def test_private_or_mixed_dns_is_rejected_before_connecting():
    transport = FakeTransport(addresses=("93.184.216.34", "127.0.0.1"))
    with pytest.raises(RobotsPolicyError):
        wikimedia_robots_allowed(TARGET, transport=transport)
    assert transport.requests == []


def test_wikibooks_style_rules_apply_to_actual_agent_and_api_paths():
    transport = FakeTransport(
        b"User-agent: Fetch\nDisallow: /\n"
        b"User-agent: *\nAllow: /w/api.php?action=mobileview&\n"
        b"Disallow: /w/\nDisallow: /api/\n"
    )
    assert wikimedia_robots_allowed(TARGET, transport=transport)
    assert not wikimedia_robots_allowed(
        "https://en.wikibooks.org/w/api.php?action=query", transport=transport
    )
    assert wikimedia_robots_allowed(
        "https://en.wikibooks.org/w/api.php?action=mobileview&format=json", transport=transport
    )
    transport.user_agent = "Fetch/1.0 (operator@example.com)"
    assert not wikimedia_robots_allowed(TARGET, transport=transport)


@pytest.mark.parametrize("target", [
    "https://tl.wikibooks.org/wiki/Cookbook:Adobo",
    "https://en.wikibooks.org.evil.example.com/wiki/Cookbook:Adobo",
    "http://en.wikibooks.org/wiki/Cookbook:Adobo",
    "https://en.wikibooks.org/wiki/Cookbook:%41dobo",
])
def test_other_hosts_and_noncanonical_targets_fail_before_dns(target):
    transport = FakeTransport()
    with pytest.raises(RobotsPolicyError):
        wikimedia_robots_allowed(target, transport=transport)
    assert transport.resolutions == []


def test_missing_identity_or_transport_error_fails_closed():
    transport = FakeTransport()
    transport.user_agent = "python-urllib"
    with pytest.raises(RobotsPolicyError):
        wikimedia_robots_allowed(TARGET, transport=transport)
    assert not transport.resolutions

    class BrokenTransport(FakeTransport):
        def fetch_once_pinned(self, *args, **kwargs):
            raise TimeoutError("private transport detail")

    with pytest.raises(RobotsPolicyError, match="policy unavailable") as error:
        wikimedia_robots_allowed(TARGET, transport=BrokenTransport())
    assert "private transport detail" not in str(error.value)


def test_changed_transport_identity_invalidates_the_decision():
    class ChangingTransport(FakeTransport):
        def fetch_once_pinned(self, *args, **kwargs):
            response = super().fetch_once_pinned(*args, **kwargs)
            self.user_agent = "Fetch/1.0 (operator@example.com)"
            return response

    with pytest.raises(RobotsPolicyError, match="user agent changed"):
        wikimedia_robots_allowed(TARGET, transport=ChangingTransport())
