from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select
from urllib.parse import urlsplit

from app.core.config import settings
from app.models.user import User
from scripts import staging_e2e_smoke, staging_live_deepseek_smoke
from test_food_safety import catalog as allergen_catalog


RENDER_API_URL = "https://provision-staging.onrender.com/api/v1"
REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("workflow", "cleanup_step"),
    [
        ("staging-e2e.yml", "Remove the run-owned synthetic households"),
        ("live-deepseek-smoke.yml", "Remove the run-owned synthetic household"),
    ],
)
def test_workflow_cleanup_runs_after_attempted_fixture_creation(workflow, cleanup_step):
    workflow_text = (REPOSITORY_ROOT / ".github" / "workflows" / workflow).read_text(
        encoding="utf-8"
    )
    lines = workflow_text.splitlines()
    step_index = next(
        index for index, line in enumerate(lines) if line.strip() == f"- name: {cleanup_step}"
    )

    fixture_step_index = next(
        index for index, line in enumerate(lines) if line.strip() == "id: staging-fixture"
    )

    assert fixture_step_index < step_index
    assert (
        lines[step_index + 1].strip()
        == "if: always() && steps.staging-fixture.outcome != 'skipped'"
    )


@pytest.mark.parametrize("workflow", ["staging-e2e.yml", "live-deepseek-smoke.yml"])
def test_workflow_revision_check_uses_bash_3_2_compatible_case_normalization(workflow):
    workflow_text = (
        REPOSITORY_ROOT / ".github" / "workflows" / workflow
    ).read_text(encoding="utf-8")

    assert "tr '[:upper:]' '[:lower:]'" in workflow_text
    assert "${PROVISION_EXPECTED_RENDER_COMMIT,,}" not in workflow_text


def test_staging_workflow_runs_authenticated_and_offline_recovery_ui_smokes():
    workflow = (
        REPOSITORY_ROOT / ".github" / "workflows" / "staging-e2e.yml"
    ).read_text(encoding="utf-8")

    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testStagingLoginAndRelaunch"
    ) in workflow
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testCookWithPipLoadingEmptyAndOfflineRecovery"
    ) in workflow
    assert (
        "-only-testing:frontendUITests/CookWithPipUITests/"
        "testShoppingOfflineRetryAndStalePreviewRecovery"
    ) in workflow


def test_cleanup_is_a_no_op_when_fixture_creation_registered_no_account(monkeypatch, capsys):
    for suffix in ("", *(f"_{number}" for number in range(2, 11))):
        monkeypatch.delenv(f"PROVISION_STAGING_TEST_EMAIL{suffix}", raising=False)
        monkeypatch.delenv(f"PROVISION_STAGING_TEST_PASSWORD{suffix}", raising=False)

    staging_e2e_smoke.cleanup()

    assert "No staging E2E account was created" in capsys.readouterr().out


def test_prepare_preflights_and_persists_cleanup_credentials_before_registration(
    monkeypatch, tmp_path
):
    events = []
    env_file = tmp_path / "github-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("PROVISION_STAGING_API_BASE_URL", RENDER_API_URL)
    monkeypatch.setenv("PROVISION_STAGING_FIXTURE_TOKEN", "synthetic-fixture-token")
    monkeypatch.setattr(staging_e2e_smoke, "preflight", lambda: events.append("preflight"))
    monkeypatch.setattr(
        staging_e2e_smoke,
        "_remember_account",
        lambda *_args, **_kwargs: events.append("remember"),
    )

    def register(*_args):
        events.append("register")
        return {"default_household_id": 10}

    monkeypatch.setattr(staging_e2e_smoke, "_register", register)

    staging_e2e_smoke.prepare()

    assert events == ["preflight", "remember", "register", "remember"]


def test_api_smoke_preflights_before_login(monkeypatch):
    events = []
    monkeypatch.setattr(staging_e2e_smoke, "preflight", lambda: events.append("preflight"))
    monkeypatch.setenv("PROVISION_STAGING_TEST_EMAIL", "synthetic@example.com")
    monkeypatch.setenv("PROVISION_STAGING_TEST_PASSWORD", "synthetic-password")
    monkeypatch.setenv("PROVISION_STAGING_TEST_HOUSEHOLD_ID", "10")

    def login(*_args):
        events.append("login")
        raise RuntimeError("stop after order assertion")

    monkeypatch.setattr(staging_e2e_smoke, "_login", login)

    with pytest.raises(RuntimeError, match="order assertion"):
        staging_e2e_smoke.api_smoke()

    assert events == ["preflight", "login"]


