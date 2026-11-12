import pytest

from app.core.staging_target import validate_staging_api_base_url, verify_staging_deployment


@pytest.mark.parametrize(
    "value",
    [
        "http://provision-staging.onrender.com/api/v1",
        "https://production.example.com/api/v1",
        "https://provision-staging.onrender.com.evil.example/api/v1",
        "https://user:password@provision-staging.onrender.com/api/v1",
        "https://provision-staging.onrender.com:444/api/v1",
        "https://provision-staging.onrender.com/api/v1?token=secret",
        "https://provision-staging.onrender.com/api/v1#fragment",
        "https://provision-staging.onrender.com/",
    ],
)
def test_staging_api_url_rejects_non_render_or_unsafe_targets(value):
    with pytest.raises(ValueError):
        validate_staging_api_base_url(value)


def test_staging_api_url_accepts_the_render_hostname_and_normalizes_trailing_slash():
    assert validate_staging_api_base_url(
        "https://Provision-Staging.onrender.com/api/v1/"
    ) == "https://provision-staging.onrender.com/api/v1"


def test_preflight_checks_render_health_readiness_and_exact_revision():
    commit = "a" * 40

    class Response:
        def __init__(self, status_code, body=None):
            self.status_code = status_code
            self.body = body or {}

        def json(self):
            return self.body

    class Client:
        def __init__(self):
            self.urls = []

        def get(self, url):
            self.urls.append(url)
            if url.endswith("/health"):
                return Response(200, {"deployment": "staging", "revision": commit})
            return Response(200, {"status": "ready"})

    client = Client()

    verify_staging_deployment(
        client,
        "https://provision-staging.onrender.com/api/v1",
        commit,
        sleep=lambda _: None,
    )

    assert client.urls == [
        "https://provision-staging.onrender.com/health",
        "https://provision-staging.onrender.com/ready",
    ]


def test_preflight_rejects_wrong_revision_before_credentials_are_used():
    class Response:
        status_code = 200

        def json(self):
            return {"deployment": "staging", "revision": "b" * 40}

    class Client:
        def get(self, _url):
            return Response()

    with pytest.raises(RuntimeError, match="requested commit"):
        verify_staging_deployment(
            Client(),
            "https://provision-staging.onrender.com/api/v1",
            "a" * 40,
            attempts=1,
            sleep=lambda _: None,
        )


def test_preflight_rejects_database_that_is_not_ready():
    commit = "a" * 40

    class Response:
        def __init__(self, body):
            self.status_code = 200
            self.body = body

        def json(self):
            return self.body

    class Client:
        def get(self, url):
            if url.endswith("/health"):
                return Response({"deployment": "staging", "revision": commit})
            return Response({"status": "not_ready"})

    with pytest.raises(RuntimeError, match="database readiness"):
        verify_staging_deployment(
            Client(),
            "https://provision-staging.onrender.com/api/v1",
            commit,
            attempts=1,
            sleep=lambda _: None,
        )
