"""Shared test fixtures for backend authentication behavior."""

import pytest

from ml_project.api.rate_limit import InMemoryLoginRateLimiter
from ml_project.api.routers import auth as auth_router


@pytest.fixture(autouse=True)
def isolated_login_rate_limiter(monkeypatch):
    """Keep the process-local production limiter isolated between test cases."""
    monkeypatch.setattr(auth_router, "login_rate_limiter", InMemoryLoginRateLimiter())
