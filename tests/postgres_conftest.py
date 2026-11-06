"""PostgreSQL integration test fixtures.

Provides a dedicated PostgreSQL test database fixture with transaction-level
isolation. Existing SQLite fixtures and tests in tests/conftest.py are
preserved unchanged.

To use:
    export TEST_DATABASE_URL="postgresql+psycopg://user:pass@localhost:5432/recruitment_test_db"
    python -m pytest tests/test_auth_api.py -q
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app

TEST_DATABASE_URL_ENV = "TEST_DATABASE_URL"
PROTECTED_DATABASE_NAME = "recruitment_db"


def _validate_test_database_url(url: str | None) -> str:
    """Validate TEST_DATABASE_URL is set and safe for testing.

    Raises RuntimeError if the URL is missing, targets the protected
    application database, or is not a PostgreSQL URL.
    """
    if not url:
        raise RuntimeError(
            f"{TEST_DATABASE_URL_ENV} is not set. "
            "Set it to a dedicated PostgreSQL test database URL "
            "(e.g. postgresql+psycopg://user:pass@localhost:5432/recruitment_test_db)."
        )

    if not url.startswith("postgresql+"):
        scheme = url.split("://")[0] if "://" in url else url
        raise RuntimeError(
            f"{TEST_DATABASE_URL_ENV} must be a PostgreSQL URL "
            f"(postgresql+...), got scheme: {scheme}"
        )

    database_name = _database_name_from_url(url)
    if database_name == PROTECTED_DATABASE_NAME:
        raise RuntimeError(
            f"{TEST_DATABASE_URL_ENV} targets the protected database "
            f"'{PROTECTED_DATABASE_NAME}'. Use a dedicated test database instead."
        )

    return url


def _database_name_from_url(url: str) -> str | None:
    """Extract the database name from a SQLAlchemy database URL."""
    try:
        parsed = make_url(url)
    except Exception:  # noqa: BLE001 - intentional broad catch for URL parsing safety
        return None
    return parsed.database


@pytest.fixture
def postgres_client() -> Iterator[tuple[TestClient, sessionmaker]]:
    """Provide a FastAPI TestClient connected to a PostgreSQL test database.

    The fixture:
    - Requires TEST_DATABASE_URL environment variable
    - Validates it does not target the protected application database
    - Creates a SQLAlchemy engine and connection
    - Begins an outer transaction for test isolation
    - Overrides get_api_session with a session factory using savepoints
      so application-level commits do not persist test data
    - Rolls back the outer transaction and disposes the engine on teardown

    Does not create or drop databases, does not run migrations, and does not
    execute destructive SQL.
    """
    url = _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))

    engine = create_engine(url, pool_pre_ping=True)
    connection = engine.connect()
    transaction = connection.begin()

    session_factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_session() -> Iterator[Session]:
        session = session_factory()
        try:
            yield session
        finally:
            session.close()

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_api_session] = override_session

    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        transaction.rollback()
        connection.close()
        engine.dispose()


def test_validate_test_database_url_missing(monkeypatch):
    """Missing TEST_DATABASE_URL raises a safe error without connecting."""
    monkeypatch.delenv(TEST_DATABASE_URL_ENV, raising=False)
    with pytest.raises(RuntimeError, match="is not set"):
        _validate_test_database_url(None)


def test_validate_test_database_url_protected_db(monkeypatch):
    """URL targeting recruitment_db raises a safe error without connecting."""
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://user:pass@localhost:5432/recruitment_db",
    )
    with pytest.raises(RuntimeError, match="protected database"):
        _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))


def test_validate_test_database_url_similar_name_accepted(monkeypatch):
    """Database name recruitment_db_backup is accepted (exact match required)."""
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://user:pass@localhost:5432/recruitment_db_backup",
    )
    result = _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))
    assert result == "postgresql+psycopg://user:pass@localhost:5432/recruitment_db_backup"


def test_validate_test_database_url_password_contains_protected_name(monkeypatch):
    """recruitment_db in the password is accepted when the database name differs."""
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://user:recruitment_db_secret@localhost:5432/test_db",
    )
    result = _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))
    assert result == "postgresql+psycopg://user:recruitment_db_secret@localhost:5432/test_db"


def test_validate_test_database_url_query_contains_protected_name(monkeypatch):
    """recruitment_db in a query parameter is accepted when the database name differs."""
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://user:pass@localhost:5432/test_db?options=recruitment_db",
    )
    result = _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))
    assert result == "postgresql+psycopg://user:pass@localhost:5432/test_db?options=recruitment_db"


def test_validate_test_database_url_non_postgresql(monkeypatch):
    """Non-PostgreSQL URL raises a safe error without connecting."""
    monkeypatch.setenv(TEST_DATABASE_URL_ENV, "sqlite+pysqlite:///:memory:")
    with pytest.raises(RuntimeError, match="PostgreSQL URL"):
        _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))


def test_validate_test_database_url_valid(monkeypatch):
    """Valid PostgreSQL test URL passes validation."""
    monkeypatch.setenv(
        TEST_DATABASE_URL_ENV,
        "postgresql+psycopg://user:pass@localhost:5432/recruitment_test_db",
    )
    result = _validate_test_database_url(os.getenv(TEST_DATABASE_URL_ENV))
    assert result == "postgresql+psycopg://user:pass@localhost:5432/recruitment_test_db"
