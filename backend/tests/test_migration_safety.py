from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool
from pydantic import SecretStr

from app.core.migration_safety import (
    STAGING_MIGRATION_CONFIRMATION,
    acquire_migration_advisory_lock,
    resolve_migration_database_url,
)


DIRECT_STAGING_URL = (
    "postgresql+psycopg://migrator:synthetic-test-password@ep-staging.ap-southeast-1.aws.neon.tech/"
    "provision_staging?sslmode=require"
)


def staging_settings(migration_url: str | None = DIRECT_STAGING_URL) -> SimpleNamespace:
    return SimpleNamespace(
        DEPLOYMENT_ENVIRONMENT="staging",
        DATABASE_URL=(
            "postgresql+psycopg://app:synthetic-test-password@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
        MIGRATION_DATABASE_URL=SecretStr(migration_url) if migration_url is not None else None,
    )


def test_staging_migrations_require_a_direct_url_and_confirmation():
    missing_migration_url = SimpleNamespace(
        DEPLOYMENT_ENVIRONMENT="staging",
        DATABASE_URL=staging_settings().DATABASE_URL,
        MIGRATION_DATABASE_URL=None,
    )
    with pytest.raises(RuntimeError, match="require MIGRATION_DATABASE_URL"):
        resolve_migration_database_url(missing_migration_url, {})

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
        DATABASE_URL=(
            "postgresql+psycopg://app:synthetic-test-password@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
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


def test_staging_app_and_migration_urls_must_target_the_same_neon_database():
    confirmed = {"PROVISION_CONFIRM_STAGING_MIGRATION": STAGING_MIGRATION_CONFIRMATION}
    settings = SimpleNamespace(
        DEPLOYMENT_ENVIRONMENT="staging",
        DATABASE_URL=(
            "postgresql+psycopg://app:secret@ep-another-project-pooler.ap-southeast-1.aws.neon.tech/"
            "provision_staging?sslmode=require"
        ),
        MIGRATION_DATABASE_URL=SecretStr(DIRECT_STAGING_URL),
    )

    with pytest.raises(RuntimeError, match="same Neon staging database"):
        resolve_migration_database_url(settings, confirmed)

    settings.DATABASE_URL = (
        "postgresql+psycopg://app:secret@ep-staging-pooler.ap-southeast-1.aws.neon.tech/"
        "another_database?sslmode=require"
    )
    with pytest.raises(RuntimeError, match="same Neon staging database"):
        resolve_migration_database_url(settings, confirmed)


def test_migration_advisory_lock_waits_for_an_existing_runner(monkeypatch):
    class Connection:
        def __init__(self):
            self.results = iter([False, True])
            self.statements = []
            self.commits = 0

        def scalar(self, statement):
            self.statements.append(str(statement))
            return next(self.results)

        def commit(self):
            self.commits += 1

    connection = Connection()
    monkeypatch.setattr("app.core.migration_safety.time.sleep", lambda _: None)

    acquire_migration_advisory_lock(
        connection,
        timeout_seconds=1,
        poll_interval_seconds=0,
    )

    assert len(connection.statements) == 2
    assert all("pg_try_advisory_lock" in statement for statement in connection.statements)
    assert connection.commits == 1


def test_migration_advisory_lock_fails_after_its_bounded_wait(monkeypatch):
    class Connection:
        def scalar(self, _statement):
            return False

    ticks = iter([0.0, 0.0, 1.0])
    monkeypatch.setattr("app.core.migration_safety.time.monotonic", lambda: next(ticks))
    monkeypatch.setattr("app.core.migration_safety.time.sleep", lambda _: None)

    with pytest.raises(RuntimeError, match="migration lock wait exceeded"):
        acquire_migration_advisory_lock(
            Connection(),
            timeout_seconds=1,
            poll_interval_seconds=0,
        )


def test_postgresql_migration_advisory_lock_serializes_connections(engine):
    lock_engine = create_engine(engine.url, poolclass=NullPool)
    try:
        with lock_engine.connect() as migration_owner:
            acquire_migration_advisory_lock(migration_owner)
            with lock_engine.connect() as competing_migration:
                with pytest.raises(RuntimeError, match="migration lock wait exceeded"):
                    acquire_migration_advisory_lock(
                        competing_migration,
                        timeout_seconds=0,
                        poll_interval_seconds=0,
                    )

        with lock_engine.connect() as next_migration:
            acquire_migration_advisory_lock(
                next_migration,
                timeout_seconds=1,
                poll_interval_seconds=0,
            )
    finally:
        lock_engine.dispose()
