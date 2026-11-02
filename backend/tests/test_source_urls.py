import pytest

from app.services.source_urls import (
    canonical_recipe_url,
    normalize_host,
    validate_redirect_hops,
)


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (
            "HTTPS://WWW.Example.com:443/recipe/chicken-adobo/?utm_source=search&FBCLID=abc&b=2&a=1#comments",
            "https://www.example.com/recipe/chicken-adobo/?a=1&b=2",
        ),
        (
            "https://example.com/recipe/adobo?notutm_source=kept&utm_campaign=spring&ref=home&gclid=x",
            "https://example.com/recipe/adobo?notutm_source=kept&ref=home",
        ),
        (
            "https://example.com/recipe/adobo?tag=one&tag=two&utm_medium=email",
            "https://example.com/recipe/adobo?tag=one&tag=two",
        ),
    ],
)
def test_canonical_url_normalizes_host_and_literal_tracking_parameters(
    url: str, expected: str
) -> None:
    assert canonical_recipe_url(url) == expected


def test_tracking_variants_canonicalize_to_one_deduplication_key() -> None:
    first = canonical_recipe_url(
        "https://Example.com/recipe/adobo?utm_source=newsletter&fbclid=one"
    )
    second = canonical_recipe_url("https://example.com/recipe/adobo#recipe")

    assert first == second == "https://example.com/recipe/adobo"


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/recipe/adobo",
        "https://user@example.com/recipe/adobo",
        "https://user:secret@example.com/recipe/adobo",
        "https://example.com:8443/recipe/adobo",
        "https://example.com:/recipe/adobo",
        "https://127.0.0.1/recipe/adobo",
        "https://[::1]/recipe/adobo",
        "https://[::ffff:127.0.0.1]/recipe/adobo",
        "https://localhost/recipe/adobo",
        "https://api.local/recipe/adobo",
        "https://printer.home/recipe/adobo",
        "https://example.test/recipe/adobo",
        "https://example.com/category/adobo",
        "https://example.com/recipe/%2e%2e",
        "https://example.com/recipe/%252e%252e",
        "https://example.com/recipe/adobo?access_token=secret",
        "https://example.com/recipe/adobo?%2561ccess_token=secret",
        "https://example.com/recipe/adobo?next=%0d%0aInjected",
    ],
    ids=[
        "http",
        "username",
        "password",
        "custom-port",
        "empty-port",
        "ipv4-literal",
        "ipv6-loopback",
        "ipv4-mapped-loopback",
        "localhost",
        "local-domain",
        "home-domain",
        "reserved-domain",
        "category-page",
        "encoded-dot-segment",
        "double-encoded-dot-segment",
        "credential-query",
        "double-encoded-credential-query",
        "query-control-character",
    ],
)
def test_canonical_url_rejects_unsafe_or_non_recipe_urls(url: str) -> None:
    with pytest.raises(ValueError):
        canonical_recipe_url(url)


@pytest.mark.parametrize(
    "host",
    [
        "127.0.0.1",
        "::1",
        "[::1]",
        "localhost",
        "service.internal",
        "printer.lan",
        "example.",
        "singlelabel",
        "-bad.example",
        "bad-.example",
        "bad..example",
        "münchen.example",
    ],
)
def test_normalize_host_rejects_ip_local_and_noncanonical_hosts(host: str) -> None:
    with pytest.raises(ValueError):
        normalize_host(host)


def test_normalize_host_accepts_canonical_public_ascii_hostname() -> None:
    assert normalize_host("www.example.com") == "www.example.com"


def test_redirect_plan_allows_only_exact_initial_and_redirect_hosts() -> None:
    plan = validate_redirect_hops(
        initial_source_hosts={"recipes.example.com"},
        redirect_hosts={"www.recipes.example.com"},
        urls=[
            "https://recipes.example.com/recipe/adobo",
            "https://www.recipes.example.com/recipe/adobo",
        ],
        addresses={
            "recipes.example.com": ["8.8.8.8"],
            "www.recipes.example.com": ["1.1.1.1"],
        },
    )

    assert [url for url, _ in plan] == [
        "https://recipes.example.com/recipe/adobo",
        "https://www.recipes.example.com/recipe/adobo",
    ]


