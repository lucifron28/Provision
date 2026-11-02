"""Fail-closed PostgreSQL test database and schema ownership helpers."""

from __future__ import annotations

import re
import secrets
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator, Mapping

from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL, make_url

TEST_SCHEMA_PREFIX = "provision_pytest_"
TEST_SCHEMA_MARKER = "__provision_test_owner"
_SCHEMA_RE = re.compile(r"\Aprovision_pytest_[a-f0-9]{32}\Z")


@dataclass(frozen=True)
class OwnedTestSchema:
    database_url: URL
    schema: str
    token: str
    owner: str

    @property
    def scoped_url(self) -> URL:
        return database_url_for_schema(self.database_url, self.schema)


def test_database_url_from_environment(environ: Mapping[str, str]) -> URL:
    """Read only TEST_DATABASE_URL and reject anything that is not a test DB."""
    raw_url = environ.get("TEST_DATABASE_URL")
    if not raw_url:
        raise RuntimeError(
            "TEST_DATABASE_URL must be set to a dedicated PostgreSQL test database; "
            "refusing DATABASE_URL fallback."
        )

    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise RuntimeError("TEST_DATABASE_URL is not a valid SQLAlchemy URL.") from exc

    database = url.database or ""
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("TEST_DATABASE_URL must use PostgreSQL; SQLite tests are disabled.")
    if not database.lower().endswith("_test"):
        raise RuntimeError(
            "TEST_DATABASE_URL database name must end in '_test'; refusing a non-test database."
        )
    return url


def database_url_for_schema(database_url: URL, schema: str) -> URL:
    if not _SCHEMA_RE.fullmatch(schema):
        raise ValueError("Refusing an invalid PostgreSQL test schema name.")
    return database_url.update_query_dict({"options": f"-csearch_path={schema}"})


