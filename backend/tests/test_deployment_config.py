import json
from pathlib import Path

from pydantic import SecretStr, ValidationError
import pytest

from app.core.config import LOCAL_DATABASE_URL, Settings
from app.core.database import engine_options_for_url

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_render_container_uses_port_and_ignores_untrusted_forwarded_headers():
    dockerfile = (REPOSITORY_ROOT / "Dockerfile").read_text(encoding="utf-8")
    command_line = next(
        line.removeprefix("CMD ")
        for line in dockerfile.splitlines()
        if line.startswith("CMD ")
    )
    command = json.loads(command_line)
    shell_command = command[2]

    assert "${PORT:-10000}" in shell_command
    assert "--no-proxy-headers" in shell_command
    assert "--forwarded-allow-ips=*" not in shell_command


def test_render_free_staging_blueprint_omits_unsupported_shutdown_override():
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "plan: free" in blueprint
    assert "maxShutdownDelaySeconds" not in blueprint


def test_render_staging_service_uses_blueprint_branch_for_root_dockerfile():
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "branch: main" not in blueprint
    assert "dockerfilePath: ./Dockerfile" in blueprint


def test_render_staging_generates_app_secrets_and_keeps_neon_urls_manual():
    blueprint = (REPOSITORY_ROOT / "render.yaml").read_text(encoding="utf-8")

    assert "- key: DATABASE_URL\n        sync: false" in blueprint
    assert "- key: MIGRATION_DATABASE_URL\n        sync: false" in blueprint
    assert "- key: JWT_SECRET_KEY\n        generateValue: true" in blueprint
    assert "- key: STAGING_TEST_FIXTURE_TOKEN\n        generateValue: true" in blueprint


def settings_for(**values) -> Settings:
    values.setdefault("JWT_SECRET_KEY", "development-test-secret")
    return Settings(_env_file=None, **values)


def test_production_rejects_the_implicit_local_database_default():
    with pytest.raises(ValidationError, match="explicitly configured"):
        settings_for(
            ENVIRONMENT="production",
            DATABASE_URL=LOCAL_DATABASE_URL,
            JWT_SECRET_KEY="s" * 40,
        )


def test_production_requires_a_strong_signing_secret_and_database_tls():
    with pytest.raises(ValidationError, match="at least 32 characters"):
        settings_for(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg://app:secret@db.example.test/provision",
            JWT_SECRET_KEY="short",
        )

    with pytest.raises(ValidationError, match="require TLS"):
        settings_for(
            ENVIRONMENT="production",
            DATABASE_URL="postgresql+psycopg://app:secret@db.example.test/provision",
            JWT_SECRET_KEY="s" * 40,
        )


def test_remote_production_database_accepts_required_tls_and_staging_designation():
    configured = settings_for(
        ENVIRONMENT="production",
        DEPLOYMENT_ENVIRONMENT="staging",
        DATABASE_URL=(
            "postgresql+psycopg://app:secret@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
        MIGRATION_DATABASE_URL=SecretStr(
            "postgresql+psycopg://migrator:secret@ep-staging.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
        JWT_SECRET_KEY="s" * 40,
    )

    assert configured.DEPLOYMENT_ENVIRONMENT == "staging"
    assert configured.MIGRATION_DATABASE_URL is not None


def test_staging_requires_a_matching_direct_neon_migration_target():
    with pytest.raises(ValidationError, match="MIGRATION_DATABASE_URL is required"):
        settings_for(
            ENVIRONMENT="production",
            DEPLOYMENT_ENVIRONMENT="staging",
            DATABASE_URL=(
                "postgresql+psycopg://app:secret@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
                "provision_staging?sslmode=require"
            ),
            JWT_SECRET_KEY="s" * 40,
        )

    with pytest.raises(ValidationError, match="same Neon staging database"):
        settings_for(
            ENVIRONMENT="production",
            DEPLOYMENT_ENVIRONMENT="staging",
            DATABASE_URL=(
                "postgresql+psycopg://app:secret@ep-other-pooler.ap-southeast-1.aws.neon.tech/"
                "provision_staging?sslmode=require"
            ),
            MIGRATION_DATABASE_URL=SecretStr(
                "postgresql+psycopg://migrator:secret@ep-staging.ap-southeast-1.aws.neon.tech/"
                "provision_staging?sslmode=require"
            ),
            JWT_SECRET_KEY="s" * 40,
        )


def test_migrations_reject_a_transaction_pooled_database_url():
    with pytest.raises(ValidationError, match="direct PostgreSQL endpoint"):
        settings_for(
            MIGRATION_DATABASE_URL=(
                "postgresql+psycopg://migrator:secret@db-pooler.example.test/provision?sslmode=require"
            )
        )


def test_invalid_url_validation_does_not_echo_database_credentials():
    with pytest.raises(ValidationError) as caught:
        settings_for(DATABASE_URL="not-a-url-with-secret-fragment")

    assert "secret-fragment" not in str(caught.value)


def test_engine_options_bound_pool_and_disable_auto_prepare_for_neon_pooler():
    options = engine_options_for_url(
        "postgresql+psycopg://app:secret@ep-example-pooler.ap-southeast-1.aws.neon.tech/provision?sslmode=require"
    )

    assert options["pool_pre_ping"] is True
    assert options["pool_size"] == 5
    assert options["max_overflow"] == 0
    assert options["pool_recycle"] == 300
    assert options["connect_args"]["prepare_threshold"] is None