@pytest.mark.parametrize(
    ("initial_hosts", "redirect_hosts", "url"),
    [
        (set(), {"recipes.example.com"}, "https://recipes.example.com/recipe/adobo"),
        (
            {"recipes.example.com"},
            {"www.recipes.example.com"},
            "https://shop.recipes.example.com/recipe/adobo",
        ),
        (
            {"recipes.example.com"},
            set(),
            "https://external.example.com/recipe/adobo",
        ),
    ],
    ids=["redirect-host-cannot-be-initial", "no-subdomain-wildcard", "external-escape"],
)
def test_redirect_plan_rejects_unapproved_or_nonexact_hosts(
    initial_hosts: set[str], redirect_hosts: set[str], url: str
) -> None:
    with pytest.raises(ValueError):
        validate_redirect_hops(
            initial_source_hosts=initial_hosts,
            redirect_hosts=redirect_hosts,
            urls=[url],
            addresses={
                "recipes.example.com": ["8.8.8.8"],
                "shop.recipes.example.com": ["8.8.8.8"],
                "external.example.com": ["8.8.8.8"],
            },
        )


def test_redirect_plan_rejects_host_if_any_dns_answer_is_not_public() -> None:
    with pytest.raises(ValueError):
        validate_redirect_hops(
            initial_source_hosts={"recipes.example.com"},
            redirect_hosts=set(),
            urls=["https://recipes.example.com/recipe/adobo"],
            addresses={"recipes.example.com": ["8.8.8.8", "10.0.0.7"]},
        )


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",
        "10.0.0.1",
        "169.254.169.254",
        "192.168.1.20",
        "::1",
        "fc00::1",
        "fe80::1",
        "::ffff:8.8.8.8",
        "2002:0808:0808::",
        "2001:0000::",
        "64:ff9b::808:808",
        "not-an-ip-address",
    ],
    ids=[
        "ipv4-loopback",
        "ipv4-private",
        "ipv4-link-local-metadata",
        "ipv4-private-lan",
        "ipv6-loopback",
        "ipv6-unique-local",
        "ipv6-link-local",
        "ipv4-mapped-ipv6",
        "ipv6-6to4",
        "ipv6-teredo",
        "ipv6-well-known-nat64",
        "invalid-dns-answer",
    ],
)
def test_redirect_plan_rejects_private_or_special_use_dns_addresses(address: str) -> None:
    with pytest.raises(ValueError):
        validate_redirect_hops(
            initial_source_hosts={"recipes.example.com"},
            redirect_hosts=set(),
            urls=["https://recipes.example.com/recipe/adobo"],
            addresses={"recipes.example.com": [address]},
        )


def test_redirect_plan_sorts_and_deduplicates_pinned_public_dns_answers() -> None:
    plan = validate_redirect_hops(
        initial_source_hosts={"recipes.example.com"},
        redirect_hosts=set(),
        urls=["https://recipes.example.com/recipe/adobo"],
        addresses={
            "recipes.example.com": ["2606:4700:4700::1111", "8.8.8.8", "8.8.8.8"]
        },
    )

    assert plan == [
        (
            "https://recipes.example.com/recipe/adobo",
            ("2606:4700:4700::1111", "8.8.8.8"),
        )
    ]


def test_redirect_plan_canonicalizes_equivalent_ipv6_dns_answers() -> None:
    plan = validate_redirect_hops(
        initial_source_hosts={"recipes.example.com"},
        redirect_hosts=set(),
        urls=["https://recipes.example.com/recipe/adobo"],
        addresses={
            "recipes.example.com": [
                "2606:4700:4700:0000:0000:0000:0000:1111",
                "2606:4700:4700::1111",
            ]
        },
    )

    assert plan[0][1] == ("2606:4700:4700::1111",)


@pytest.mark.parametrize("urls", [[], ["https://recipes.example/recipe/adobo"] * 7])
def test_redirect_plan_requires_one_to_six_urls(urls: list[str]) -> None:
    with pytest.raises(ValueError):
        validate_redirect_hops(
            initial_source_hosts={"recipes.example.com"},
            redirect_hosts=set(),
            urls=urls,
            addresses={"recipes.example.com": ["8.8.8.8"]},
        )


def test_redirect_plan_requires_dns_results_for_every_hop() -> None:
    with pytest.raises(ValueError):
        validate_redirect_hops(
            initial_source_hosts={"recipes.example.com"},
            redirect_hosts={"cdn.example.com"},
            urls=[
                "https://recipes.example.com/recipe/adobo",
                "https://cdn.example.com/recipe/adobo",
            ],
            addresses={"recipes.example.com": ["8.8.8.8"]},
        )
