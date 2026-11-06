"""PostgreSQL integration tests for authentication and registration.

These tests exercise the same business rules as the SQLite auth tests
(tests/test_auth_api.py) but run against a dedicated PostgreSQL test database
via the postgres_client fixture. No SQLite-specific constructs are used.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ml_project.config import get_jwt_settings
from ml_project.models import RefreshSession, User, Workspace, WorkspaceMember
from ml_project.security import hash_password, verify_password

TEST_JWT_SECRET = "test-only-secret-key-with-at-least-32-bytes"
TEST_PASSWORD = "Correct test passphrase 2026!"


def _add_user(factory: sessionmaker, *, email: str = "admin@example.com", is_active: bool = True, password: str = TEST_PASSWORD):
    with factory.begin() as session:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Recruitment Admin",
            is_active=is_active,
        )
        session.add(user)
        session.flush()
        return user.id


def _token(client, email: str, password: str = TEST_PASSWORD) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _signed_token(*, secret=TEST_JWT_SECRET, claims=None):
    settings = get_jwt_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "iss": settings.issuer,
        "aud": settings.audience,
    }
    if claims is not None:
        payload.update(claims)
    return jwt.encode(payload, secret, algorithm="HS256")


def test_register_creates_user_workspace_and_admin_membership(postgres_client):
    client, factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 201
    assert response.text == ""

    with factory.begin() as session:
        user = session.scalar(
            select(User).where(func.lower(User.email) == "jordan@example.com")
        )
        assert user is not None
        assert user.full_name == "Jordan Lee"
        assert user.is_active is True
        assert verify_password("UniquePass123", user.password_hash)

        workspace = session.scalar(
            select(Workspace).where(Workspace.created_by_id == user.id)
        )
        assert workspace is not None
        assert workspace.name == "Apex Talent"
        assert workspace.slug.startswith("apex-talent-")

        membership = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id,
            )
        )
        assert membership is not None
        assert membership.role == "ADMIN"


def test_register_normalizes_email(postgres_client):
    client, factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "  JORDAN@EXAMPLE.COM ",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 201

    with factory.begin() as session:
        user = session.scalar(
            select(User).where(func.lower(User.email) == "jordan@example.com")
        )
        assert user is not None
        assert user.email == "jordan@example.com"


def test_register_rejects_duplicate_email(postgres_client):
    client, factory = postgres_client
    _add_user(factory, email="jordan@example.com")

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 409
    assert response.json() == {
        "detail": "A user with this email already exists."
    }


def test_register_can_login_after_registration(postgres_client):
    client, _factory = postgres_client

    client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    login_resp = client.post(
        "/auth/login",
        json={"email": "jordan@example.com", "password": "UniquePass123"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert login_resp.status_code == 200
    body = login_resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60


def test_register_rejects_invalid_email(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "not-an-email",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 422


def test_register_rejects_blank_full_name(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "   ",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 422


def test_register_rejects_short_password(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "short",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 422


def test_register_rejects_blank_workspace_name(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "   ",
        },
    )

    assert response.status_code == 422


def test_register_rejects_missing_fields(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            # missing password and workspace_name
        },
    )

    assert response.status_code == 422


def test_register_does_not_issue_tokens(postgres_client):
    client, _factory = postgres_client

    response = client.post(
        "/auth/register",
        json={
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": "UniquePass123",
            "workspace_name": "Apex Talent",
        },
    )

    assert response.status_code == 201
    assert response.text == ""
    assert response.cookies.get("refresh_token") is None


def test_login_returns_short_lived_bearer_token(postgres_client, jwt_test_configuration):
    client, factory = postgres_client
    user_id = _add_user(factory)

    response = client.post(
        "/auth/login",
        json={"email": " ADMIN@EXAMPLE.COM ", "password": TEST_PASSWORD},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 15 * 60
    assert TEST_PASSWORD not in response.text
    claims = jwt.decode(
        body["access_token"],
        TEST_JWT_SECRET,
        algorithms=["HS256"],
        issuer="test-auth-api",
        audience="test-clients",
        options={"require": ["sub", "iat", "exp", "iss", "aud"]},
    )
    assert claims["sub"] == str(user_id)
    assert "role" not in claims
    assert "workspace_id" not in claims


def test_login_rejects_unknown_user_and_wrong_password_generically(postgres_client):
    client, factory = postgres_client
    _add_user(factory)

    wrong_password = client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "wrong password"}
    )
    unknown_user = client.post(
        "/auth/login", json={"email": "unknown@example.com", "password": "wrong password"}
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()
    assert wrong_password.json()["detail"] == "Invalid email or password."
    assert "admin@example.com" not in unknown_user.text


def test_login_creates_refresh_session_and_cookie(postgres_client):
    client, factory = postgres_client
    _add_user(factory)

    response = client.post(
        "/auth/login",
        json={"email": "admin@example.com", "password": TEST_PASSWORD},
        headers={"Origin": "http://localhost:5173"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert "refresh_token" in response.cookies

    with factory.begin() as session:
        user = session.scalar(
            select(User).where(func.lower(User.email) == "admin@example.com")
        )
        assert user is not None
        refresh_count = session.scalar(
            select(func.count(RefreshSession.id)).where(
                RefreshSession.user_id == user.id
            )
        )
        assert refresh_count >= 1
