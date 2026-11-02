#!/usr/bin/env python3
"""Safely transfer a legacy Provision SQLite database into PostgreSQL."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from sqlalchemy import MetaData, Table, create_engine, func, inspect, select, text
from sqlalchemy.engine import Connection, Engine, URL, make_url
from sqlalchemy.sql.sqltypes import (
    Boolean as BooleanType,
    Date as DateType,
    DateTime as DateTimeType,
    Enum as EnumType,
    Float as FloatType,
    Integer as IntegerType,
    Numeric as NumericType,
)

TABLES_IN_DEPENDENCY_ORDER = [
    "users",
    "products",
    "storage_locations",
    "grocery_sessions",
    "inventory_batches",
    "shopping_list_items",
    "inventory_events",
]
SQLITE_METADATA_TABLES = {"alembic_version"}
LEGACY_IMPORT_REVISION = "a4d9c69b8f21"


class MigrationError(RuntimeError):
    """Raised when the source or target cannot be migrated without data loss."""


def _open_sqlite_read_only(sqlite_path: Path) -> sqlite3.Connection:
    resolved_path = sqlite_path.resolve(strict=True)
    connection = sqlite3.connect(
        f"{resolved_path.as_uri()}?mode=ro",
        uri=True,
        timeout=30,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA query_only = ON")
    return connection


def _copy_wal_consistent_snapshot(sqlite_path: Path, destination_path: Path) -> Path:
    """Use SQLite's backup API so committed WAL pages are included read-only."""
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = destination_path.with_name(
        f".{destination_path.name}.{uuid.uuid4().hex}.tmp"
    )
    source = None
    destination = None
    try:
        source = _open_sqlite_read_only(sqlite_path)
        destination = sqlite3.connect(temporary_path)
        source.backup(destination, pages=256, sleep=0.01)
        integrity = destination.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise MigrationError(f"SQLite snapshot integrity check failed: {integrity}")
        destination.close()
        destination = None
        os.replace(temporary_path, destination_path)
        return destination_path
    finally:
        if destination is not None:
            destination.close()
        if source is not None:
            source.close()
        if temporary_path.exists():
            temporary_path.unlink()


