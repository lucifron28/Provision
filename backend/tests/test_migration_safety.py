from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from app.core.config import Settings
from app.core.migration_safety import (
    STAGING_MIGRATION_CONFIRMATION,
    resolve_migration_database_url,
)


DIRECT_STAGING_URL = (
    "postgresql+psycopg://migrator:synthetic-test-password@ep-staging.ap-southeast-1.aws.neon.tech/"
    "provision_staging?sslmode=require"
)


def staging_settings(migration_url: str | None = DIRECT_STAGING_URL) -> Settings:
    values = {
        "_env_file": None,
        "ENVIRONMENT": "production",
        "DEPLOYMENT_ENVIRONMENT": "staging",
        "DATABASE_URL": (
            "postgresql+psycopg://app:synthetic-test-password@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
        "JWT_SECRET_KEY": "synthetic-test-signing-secret-long-enough",
    }
    if migration_url is not None:
        values["MIGRATION_DATABASE_URL"] = SecretStr(migration_url)
    return Settings(**values)


def test_staging_migrations_require_a_direct_url_and_confirmation():
    with pytest.raises(RuntimeError, match="require MIGRATION_DATABASE_URL"):
        resolve_migration_database_url(staging_settings(None), {})

    with pytest.raises(RuntimeError, match="explicit target confirmation"):
        resolve_migration_database_url(staging_settings(), {})


def test_staging_migration_accepts_only_named_tls_neon_database():
    confirmed = {"PROVISION_CONFIRM_STAGING_MIGRATION": STAGING_MIGRATION_CONFIRMATION}
    assert resolve_migration_database_url(staging_settings(), confirmed) == DIRECT_STAGING_URL


@pytest.mark.parametrize(
    "url, error",
    [
        (
            "postgresql+psycopg://migrator:secret@db.example.test/provision_staging?sslmode=require",
            "direct Neon",
        ),
        (
            "postgresql+psycopg://migrator:secret@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require",
            "direct, non-pooled",
        ),
        (
            "postgresql+psycopg://migrator:secret@ep-staging.ap-southeast-1.aws.neon.tech/"
            "neondb?sslmode=require",
            "include 'staging'",
        ),
        (
            "postgresql+psycopg://migrator:secret@ep-staging.ap-southeast-1.aws.neon.tech/"
            "provision_staging",
            "require TLS",
        ),
    ],
)
def test_staging_migration_refuses_unverified_targets(url, error):
    settings = SimpleNamespace(
        DEPLOYMENT_ENVIRONMENT="staging",
        DATABASE_URL="unused",
        MIGRATION_DATABASE_URL=SecretStr(url),
    )
    with pytest.raises(RuntimeError, match=error):
        resolve_migration_database_url(
            settings,
            {"PROVISION_CONFIRM_STAGING_MIGRATION": STAGING_MIGRATION_CONFIRMATION},
        )


def test_local_migrations_keep_the_existing_database_configuration():
    settings = SimpleNamespace(
        DEPLOYMENT_ENVIRONMENT="development",
        DATABASE_URL="postgresql+psycopg://provision:provision@127.0.0.1:5432/provision",
        MIGRATION_DATABASE_URL=None,
    )
    assert resolve_migration_database_url(settings, {}) == settings.DATABASE_URL
