from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from app.core.config import settings
from sqlalchemy.engine import make_url


def engine_options_for_url(database_url: str) -> dict:
    """Return bounded, restart-tolerant SQLAlchemy settings for this URL."""
    parsed = make_url(database_url)
    connect_args = {}
    if parsed.get_backend_name() == "sqlite":
        connect_args["check_same_thread"] = False
    elif "-pooler." in (parsed.host or ""):
        # Neon uses PgBouncer transaction pooling on pooled endpoints. Avoid
        # psycopg's automatic server-side prepared statements across transactions.
        connect_args["prepare_threshold"] = None

    options = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
        "echo": False,
    }
    if parsed.get_backend_name() == "postgresql":
        # Keep a small per-process connection cap and recycle connections that
        # may have outlived a Neon compute suspension or network restart.
        options.update(pool_size=5, max_overflow=0, pool_recycle=300)
    return options

engine = create_engine(
    settings.DATABASE_URL,
    **engine_options_for_url(settings.DATABASE_URL),
)

# Enforce foreign key constraints for SQLite
if settings.DATABASE_URL.startswith("sqlite"):
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency for obtaining a SQLAlchemy session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