def create_sqlite_backup(sqlite_path: Path, backup_dir: Path) -> Path:
    """Write a timestamped, WAL-consistent backup without writing to SQLite."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_path = backup_dir / f"{sqlite_path.name}.backup.{timestamp}.db"
    return _copy_wal_consistent_snapshot(sqlite_path, backup_path)


def _sqlite_user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'"
    ).fetchall()
    return {row[0] for row in rows if not row[0].startswith("sqlite_")}


def _source_columns(connection: sqlite3.Connection, table_name: str) -> list[str]:
    rows = connection.execute(f'PRAGMA table_info("{table_name}")').fetchall()
    return [row[1] for row in rows]


def _validate_source_tables(connection: sqlite3.Connection) -> None:
    actual_tables = _sqlite_user_tables(connection)
    expected_tables = set(TABLES_IN_DEPENDENCY_ORDER)
    missing = expected_tables - actual_tables
    unexpected = actual_tables - expected_tables - SQLITE_METADATA_TABLES
    if missing:
        raise MigrationError(f"SQLite source is missing required tables: {sorted(missing)}")
    if unexpected:
        raise MigrationError(
            f"SQLite source has tables the importer does not migrate: {sorted(unexpected)}"
        )


def _read_source_rows(
    connection: sqlite3.Connection,
) -> tuple[dict[str, list[str]], dict[str, list[dict[str, Any]]]]:
    _validate_source_tables(connection)
    columns_by_table: dict[str, list[str]] = {}
    rows_by_table: dict[str, list[dict[str, Any]]] = {}
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        columns = _source_columns(connection, table_name)
        if "id" not in columns:
            raise MigrationError(f"SQLite table '{table_name}' has no id column.")
        columns_by_table[table_name] = columns
        rows = connection.execute(
            f'SELECT * FROM "{table_name}" ORDER BY "id"'
        ).fetchall()
        rows_by_table[table_name] = [dict(row) for row in rows]
    return columns_by_table, rows_by_table


def _current_schema(connection: Connection) -> str:
    schema = connection.execute(text("SELECT current_schema()")).scalar_one_or_none()
    if not schema:
        raise MigrationError("PostgreSQL connection has no active schema in search_path.")
    return schema


def _reflect_target_tables(connection: Connection) -> tuple[str, dict[str, Table]]:
    schema = _current_schema(connection)
    inspector = inspect(connection)
    existing = set(inspector.get_table_names(schema=schema))
    missing = set(TABLES_IN_DEPENDENCY_ORDER) - existing
    if missing:
        raise MigrationError(
            "PostgreSQL target is missing tables: "
            f"{sorted(missing)}. Prepare the target at Alembic revision "
            f"{LEGACY_IMPORT_REVISION}, import the SQLite data, then upgrade to head."
        )

    if "alembic_version" not in existing:
        raise MigrationError(
            "Legacy SQLite imports require an Alembic target at revision "
            f"{LEGACY_IMPORT_REVISION}; import the data before upgrading to head."
        )

    version_table = Table(
        "alembic_version", MetaData(), schema=schema, autoload_with=connection
    )
    revision = connection.execute(select(version_table.c.version_num)).scalar_one_or_none()
    if revision != LEGACY_IMPORT_REVISION:
        raise MigrationError(
            "Legacy SQLite imports require the PostgreSQL target at Alembic revision "
            f"{LEGACY_IMPORT_REVISION}. Import the data at that revision, then upgrade to head."
        )

    metadata = MetaData()
    target_tables = {
        name: Table(name, metadata, schema=schema, autoload_with=connection)
        for name in TABLES_IN_DEPENDENCY_ORDER
    }
    return schema, target_tables


def _validate_schema_compatibility(
    columns_by_table: dict[str, list[str]],
    target_tables: dict[str, Table],
) -> None:
    for table_name, source_columns in columns_by_table.items():
        target_table = target_tables[table_name]
        target_columns = set(target_table.c.keys())
        unknown = set(source_columns) - target_columns
        if unknown:
            raise MigrationError(
                f"SQLite table '{table_name}' has columns absent from PostgreSQL: "
                f"{sorted(unknown)}"
            )

        missing_required = [
            column.name
            for column in target_table.columns
            if column.name not in source_columns
            and not column.nullable
            and column.server_default is None
            and column.default is None
            and column.identity is None
            and column.autoincrement is not True
        ]
        if missing_required:
            raise MigrationError(
                f"SQLite table '{table_name}' lacks required PostgreSQL columns: "
                f"{missing_required}"
            )


def _normalize_datetime(value: Any, column_type: DateTimeType) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))

    if column_type.timezone:
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
    elif result.tzinfo is not None:
        result = result.replace(tzinfo=None)
    return result


def _normalize_value(value: Any, column_type: Any) -> Any:
    if value is None:
        return None
    if isinstance(column_type, BooleanType):
        if isinstance(value, bool):
            return value
        if value in (0, 1):
            return bool(value)
        if isinstance(value, str) and value.lower() in {"0", "1", "false", "true"}:
            return value.lower() in {"1", "true"}
        raise MigrationError(f"Cannot convert {value!r} to a PostgreSQL boolean.")
    if isinstance(column_type, DateTimeType):
        return _normalize_datetime(value, column_type)
    if isinstance(column_type, DateType):
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value))
    if isinstance(column_type, FloatType):
        return float(value)
    if isinstance(column_type, NumericType):
        try:
            result = value if isinstance(value, Decimal) else Decimal(str(value))
        except InvalidOperation as exc:
            raise MigrationError(f"Cannot convert {value!r} to a PostgreSQL numeric.") from exc
        if not result.is_finite():
            raise MigrationError(f"Non-finite numeric value cannot be migrated: {value!r}")
        if column_type.scale is not None:
            quantum = Decimal(1).scaleb(-column_type.scale)
            result = result.quantize(quantum, rounding=ROUND_HALF_UP)
        return result
    if isinstance(column_type, IntegerType):
        return int(value)
    if isinstance(column_type, EnumType):
        result = value.value if hasattr(value, "value") else str(value)
        if result not in column_type.enums:
            raise MigrationError(f"Unknown value {result!r} for PostgreSQL enum.")
        return result
    return value


def _prepare_rows(
    table_name: str,
    source_columns: list[str],
    source_rows: list[dict[str, Any]],
    target_table: Table,
) -> list[dict[str, Any]]:
    prepared = []
    for row in source_rows:
        prepared.append(
            {
                column_name: _normalize_value(
                    row[column_name], target_table.c[column_name].type
                )
                for column_name in source_columns
            }
        )
    return prepared


def _assert_target_empty(connection: Connection, schema: str) -> None:
    inspector = inspect(connection)
    for table_name in inspector.get_table_names(schema=schema):
        if table_name == "alembic_version":
            continue
        table = Table(table_name, MetaData(), schema=schema, autoload_with=connection)
        count = connection.execute(select(func.count()).select_from(table)).scalar_one()
        if count:
            raise MigrationError(
                f"PostgreSQL target is not empty: {table_name} contains {count} rows."
            )


def _lock_target_tables(connection: Connection, schema: str) -> None:
    """Block concurrent writes to every existing table through commit/rollback."""
    table_names = sorted(inspect(connection).get_table_names(schema=schema))
    if not table_names:
        return
    preparer = connection.dialect.identifier_preparer
    qualified = ", ".join(
        f"{preparer.quote(schema)}.{preparer.quote(table_name)}"
        for table_name in table_names
    )
    connection.execute(text(f"LOCK TABLE {qualified} IN ACCESS EXCLUSIVE MODE"))


def _verify_rows(
    connection: Connection,
    columns_by_table: dict[str, list[str]],
    rows_by_table: dict[str, list[dict[str, Any]]],
    target_tables: dict[str, Table],
) -> None:
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        source_columns = columns_by_table[table_name]
        source_rows = rows_by_table[table_name]
        target_table = target_tables[table_name]
        target_count = connection.execute(
            select(func.count()).select_from(target_table)
        ).scalar_one()
        if target_count != len(source_rows):
            raise MigrationError(
                f"Row count mismatch for '{table_name}': "
                f"SQLite={len(source_rows)}, PostgreSQL={target_count}."
            )

        primary_key = list(target_table.primary_key.columns)
        if not primary_key or any(column.name not in source_columns for column in primary_key):
            raise MigrationError(
                f"Cannot verify '{table_name}': source does not include its PostgreSQL primary key."
            )
        statement = (
            select(*(target_table.c[name] for name in source_columns))
            .order_by(*primary_key)
        )
        target_rows = connection.execute(statement).mappings().all()
        for source_row, target_row in zip(source_rows, target_rows, strict=True):
            mismatched_columns = []
            for column_name in source_columns:
                column_type = target_table.c[column_name].type
                source_value = _normalize_value(source_row[column_name], column_type)
                target_value = _normalize_value(target_row[column_name], column_type)
                if source_value != target_value:
                    mismatched_columns.append(column_name)
            if mismatched_columns:
                key = tuple(source_row[column.name] for column in primary_key)
                raise MigrationError(
                    f"Value mismatch in '{table_name}' for primary key {key}; "
                    f"columns: {mismatched_columns}."
                )


def _synchronize_sequences(
    connection: Connection,
    schema: str,
    target_tables: dict[str, Table],
) -> None:
    preparer = connection.dialect.identifier_preparer
    for table_name, table in target_tables.items():
        if "id" not in table.c:
            continue
        qualified_name = (
            f'{preparer.quote(schema)}.{preparer.quote(table_name)}'
        )
        sequence_name = connection.execute(
            text("SELECT pg_get_serial_sequence(:table_name, 'id')"),
            {"table_name": qualified_name},
        ).scalar_one_or_none()
        if sequence_name is None:
            continue

        sequence_schema, sequence_relation = connection.execute(
            text(
                "SELECT namespace.nspname, sequence.relname "
                "FROM pg_class AS sequence "
                "JOIN pg_namespace AS namespace ON namespace.oid = sequence.relnamespace "
                "WHERE sequence.oid = to_regclass(:sequence_name)"
            ),
            {"sequence_name": sequence_name},
        ).one()

        max_id = connection.execute(select(func.max(table.c.id))).scalar_one_or_none()
        next_id = max_id + 1 if max_id is not None else 1
        qualified_sequence = (
            f"{preparer.quote(sequence_schema)}.{preparer.quote(sequence_relation)}"
        )
        connection.execute(
            text(f"ALTER SEQUENCE {qualified_sequence} RESTART WITH {int(next_id)}")
        )


def get_sqlite_table_counts(sqlite_path: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    connection = _open_sqlite_read_only(sqlite_path)
    try:
        connection.execute("BEGIN")
        _validate_source_tables(connection)
        for table_name in TABLES_IN_DEPENDENCY_ORDER:
            counts[table_name] = connection.execute(
                f'SELECT COUNT(*) FROM "{table_name}"'
            ).fetchone()[0]
        return counts
    finally:
        connection.close()


def get_postgres_table_counts(engine: Engine) -> dict[str, int]:
    counts: dict[str, int] = {}
    with engine.connect() as connection:
        schema, target_tables = _reflect_target_tables(connection)
        for table_name in TABLES_IN_DEPENDENCY_ORDER:
            counts[table_name] = connection.execute(
                select(func.count()).select_from(target_tables[table_name])
            ).scalar_one()
    return counts


def verify_data(sqlite_path: Path, pg_engine: Engine) -> tuple[bool, str]:
    """Compare schema, row counts, and source values without modifying either DB."""
    try:
        source = _open_sqlite_read_only(sqlite_path)
        try:
            source.execute("BEGIN")
            columns_by_table, rows_by_table = _read_source_rows(source)
            with pg_engine.connect() as connection:
                schema, target_tables = _reflect_target_tables(connection)
                _validate_schema_compatibility(columns_by_table, target_tables)
                _verify_rows(connection, columns_by_table, rows_by_table, target_tables)
                summary = ", ".join(
                    f"{name}={len(rows_by_table[name])}"
                    for name in TABLES_IN_DEPENDENCY_ORDER
                )
            return True, f"SQLite and PostgreSQL values match ({summary})."
        finally:
            source.close()
    except Exception as exc:
        return False, str(exc)


def migrate_data(
    sqlite_path: Path,
    pg_engine: Engine,
    dry_run: bool = False,
) -> tuple[bool, str]:
    """Import into an empty PostgreSQL target and verify before committing."""
    if pg_engine.dialect.name != "postgresql":
        return False, "PostgreSQL is required as the migration target."

    source = None
    try:
        source = _open_sqlite_read_only(sqlite_path)
        source.execute("BEGIN")
        columns_by_table, rows_by_table = _read_source_rows(source)

        with pg_engine.begin() as connection:
            schema, target_tables = _reflect_target_tables(connection)
            _validate_schema_compatibility(columns_by_table, target_tables)
            _lock_target_tables(connection, schema)
            _assert_target_empty(connection, schema)
            prepared_rows = {
                table_name: _prepare_rows(
                    table_name,
                    columns_by_table[table_name],
                    rows_by_table[table_name],
                    target_tables[table_name],
                )
                for table_name in TABLES_IN_DEPENDENCY_ORDER
            }

            if dry_run:
                return True, "Dry-run successful. Target is empty and source values fit the PostgreSQL schema."

            for table_name in TABLES_IN_DEPENDENCY_ORDER:
                rows = prepared_rows[table_name]
                if rows:
                    connection.execute(target_tables[table_name].insert(), rows)

            # Verification happens before commit. Any count or value mismatch
            # raises here and rolls back every inserted row.
            _verify_rows(connection, columns_by_table, rows_by_table, target_tables)

            # Sequence changes happen only after data verification succeeds.
            _synchronize_sequences(connection, schema, target_tables)

        summary = ", ".join(
            f"{name}={len(rows_by_table[name])}"
            for name in TABLES_IN_DEPENDENCY_ORDER
        )
        return True, f"Migration and in-transaction verification completed ({summary})."
    except Exception as exc:
        return False, str(exc)
    finally:
        if source is not None:
            source.close()


def _safe_target_label(url: URL) -> str:
    return f"{url.host or 'local'}:{url.port or 5432}/{url.database or ''}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Safely migrate a legacy Provision SQLite database to PostgreSQL."
    )
    parser.add_argument(
        "--sqlite-path",
        default=os.getenv("SQLITE_DATABASE_PATH", "provision.db"),
        help="Path to the source SQLite file (default: provision.db)",
    )
    parser.add_argument(
        "--postgres-url",
        default=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://provision:provision@127.0.0.1:5432/provision",
        ),
        help="PostgreSQL target URL (default: DATABASE_URL or localhost)",
    )
    parser.add_argument(
        "--backup-dir",
        default=None,
        help="Directory for the timestamped SQLite backup (default: source directory)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Validate without importing rows")
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Compare source schema and values without changing either database",
    )
    args = parser.parse_args(argv)

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.is_file():
        print(f"Error: SQLite source database not found at {sqlite_path}", file=sys.stderr)
        return 1

    try:
        target_url = make_url(args.postgres_url)
        if target_url.get_backend_name() != "postgresql":
            raise MigrationError("PostgreSQL is required as the migration target.")
        print(f"Source SQLite DB: {sqlite_path}")
        print(f"Target PostgreSQL: {_safe_target_label(target_url)}")

        if args.verify_only or args.dry_run:
            with tempfile.TemporaryDirectory(prefix="provision-sqlite-snapshot-") as temp_dir:
                snapshot = _copy_wal_consistent_snapshot(
                    sqlite_path,
                    Path(temp_dir) / "source.snapshot.db",
                )
                pg_engine = create_engine(target_url, pool_pre_ping=True)
                try:
                    if args.verify_only:
                        success, message = verify_data(snapshot, pg_engine)
                    else:
                        success, message = migrate_data(snapshot, pg_engine, dry_run=True)
                finally:
                    pg_engine.dispose()
        else:
            backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else sqlite_path.parent
            backup_path = create_sqlite_backup(sqlite_path, backup_dir)
            print(f"SQLite safety backup: {backup_path}")
            pg_engine = create_engine(target_url, pool_pre_ping=True)
            try:
                success, message = migrate_data(backup_path, pg_engine)
            finally:
                pg_engine.dispose()

        if success:
            print(message)
            return 0
        print(f"Migration failed: {message}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Migration failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
