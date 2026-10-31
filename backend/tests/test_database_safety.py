from dataclasses import replace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from database_safety import (
    OwnedTestSchema,
    database_url_for_schema,
    drop_owned_test_schema,
    test_database_url_from_environment as load_test_database_url,
)


VALID_TEST_URL = "postgresql+psycopg://provision:provision@127.0.0.1:55432/provision_test"
DEVELOPMENT_URL = "postgresql+psycopg://provision:provision@127.0.0.1:55432/provision"


def test_database_url_requires_explicit_test_database_without_dev_fallback():
    with pytest.raises(RuntimeError, match="refusing DATABASE_URL fallback"):
        load_test_database_url({"DATABASE_URL": DEVELOPMENT_URL})


@pytest.mark.parametrize(
    "raw_url",
    [
        DEVELOPMENT_URL,
        "sqlite:///provision_test.db",
    ],
)
def test_database_url_rejects_development_or_sqlite_targets(raw_url):
    with pytest.raises(RuntimeError):
        load_test_database_url({"TEST_DATABASE_URL": raw_url})


def test_database_url_accepts_explicit_postgres_test_database():
    url = load_test_database_url({"TEST_DATABASE_URL": VALID_TEST_URL})
    assert url.database == "provision_test"
    assert url.port == 55432


def test_schema_scoping_rejects_names_outside_owned_prefix():
    database_url = make_url(VALID_TEST_URL)
    with pytest.raises(ValueError, match="test schema name"):
        database_url_for_schema(database_url, "public")


def test_schema_cleanup_refuses_wrong_owner_token(postgres_test_schema):
    mismatched = replace(postgres_test_schema, token="not-the-run-token")
    with pytest.raises(RuntimeError, match="ownership check failed"):
        drop_owned_test_schema(mismatched)

    engine = create_engine(postgres_test_schema.scoped_url)
    try:
        with engine.connect() as connection:
            token = connection.execute(
                text(
                    'SELECT token FROM '
                    f'"{postgres_test_schema.schema}"."__provision_test_owner"'
                )
            ).scalar_one()
            assert token == postgres_test_schema.token
    finally:
        engine.dispose()


def test_schema_cleanup_refuses_non_test_schema_name(postgres_test_schema):
    non_test_schema = OwnedTestSchema(
        database_url=postgres_test_schema.database_url,
        schema="public",
        token=postgres_test_schema.token,
        owner=postgres_test_schema.owner,
    )
    with pytest.raises(RuntimeError, match="unrecognized test schema"):
        drop_owned_test_schema(non_test_schema)
