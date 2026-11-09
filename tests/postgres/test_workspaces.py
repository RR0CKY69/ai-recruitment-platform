"""PostgreSQL integration tests for workspaces.

These tests exercise workspace business rules against a dedicated PostgreSQL
test database via the postgres_client fixture. No SQLite-specific constructs
are used.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ml_project.models import AuditLog, User, Workspace, WorkspaceMember
from ml_project.security import hash_password

TEST_PASSWORD = "Workspace listing test password"


def _add_user(factory: sessionmaker, email: str):
    with factory.begin() as session:
        user = User( # type: ignore[reportGeneralTypeIssues]
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

def test_admin_can_add_existing_active_user_and_records_audit(postgres_client):
    client, factory = postgres_client
    admin = _add_user(factory, "admin-add@example.test")
    new_member = _add_user(factory, "newmember-add@example.test")
    workspace = _add_workspace_membership(factory, admin, "Add Member Workspace", "ADMIN")
    token = _token(client, "admin-add@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": new_member.email, "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["user_id"] == str(new_member.id)
    assert response.json()["role"] == "RECRUITER"

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == new_member.id,
            )
        ).scalar_one()
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.action == "workspace.member.added",
            )
        ).scalar_one()

        assert membership.role == "RECRUITER"
        assert audit.actor_id == admin.id
        assert audit.details["email"] == new_member.email
        assert audit.details["role"] == "RECRUITER"


def test_admin_can_update_workspace_name_and_records_audit(postgres_client):
    client, factory = postgres_client
    admin = _add_user(factory, "admin-rename@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Original Workspace", "ADMIN"
    )
    token = _token(client, "admin-rename@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}",
        json={"name": "Updated Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Workspace"
    assert response.json()["slug"].startswith("updated-workspace-")
    assert response.json()["slug"] != workspace.slug

    with factory() as session:
        updated_workspace = session.get(Workspace, workspace.id)
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.action == "workspace.updated",
            )
        ).scalar_one()

        assert updated_workspace.name == "Updated Workspace"
        assert audit.actor_id == admin.id
        assert audit.details["old_name"] == "Original Workspace"
        assert audit.details["new_name"] == "Updated Workspace"
        assert audit.details["old_slug"] == workspace.slug
        assert audit.details["new_slug"] == response.json()["slug"]


def test_admin_can_change_member_role_and_records_audit(postgres_client):
    client, factory = postgres_client
    admin = _add_user(factory, "admin-role@example.test")
    member = _add_user(factory, "member-role@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Role Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=member.id,
                role="RECRUITER",
            )
        )

    token = _token(client, "admin-role@example.test")
    response = client.patch(
        f"/workspaces/{workspace.id}/members/{member.id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == member.id,
            )
        ).scalar_one()
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.action == "workspace.member.role_updated",
            )
        ).scalar_one()

        assert membership.role == "ADMIN"
        assert audit.actor_id == admin.id
        assert audit.details["old_role"] == "RECRUITER"
        assert audit.details["new_role"] == "ADMIN"


def test_admin_can_remove_member_and_records_audit(postgres_client):
    client, factory = postgres_client
    admin = _add_user(factory, "admin-remove@example.test")
    member = _add_user(factory, "member-remove@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Remove Member Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=member.id,
                role="RECRUITER",
            )
        )

    token = _token(client, "admin-remove@example.test")
    response = client.delete(
        f"/workspaces/{workspace.id}/members/{member.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == member.id,
            )
        ).scalar_one_or_none()
        audit = session.execute(
            select(AuditLog).where(
                AuditLog.workspace_id == workspace.id,
                AuditLog.action == "workspace.member.removed",
            )
        ).scalar_one()

        assert membership is None
        assert audit.actor_id == admin.id
        assert audit.details["user_id"] == str(member.id)
        assert audit.details["email"] == member.email
        assert audit.details["role"] == "RECRUITER"


def test_last_admin_cannot_be_demoted_or_removed(postgres_client):
    client, factory = postgres_client
    admin = _add_user(factory, "last-admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Last Admin Workspace", "ADMIN"
    )
    token = _token(client, "last-admin@example.test")
    headers = {"Authorization": f"Bearer {token}"}

    demote_response = client.patch(
        f"/workspaces/{workspace.id}/members/{admin.id}",
        json={"role": "RECRUITER"},
        headers=headers,
    )

    assert demote_response.status_code == 409
    assert demote_response.json()["detail"] == (
        "The last workspace administrator cannot be demoted."
    )

    remove_response = client.delete(
        f"/workspaces/{workspace.id}/members/{admin.id}",
        headers=headers,
    )

    assert remove_response.status_code == 409
    assert remove_response.json()["detail"] == (
        "The last workspace administrator cannot be removed."
    )

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == admin.id,
            )
        ).scalar_one()
        audit_count = session.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.workspace_id == workspace.id
            )
        )

        assert membership.role == "ADMIN"
        assert audit_count == 0
