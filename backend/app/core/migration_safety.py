"""Fail-closed target checks for one-off staging database migrations."""

from __future__ import annotations

from collections.abc import Mapping
import time

from sqlalchemy import text
from sqlalchemy.engine import make_url


STAGING_MIGRATION_CONFIRMATION = "MIGRATE_PROVISION_STAGING"
# The two keys encode PROV/ISIO so unrelated database advisory locks do not collide.
_MIGRATION_LOCK_SQL = "SELECT pg_try_advisory_lock(1347577686, 1230195023)"


def _sslmode(url) -> str | None:
    value = url.query.get("sslmode")
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _normalized_neon_host(host: str) -> str:
    return host.lower().replace("-pooler.", ".")


def validate_staging_database_urls(application_url: str, migration_url: str) -> None:
    """Require application and migration traffic to use one TLS Neon staging database."""
    try:
        migration = make_url(migration_url)
    except Exception:
        raise ValueError("Staging database URLs must be valid PostgreSQL URLs") from None

    migration_host = (migration.host or "").lower()
    database = (migration.database or "").lower()
    if migration.get_backend_name() != "postgresql" or not migration_host.endswith(".neon.tech"):
        raise ValueError("Staging migrations must use a direct Neon PostgreSQL endpoint")
    if "-pooler." in migration_host:
        raise ValueError("Staging migrations must use a direct, non-pooled Neon endpoint")
    if "staging" not in database:
        raise ValueError("Staging migration database name must include 'staging'")
    if _sslmode(migration) not in {"require", "verify-ca", "verify-full"}:
        raise ValueError("Staging migration connections must require TLS")

    try:
        application = make_url(application_url)
    except Exception:
        raise ValueError("Staging database URLs must be valid PostgreSQL URLs") from None
    application_host = (application.host or "").lower()
    if (
        application.get_backend_name() != "postgresql"
        or not application_host.endswith(".neon.tech")
        or (application.database or "").lower() != database
        or _normalized_neon_host(application_host) != _normalized_neon_host(migration_host)
        or _sslmode(application) not in {"require", "verify-ca", "verify-full"}
    ):
        raise ValueError("Staging application and migration URLs must target the same Neon staging database")


def acquire_migration_advisory_lock(
    connection,
    *,
    timeout_seconds: float = 600,
    poll_interval_seconds: float = 1,
) -> None:
    """Serialize online PostgreSQL migrations across operators and deploys.

    The session-level lock is released when Alembic closes the connection.
    """
    deadline = time.monotonic() + timeout_seconds
    while True:
        try:
            acquired = bool(connection.scalar(text(_MIGRATION_LOCK_SQL)))
        except Exception:
            raise RuntimeError("Could not acquire PostgreSQL migration lock") from None
        if acquired:
            # The SELECT opens SQLAlchemy's implicit transaction. End it before
            # Alembic starts its own migration transaction. Session locks survive
            # commits and remain held until this connection closes.
            connection.commit()
            return

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("PostgreSQL migration lock wait exceeded its bounded timeout")
        time.sleep(min(poll_interval_seconds, remaining))


def resolve_migration_database_url(settings, environ: Mapping[str, str]) -> str:
    configured_url = (
        settings.MIGRATION_DATABASE_URL.get_secret_value()
        if settings.MIGRATION_DATABASE_URL is not None
        else settings.DATABASE_URL
    )
    if settings.DEPLOYMENT_ENVIRONMENT != "staging":
        return configured_url

    if settings.MIGRATION_DATABASE_URL is None:
        raise RuntimeError("Staging migrations require MIGRATION_DATABASE_URL")
    if environ.get("PROVISION_CONFIRM_STAGING_MIGRATION") != STAGING_MIGRATION_CONFIRMATION:
        raise RuntimeError("Staging migrations require explicit target confirmation")

    try:
        validate_staging_database_urls(settings.DATABASE_URL, configured_url)
    except ValueError as exc:
        raise RuntimeError(str(exc)) from None
    return configured_url
