import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-pytest-only-never-use-in-production")

from app.main import app as fastapi_app
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.api.v1.endpoints.auth import get_current_user
from app.models.base import Base
from app.models.user import User
import app.models  # noqa: F401

from database_safety import (
    OwnedTestSchema,
    clear_owned_test_tables,
    create_owned_test_schema,
    drop_owned_test_schema,
    test_database_url_from_environment,
)


@pytest.fixture(scope="session")
def postgres_test_schema() -> OwnedTestSchema:
    database_url = test_database_url_from_environment(os.environ)
    owned_schema = create_owned_test_schema(database_url)
    try:
        yield owned_schema
    finally:
        drop_owned_test_schema(owned_schema)


@pytest.fixture(scope="session")
def engine(postgres_test_schema: OwnedTestSchema):
    test_engine = create_engine(postgres_test_schema.scoped_url, pool_pre_ping=True)
    with test_engine.connect() as connection:
        current_schema = connection.exec_driver_sql("SELECT current_schema()").scalar_one()
        assert current_schema == postgres_test_schema.schema
    from app.core import database as app_database

    app_engine = app_database.engine
    app_database.engine = test_engine
    app_database.SessionLocal.configure(bind=test_engine)
    app_database.settings.DATABASE_URL = postgres_test_schema.scoped_url.render_as_string(
        hide_password=False
    )
    app_engine.dispose()
    Base.metadata.create_all(bind=test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture(autouse=True)
def reset_owned_test_schema(engine, postgres_test_schema):
    """Reset owned tables after every test, including engine-only tests."""
    yield
    clear_owned_test_tables(
        postgres_test_schema,
        engine,
        [table.name for table in Base.metadata.sorted_tables],
    )


@pytest.fixture
def db(engine, postgres_test_schema):
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = testing_session_local()
    try:
        yield session
    finally:
        session.close()


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
        yield db

    def override_get_current_user():
        return auth_user

    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()


@pytest.fixture
def unauthed_client(db):
    def override_get_db():
        yield db

    fastapi_app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(fastapi_app) as test_client:
            yield test_client
    finally:
        fastapi_app.dependency_overrides.clear()