def create_owned_test_schema(database_url: URL) -> OwnedTestSchema:
    """Create a fresh schema and an identity marker owned by the test role."""
    schema = f"{TEST_SCHEMA_PREFIX}{uuid.uuid4().hex}"
    token = secrets.token_hex(32)
    engine = create_engine(database_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            database, owner, version = connection.execute(
                text(
                    "SELECT current_database(), current_user, "
                    "current_setting('server_version_num')::integer"
                )
            ).one()
            if not str(database).lower().endswith("_test"):
                raise RuntimeError("Connected database is not marked as a test database.")
            if version // 10000 != 18:
                raise RuntimeError(
                    f"PostgreSQL 18 is required for backend tests, found server version {version}."
                )

            connection.execute(text(f'CREATE SCHEMA "{schema}" AUTHORIZATION CURRENT_USER'))
            connection.execute(
                text(
                    f'CREATE TABLE "{schema}"."{TEST_SCHEMA_MARKER}" '
                    "(token text PRIMARY KEY, owner name NOT NULL)"
                )
            )
            connection.execute(
                text(
                    f'INSERT INTO "{schema}"."{TEST_SCHEMA_MARKER}" (token, owner) '
                    "VALUES (:token, current_user)"
                ),
                {"token": token},
            )

        owned = OwnedTestSchema(database_url, schema, token, owner)
        verify_owned_test_schema(owned)
        return owned
    finally:
        engine.dispose()


def verify_owned_test_schema(owned: OwnedTestSchema, connection=None) -> None:
    """Raise unless the schema and its marker still belong to this test run."""
    if not _SCHEMA_RE.fullmatch(owned.schema):
        raise RuntimeError("Refusing to use an unrecognized test schema name.")

    temporary_engine = None
    if connection is None:
        temporary_engine = create_engine(owned.database_url, pool_pre_ping=True)
        connection = temporary_engine.connect()
    try:
        _verify_schema_role(owned, connection)
        marker = connection.execute(
            text(f'SELECT token, owner::text FROM "{owned.schema}"."{TEST_SCHEMA_MARKER}"')
        ).one_or_none()
        if marker is None or marker.token != owned.token or marker.owner != owned.owner:
            raise RuntimeError(
                "PostgreSQL test schema ownership check failed; refusing cleanup or table reset."
            )
    finally:
        if temporary_engine is not None:
            connection.close()
            temporary_engine.dispose()


def _verify_schema_role(owned: OwnedTestSchema, connection) -> None:
    database, current_owner = connection.execute(
        text("SELECT current_database(), current_user")
    ).one()
    schema_owner = connection.execute(
        text(
            "SELECT role.rolname "
            "FROM pg_namespace AS namespace "
            "JOIN pg_roles AS role ON role.oid = namespace.nspowner "
            "WHERE namespace.nspname = :schema"
        ),
        {"schema": owned.schema},
    ).scalar_one_or_none()
    if schema_owner is None:
        raise RuntimeError("Owned PostgreSQL test schema no longer exists.")
    if (
        not str(database).lower().endswith("_test")
        or current_owner != owned.owner
        or schema_owner != owned.owner
    ):
        raise RuntimeError(
            "PostgreSQL test schema ownership check failed; refusing cleanup or table reset."
        )


@contextmanager
def test_schema_without_owner_marker(
    owned: OwnedTestSchema, engine
) -> Iterator[None]:
    """Temporarily remove the marker from a separate importer test schema."""
    with engine.begin() as connection:
        verify_owned_test_schema(owned, connection)
        connection.execute(text(f'DROP TABLE "{owned.schema}"."{TEST_SCHEMA_MARKER}"'))
    try:
        yield
    finally:
        with engine.begin() as connection:
            _verify_schema_role(owned, connection)
            marker_exists = connection.execute(
                text(
                    "SELECT EXISTS (SELECT 1 FROM pg_tables "
                    "WHERE schemaname = :schema AND tablename = :table)"
                ),
                {"schema": owned.schema, "table": TEST_SCHEMA_MARKER},
            ).scalar_one()
            if not marker_exists:
                connection.execute(
                    text(
                        f'CREATE TABLE "{owned.schema}"."{TEST_SCHEMA_MARKER}" '
                        "(token text PRIMARY KEY, owner name NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        f'INSERT INTO "{owned.schema}"."{TEST_SCHEMA_MARKER}" '
                        "(token, owner) VALUES (:token, current_user)"
                    ),
                    {"token": owned.token},
                )
            verify_owned_test_schema(owned, connection)


def clear_owned_test_tables(owned: OwnedTestSchema, engine, tables: list[str]) -> None:
    """Truncate only the known application tables owned by this test schema."""
    if not tables or len(tables) != len(set(tables)):
        raise ValueError("Refusing an empty or duplicate PostgreSQL test table list.")

    quoted_schema = f'"{owned.schema}"'
    qualified_tables = ", ".join(f'{quoted_schema}."{table}"' for table in tables)
    with engine.begin() as connection:
        current_schema = connection.execute(text("SELECT current_schema()" )).scalar_one()
        if current_schema != owned.schema:
            raise RuntimeError("Test connection search_path is outside its owned schema.")
        verify_owned_test_schema(owned, connection)

        actual_tables = set(
            connection.execute(
                text(
                    "SELECT tablename FROM pg_tables "
                    "WHERE schemaname = :schema"
                ),
                {"schema": owned.schema},
            ).scalars()
        )
        expected_tables = set(tables) | {TEST_SCHEMA_MARKER}
        if actual_tables != expected_tables:
            raise RuntimeError(
                "Test schema contains missing or unexpected tables; refusing to truncate."
            )

        unowned = connection.execute(
            text(
                "SELECT c.relname FROM pg_class AS c "
                "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
                "JOIN pg_roles AS r ON r.oid = c.relowner "
                "WHERE n.nspname = :schema AND c.relkind IN ('r', 'p') "
                "AND r.rolname <> current_user"
            ),
            {"schema": owned.schema},
        ).scalars().all()
        if unowned:
            raise RuntimeError(
                f"Test schema contains tables owned by another role: {unowned}; refusing to truncate."
            )

        connection.execute(text(f"TRUNCATE TABLE {qualified_tables} RESTART IDENTITY"))


def drop_owned_test_schema(owned: OwnedTestSchema) -> None:
    """Drop only the schema whose owner and per-run marker both match."""
    verify_engine = create_engine(
        owned.database_url,
        isolation_level="AUTOCOMMIT",
        pool_pre_ping=True,
    )
    try:
        with verify_engine.connect() as connection:
            verify_owned_test_schema(owned, connection)
            connection.execute(text(f'DROP SCHEMA "{owned.schema}" CASCADE'))
    finally:
        verify_engine.dispose()
