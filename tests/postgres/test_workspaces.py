"""PostgreSQL integration tests for workspaces.

These tests exercise workspace business rules against a dedicated PostgreSQL
test database via the postgres_client fixture. No SQLite-specific constructs
are used.
"""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from ml_project.models import User, Workspace, WorkspaceMember
from ml_project.security import hash_password

TEST_PASSWORD = "Workspace listing test password"


def _add_user(factory: sessionmaker, email: str):
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


def _add_workspace_membership(
    factory: sessionmaker, user, name: str, role: str
):
    with factory.begin() as session:
        workspace = Workspace(
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


def _token(client, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_lists_multiple_member_workspaces_with_roles(postgres_client):
    client, factory = postgres_client
    user = _add_user(factory, "multi@example.test")
    workspace_b = _add_workspace_membership(factory, user, "Beta Workspace", "RECRUITER")
    workspace_a = _add_workspace_membership(factory, user, "Alpha Workspace", "ADMIN")
    _add_user(factory, "other@example.test")
    token = _token(client, "multi@example.test")

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    workspace_ids = {item["workspace_id"] for item in body}
    assert str(workspace_a.id) in workspace_ids
    assert str(workspace_b.id) in workspace_ids
    roles = {item["workspace_id"]: item["role"] for item in body}
    assert roles[str(workspace_a.id)] == "ADMIN"
    assert roles[str(workspace_b.id)] == "RECRUITER"
    assert "email" not in response.text
    assert "password_hash" not in response.text


def test_user_without_memberships_gets_empty_list(postgres_client):
    client, factory = postgres_client
    _add_user(factory, "unassigned@example.test")
    token = _token(client, "unassigned@example.test")

    response = client.get("/workspaces", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json() == []


def test_unauthenticated_workspace_listing_is_rejected(postgres_client):
    client, _factory = postgres_client

    response = client.get("/workspaces")

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or expired access token."}


def test_user_id_query_cannot_select_another_users_workspaces(postgres_client):
    client, factory = postgres_client
    first_user = _add_user(factory, "first@example.test")
    second_user = _add_user(factory, "second@example.test")
    first_workspace = _add_workspace_membership(
        factory, first_user, "First Workspace", "RECRUITER"
    )
    second_workspace = _add_workspace_membership(
        factory, second_user, "Second Workspace", "ADMIN"
    )
    first_token = _token(client, "first@example.test")

    response = client.get(
        "/workspaces",
        params={"user_id": str(second_user.id)},
        headers={"Authorization": f"Bearer {first_token}"},
    )

    assert response.status_code == 200
    assert [item["workspace_id"] for item in response.json()] == [
        str(first_workspace.id)
    ]
    assert str(second_workspace.id) not in response.text