def test_live_deepseek_preflights_before_authentication(monkeypatch):
    events = []
    monkeypatch.setenv("PROVISION_LIVE_DEEPSEEK_ENABLED", "true")
    monkeypatch.setenv(
        "PROVISION_LIVE_DEEPSEEK_CONFIRMATION",
        staging_live_deepseek_smoke.CONFIRMATION,
    )
    monkeypatch.setenv("PROVISION_STAGING_API_BASE_URL", RENDER_API_URL)
    monkeypatch.setenv("PROVISION_EXPECTED_RENDER_COMMIT", "a" * 40)
    monkeypatch.setenv("PROVISION_STAGING_TEST_EMAIL", "synthetic@example.com")
    monkeypatch.setenv("PROVISION_STAGING_TEST_PASSWORD", "synthetic-password")
    monkeypatch.setenv("PROVISION_STAGING_TEST_HOUSEHOLD_ID", "10")
    monkeypatch.setattr(
        staging_live_deepseek_smoke,
        "verify_staging_deployment",
        lambda *_args, **_kwargs: events.append("preflight"),
    )

    def request(*_args, **_kwargs):
        events.append("authenticated-request")
        raise RuntimeError("stop after order assertion")

    monkeypatch.setattr(staging_live_deepseek_smoke, "_request", request)

    with pytest.raises(RuntimeError, match="order assertion"):
        staging_live_deepseek_smoke.run_one_request()

    assert events == ["preflight", "authenticated-request"]


def test_live_deepseek_remains_disabled_without_validation_toggle(monkeypatch):
    monkeypatch.setenv("PROVISION_LIVE_DEEPSEEK_ENABLED", "false")
    monkeypatch.setenv(
        "PROVISION_LIVE_DEEPSEEK_CONFIRMATION",
        staging_live_deepseek_smoke.CONFIRMATION,
    )
    monkeypatch.setattr(
        staging_live_deepseek_smoke,
        "_request",
        lambda *_args, **_kwargs: pytest.fail("disabled workflow sent an authenticated request"),
    )

    with pytest.raises(RuntimeError, match="remains disabled"):
        staging_live_deepseek_smoke.run_one_request()


def test_api_smoke_runs_against_local_test_api_and_cleans_its_accounts(
    unauthed_client, db, allergen_catalog, monkeypatch, tmp_path
):
    token = "synthetic-local-fixture-token"
    env_file = tmp_path / "github-env"
    env_file.write_text("", encoding="utf-8")
    monkeypatch.setenv("GITHUB_ENV", str(env_file))
    monkeypatch.setenv("PROVISION_STAGING_API_BASE_URL", RENDER_API_URL)
    monkeypatch.setenv("PROVISION_STAGING_FIXTURE_TOKEN", token)
    monkeypatch.setattr(settings, "DEPLOYMENT_ENVIRONMENT", "staging")
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURES_ENABLED", True)
    monkeypatch.setattr(settings, "STAGING_TEST_FIXTURE_TOKEN", SecretStr(token))
    monkeypatch.setattr(staging_e2e_smoke, "preflight", lambda: None)
    monkeypatch.setattr(staging_e2e_smoke, "print", lambda *_args, **_kwargs: None, raising=False)
    class LocalClient:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def request(self, method, url, **kwargs):
            kwargs.pop("timeout", None)
            return unauthed_client.request(method, urlsplit(url).path, **kwargs)

        def get(self, url, **kwargs):
            return self.request("GET", url, **kwargs)

        def delete(self, url, **kwargs):
            return self.request("DELETE", url, **kwargs)

    monkeypatch.setattr(
        staging_e2e_smoke.httpx,
        "Client",
        lambda *_args, **_kwargs: LocalClient(),
    )

    staging_e2e_smoke.prepare()
    for line in env_file.read_text(encoding="utf-8").splitlines():
        name, value = line.split("=", 1)
        monkeypatch.setenv(name, value)
    staging_e2e_smoke.api_smoke()
    staging_e2e_smoke.cleanup()

    remaining_fixtures = db.scalar(
        select(func.count()).select_from(User).where(User.email.like("provision-e2e+%@example.com"))
    )
    assert remaining_fixtures == 0
