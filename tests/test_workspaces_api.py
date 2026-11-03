from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.models import Base, User, Workspace, WorkspaceMember
from ml_project.security import hash_password

TEST_JWT_SECRET = "workspace-list-test-secret-at-least-32-bytes"
TEST_PASSWORD = "Workspace listing test password"


@pytest.fixture
def workspace_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-workspaces-api")
    monkeypatch.setenv("JWT_AUDIENCE", "test-workspace-clients")
    monkeypatch.setattr("ml_project.config.load_dotenv", lambda *_args, **_kwargs: None)

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    previous_overrides = app.dependency_overrides.copy()
    app.dependency_overrides[get_api_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)
        engine.dispose()


def _add_user(factory, email: str) -> User:
    with factory.begin() as session:
        user = User(
            email=email,
            password_hash=hash_password(TEST_PASSWORD),
            full_name=f"{email.split('@')[0]} User",
            is_active=True,
        )
        session.add(user)
        session.flush()
        return user


def _add_workspace_membership(factory, user: User, name: str, role: str) -> Workspace:
    with factory.begin() as session:
        workspace = Workspace(
            id=uuid4(),
            name=name,
            slug=name.casefold().replace(" ", "-"),
        )
        session.add(workspace)
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=role,
            )
        )
        session.flush()
        return workspace


def _access_token(client: TestClient, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_lists_multiple_member_workspaces_with_roles(workspace_client):
    client, factory = workspace_client
    user = _add_user(factory, "multi@example.test")
    workspace_b = _add_workspace_membership(factory, user, "Beta Workspace", "RECRUITER")
    workspace_a = _add_workspace_membership(factory, user, "Alpha Workspace", "ADMIN")
    _add_user(factory, "other@example.test")
    token = _access_token(client, "multi@example.test")

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == [
        {
            "workspace_id": str(workspace_a.id),
            "name": "Alpha Workspace",
            "slug": "alpha-workspace",
            "role": "ADMIN",
        },
        {
            "workspace_id": str(workspace_b.id),
            "name": "Beta Workspace",
            "slug": "beta-workspace",
            "role": "RECRUITER",
        },
    ]
    assert "email" not in response.text
    assert "password_hash" not in response.text


def test_user_without_memberships_gets_empty_list(workspace_client):
    client, factory = workspace_client
    _add_user(factory, "unassigned@example.test")
    token = _access_token(client, "unassigned@example.test")

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []


def test_unauthenticated_workspace_listing_is_rejected(workspace_client):
    client, _factory = workspace_client

    response = client.get("/workspaces")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token."}


def test_user_id_query_cannot_select_another_users_workspaces(workspace_client):
    client, factory = workspace_client
    first_user = _add_user(factory, "first@example.test")
    second_user = _add_user(factory, "second@example.test")
    first_workspace = _add_workspace_membership(factory, first_user, "First Workspace", "RECRUITER")
    second_workspace = _add_workspace_membership(factory, second_user, "Second Workspace", "ADMIN")
    first_token = _access_token(client, "first@example.test")

    response = client.get(
        "/workspaces",
        params={"user_id": str(second_user.id)},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    assert [item["workspace_id"] for item in response.json()] == [str(first_workspace.id)]
    assert str(second_workspace.id) not in response.text
