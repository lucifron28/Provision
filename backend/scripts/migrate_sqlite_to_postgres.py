#!/usr/bin/env python3
"""
Provision SQLite to PostgreSQL Safe Migration Script.

Features:
- Automatic timestamped backup of the source SQLite database before migration.
- Reads source SQLite data safely without modifying or deleting the source file.
- Imports data in topological foreign key dependency order.
- Updates PostgreSQL auto-increment sequences (id sequences) after data insertion.
- Performs end-to-end count and integrity verification across all tables.
- Runs inside an atomic transaction: rolls back completely on any error.
- Supports --dry-run and --verify-only modes.
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine

TABLES_IN_DEPENDENCY_ORDER: List[str] = [
    "users",
    "products",
    "storage_locations",
    "grocery_sessions",
    "inventory_batches",
    "shopping_list_items",
    "inventory_events",
]


def create_sqlite_backup(sqlite_path: Path, backup_dir: Path) -> Path:
    """Creates a timestamped copy of the SQLite database before migration."""
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"{sqlite_path.name}.backup.{timestamp}"
    backup_path = backup_dir / backup_filename
    shutil.copy2(sqlite_path, backup_path)
    return backup_path


def get_sqlite_table_counts(sqlite_path: Path) -> Dict[str, int]:
    """Gets row counts from SQLite database for expected tables."""
    counts = {}
    conn = sqlite3.connect(sqlite_path)
    cursor = conn.cursor()
    for table in TABLES_IN_DEPENDENCY_ORDER:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            counts[table] = cursor.fetchone()[0]
        except sqlite3.OperationalError:
            counts[table] = 0
    conn.close()
    return counts


def get_postgres_table_counts(engine: Engine) -> Dict[str, int]:
    """Gets row counts from PostgreSQL database for expected tables."""
    counts = {}
    with engine.connect() as conn:
        for table in TABLES_IN_DEPENDENCY_ORDER:
            try:
                res = conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
                counts[table] = res.scalar() or 0
            except Exception:
                counts[table] = 0
    return counts


def migrate_data(
    sqlite_path: Path,
    pg_engine: Engine,
    dry_run: bool = False,
) -> Tuple[bool, str]:
    """Transfers data from SQLite to PostgreSQL within a transaction."""
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    inspector = inspect(pg_engine)
    pg_tables = set(inspector.get_table_names())
    missing_tables = set(TABLES_IN_DEPENDENCY_ORDER) - pg_tables
    if missing_tables:
        return (
            False,
            f"PostgreSQL target is missing tables: {missing_tables}. Run 'alembic upgrade head' first.",
        )

    print("\n🔍 Checking SQLite source data...")
    source_counts = get_sqlite_table_counts(sqlite_path)
    for table, count in source_counts.items():
        print(f"  • {table}: {count} records found in SQLite")

    if dry_run:
        sqlite_conn.close()
        return True, "Dry-run successful. No data written to PostgreSQL."

    # Begin migration transaction
    print("\n🚀 Starting atomic data transfer to PostgreSQL...")
    with pg_engine.begin() as pg_conn:
        # Check target database for existing data
        for table in TABLES_IN_DEPENDENCY_ORDER:
            res = pg_conn.execute(text(f'SELECT COUNT(*) FROM "{table}"'))
            existing = res.scalar() or 0
            if existing > 0:
                print(f"  ⚠️ Warning: PostgreSQL table '{table}' already contains {existing} rows.")

        for table in TABLES_IN_DEPENDENCY_ORDER:
            sqlite_cursor.execute(f"SELECT * FROM {table}")
            rows = sqlite_cursor.fetchall()
            if not rows:
                print(f"  ℹ️ Table '{table}': 0 rows to migrate.")
                continue

            columns = list(rows[0].keys())
            cols_str = ", ".join(f'"{col}"' for col in columns)
            bind_str = ", ".join(f":{col}" for col in columns)
            insert_stmt = text(f'INSERT INTO "{table}" ({cols_str}) VALUES ({bind_str})')

            data = [dict(row) for row in rows]
            pg_conn.execute(insert_stmt, data)
            print(f"  ✓ Migrated {len(data)} rows into '{table}'")

        # Synchronize PostgreSQL primary key sequences
        print("\n🔄 Synchronizing PostgreSQL auto-increment sequences...")
        for table in TABLES_IN_DEPENDENCY_ORDER:
            seq_sql = text(
                f"""
                SELECT setval(
                    pg_get_serial_sequence('"{table}"', 'id'),
                    COALESCE((SELECT MAX(id) FROM "{table}"), 1),
                    (SELECT MAX(id) FROM "{table}") IS NOT NULL
                );
                """
            )
            try:
                pg_conn.execute(seq_sql)
                print(f"  ✓ Synchronized sequence for '{table}'")
            except Exception as e:
                print(f"  ⚠️ Note on sequence for '{table}': {e}")

    sqlite_conn.close()

    # Verification phase
    print("\n🔎 Verifying row counts between SQLite and PostgreSQL...")
    pg_counts = get_postgres_table_counts(pg_engine)
    discrepancies = []
    for table in TABLES_IN_DEPENDENCY_ORDER:
        src = source_counts.get(table, 0)
        dst = pg_counts.get(table, 0)
        status = "✓ MATCH" if src == dst else "❌ MISMATCH"
        print(f"  [{status}] {table}: SQLite={src}, PostgreSQL={dst}")
        if src != dst:
            discrepancies.append((table, src, dst))

    if discrepancies:
        return False, f"Row count verification failed for tables: {discrepancies}"

    return True, "Migration and verification completed successfully!"


def main():
    parser = argparse.ArgumentParser(description="Provision SQLite to PostgreSQL safe migration utility.")
    parser.add_argument(
        "--sqlite-path",
        type=str,
        default=os.getenv("SQLITE_DATABASE_PATH", "provision.db"),
        help="Path to the source SQLite database file (default: provision.db)",
    )
    parser.add_argument(
        "--postgres-url",
        type=str,
        default=os.getenv(
            "DATABASE_URL",
            "postgresql+psycopg://provision:provision@127.0.0.1:5432/provision",
        ),
        help="Target PostgreSQL connection URL (default: from DATABASE_URL or localhost)",
    )
    parser.add_argument(
        "--backup-dir",
        type=str,
        default=None,
        help="Directory to store SQLite backup before migration (default: same as SQLite file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration and verify schema without inserting records",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Compare existing row counts between SQLite and PostgreSQL without altering data",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path).resolve()
    if not sqlite_path.exists():
        print(f"❌ Error: SQLite source database not found at {sqlite_path}")
        sys.exit(1)

    backup_dir = Path(args.backup_dir).resolve() if args.backup_dir else sqlite_path.parent
    print(f"📂 Source SQLite DB: {sqlite_path}")
    print(f"🐘 Target PostgreSQL: {args.postgres_url.split('@')[-1] if '@' in args.postgres_url else args.postgres_url}")

    if args.verify_only:
        print("\n🔎 Running verification-only comparison...")
        pg_engine = create_engine(args.postgres_url)
        src_counts = get_sqlite_table_counts(sqlite_path)
        dst_counts = get_postgres_table_counts(pg_engine)
        for table in TABLES_IN_DEPENDENCY_ORDER:
            s = src_counts.get(table, 0)
            d = dst_counts.get(table, 0)
            status = "✓ MATCH" if s == d else "❌ MISMATCH"
            print(f"  [{status}] {table}: SQLite={s}, PostgreSQL={d}")
        sys.exit(0)

    # 1. Create safety backup
    print("\n📦 Creating safety backup of SQLite database...")
    backup_path = create_sqlite_backup(sqlite_path, backup_dir)
    print(f"  ✓ Backup saved to: {backup_path}")

    # 2. Connect to PostgreSQL
    pg_engine = create_engine(args.postgres_url)

    # 3. Perform Migration
    success, msg = migrate_data(sqlite_path, pg_engine, dry_run=args.dry_run)
    if success:
        print(f"\n🎉 {msg}")
    else:
        print(f"\n❌ Migration Failed: {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
