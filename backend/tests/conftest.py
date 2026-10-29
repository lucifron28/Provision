import os
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-never-use-in-production")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.main import app as fastapi_app
from app.core.database import get_db
from app.core.security import hash_password, create_access_token
from app.api.v1.endpoints.auth import get_current_user
from app.models.base import Base
from app.models.user import User
import app.models  # noqa: F401
DEFAULT_TEST_POSTGRES_URL = "postgresql+psycopg://provision:provision@127.0.0.1:5432/provision_test"


@pytest.fixture(scope="session")
def engine():
    pg_url = os.getenv("TEST_DATABASE_URL", os.getenv("DATABASE_URL", DEFAULT_TEST_POSTGRES_URL))
    test_engine = None
    try:
        url = make_url(pg_url)
        if url.get_backend_name() == "postgresql":
            target_db = url.database or "provision_test"
            # Connect to maintenance database to ensure test db exists
            maintenance_url = url.set(database="provision")
            try:
                temp_engine = create_engine(maintenance_url, isolation_level="AUTOCOMMIT")
                with temp_engine.connect() as conn:
                    exists = conn.execute(
                        text("SELECT 1 FROM pg_database WHERE datname = :d"),
                        {"d": target_db},
                    ).scalar()
                    if not exists:
                        conn.execute(text(f'CREATE DATABASE "{target_db}"'))
                temp_engine.dispose()
            except Exception:
                pass
            test_engine = create_engine(pg_url, pool_pre_ping=True)
            with test_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
    except Exception as e:
        print(f"\n[CONFTEST WARNING] Failed to connect to PostgreSQL: {e}\n")
        test_engine = None

    if test_engine is None:
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        @event.listens_for(test_engine, "connect")
        def set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    if test_engine.url.get_backend_name() != "postgresql":
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture
def db(engine):
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        if engine.url.get_backend_name() == "postgresql":
            with engine.begin() as conn:
                tables = ", ".join(f'"{t.name}"' for t in reversed(Base.metadata.sorted_tables))
                conn.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE;"))
        else:
            Base.metadata.drop_all(bind=engine)
            Base.metadata.create_all(bind=engine)
@pytest.fixture
def auth_user(db):
    user = User(
        email="testuser@provision.local",
        hashed_password=hash_password("password123"),
        display_name="Test User",
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@pytest.fixture
def auth_headers(auth_user):
    token = create_access_token(subject=auth_user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db, auth_user):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    def override_get_current_user():
        return auth_user

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = override_get_current_user
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(db):
    def override_get_db():
        try:
            yield db
        finally:
            pass

    fastapi_app.dependency_overrides[get_db] = override_get_db
    with TestClient(fastapi_app) as test_client:
        yield test_client
    fastapi_app.dependency_overrides.clear()
