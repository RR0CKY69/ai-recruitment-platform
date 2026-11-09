"""PostgreSQL integration test conftest.

Re-exports the postgres_client fixture from tests.postgres_conftest so it is
available to all tests under tests/postgres/ without modifying existing files.
Also provides a JWT test configuration fixture so token creation and
verification in the PostgreSQL auth tests use the same explicit test
configuration as the SQLite auth tests.
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
from tests.postgres_conftest import TEST_DATABASE_URL_ENV, postgres_client

TEST_JWT_SECRET = "test-only-secret-key-with-at-least-32-bytes"
TEST_JWT_ISSUER = "test-auth-api"
TEST_JWT_AUDIENCE = "test-clients"

__all__ = ["jwt_test_configuration", "postgres_client"]


@pytest.fixture
def jwt_test_configuration(monkeypatch: pytest.MonkeyPatch):
    """Configure JWT signing/verification to use explicit test values.

    The application signs access tokens using get_jwt_settings(), which reads
    JWT_SECRET_KEY / JWT_ISSUER / JWT_AUDIENCE from the environment (loaded
    from .env) on every call. Without this fixture the PostgreSQL client signs
    tokens with the real .env secret while tests decode them with
    TEST_JWT_SECRET, raising jwt.InvalidSignatureError. This fixture mirrors
    tests/test_auth_api.py by overriding the environment so the same explicit
    test configuration is used to create and verify tokens.
    """
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ISSUER", TEST_JWT_ISSUER)
    monkeypatch.setenv("JWT_AUDIENCE", TEST_JWT_AUDIENCE)
    yield


@pytest.fixture
def postgres_concurrency_client() -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    """Provide independent PostgreSQL sessions for concurrent API requests.

    Strictly restricted to the local recruitment_test_db database.
    Unlike postgres_client, requests commit through independent connections.
    """
    url = os.getenv(TEST_DATABASE_URL_ENV)
    if not url:
        raise RuntimeError(f"{TEST_DATABASE_URL_ENV} is not set.")

    try:
        parsed = make_url(url)
    except Exception as exc:
        raise RuntimeError("Invalid PostgreSQL test database URL.") from exc

    if (
        not parsed.drivername.startswith("postgresql+")
        or parsed.host not in {"localhost", "127.0.0.1"}
        or parsed.database != "recruitment_test_db"
    ):
        raise RuntimeError(
            "Concurrency tests require postgresql+ on localhost "
            "and the exact recruitment_test_db database."
        )

    engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=0,
    )
    session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    def override_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_api_session] = override_session

    try:
        with TestClient(app) as client:
            yield client, session_factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()
