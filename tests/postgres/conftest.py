"""PostgreSQL integration test conftest.

Re-exports the postgres_client fixture from tests.postgres_conftest so it is
available to all tests under tests/postgres/ without modifying existing files.
Also provides a JWT test configuration fixture so token creation and
verification in the PostgreSQL auth tests use the same explicit test
configuration as the SQLite auth tests.
"""

from __future__ import annotations

import pytest

from tests.postgres_conftest import postgres_client

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
