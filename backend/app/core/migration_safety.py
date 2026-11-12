"""Fail-closed target checks for one-off staging database migrations."""

from __future__ import annotations

from collections.abc import Mapping

from sqlalchemy.engine import make_url


STAGING_MIGRATION_CONFIRMATION = "MIGRATE_PROVISION_STAGING"


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

    parsed = make_url(configured_url)
    host = (parsed.host or "").lower()
    database = (parsed.database or "").lower()
    if parsed.get_backend_name() != "postgresql" or not host.endswith(".neon.tech"):
        raise RuntimeError("Staging migrations must target a direct Neon PostgreSQL endpoint")
    if "-pooler." in host:
        raise RuntimeError("Staging migrations must use the direct, non-pooled endpoint")
    if "staging" not in database:
        raise RuntimeError("Staging migration database name must include 'staging'")
    sslmode = parsed.query.get("sslmode")
    if isinstance(sslmode, (list, tuple)):
        sslmode = sslmode[0] if sslmode else None
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        raise RuntimeError("Staging migration connections must require TLS")
    return configured_url
