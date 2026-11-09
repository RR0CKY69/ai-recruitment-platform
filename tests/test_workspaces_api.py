from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.models import AuditLog, Base, User, Workspace, WorkspaceMember
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


def test_workspace_member_can_view_workspace_details(workspace_client):
    client, factory = workspace_client
    user = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(factory, user, "Admin Workspace", "ADMIN")
    token = _access_token(client, "admin@example.test")

    response = client.get(
        f"/workspaces/{workspace.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "workspace_id": str(workspace.id),
        "name": "Admin Workspace",
        "slug": "admin-workspace",
        "role": "ADMIN",
    }


def test_workspace_member_can_list_workspace_members(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    recruiter = _add_user(factory, "recruiter@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=recruiter.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.get(
        f"/workspaces/{workspace.id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    members = response.json()

    assert len(members) == 2
    assert [member["email"] for member in members] == [
        "admin@example.test",
        "recruiter@example.test",
    ]
    assert [member["role"] for member in members] == ["ADMIN", "RECRUITER"]

    for member in members:
        assert member["membership_id"]
        assert member["user_id"]
        assert member["full_name"]
        assert member["created_at"]
        assert "password_hash" not in member


def test_non_member_cannot_view_another_workspace(workspace_client):
    client, factory = workspace_client
    owner = _add_user(factory, "owner@example.test")
    _add_user(factory, "outsider@example.test")
    workspace = _add_workspace_membership(
        factory, owner, "Private Workspace", "ADMIN"
    )
    token = _access_token(client, "outsider@example.test")

    response = client.get(
        f"/workspaces/{workspace.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_non_member_cannot_list_another_workspace_members(workspace_client):
    client, factory = workspace_client
    owner = _add_user(factory, "owner@example.test")
    _add_user(factory, "outsider@example.test")
    workspace = _add_workspace_membership(
        factory, owner, "Private Workspace", "ADMIN"
    )
    token = _access_token(client, "outsider@example.test")

    response = client.get(
        f"/workspaces/{workspace.id}/members",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_can_add_existing_active_user_and_records_audit(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    new_member = _add_user(factory, "newmember@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": " NEWMEMBER@example.test ", "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["user_id"] == str(new_member.id)
    assert data["email"] == "newmember@example.test"
    assert data["role"] == "RECRUITER"

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
        assert audit.entity_id == new_member.id
        assert audit.details["email"] == "newmember@example.test"
        assert audit.details["role"] == "RECRUITER"


def test_recruiter_cannot_add_workspace_members(workspace_client):
    client, factory = workspace_client
    recruiter = _add_user(factory, "recruiter@example.test")
    new_member = _add_user(factory, "newmember@example.test")
    workspace = _add_workspace_membership(
        factory, recruiter, "Recruiter Workspace", "RECRUITER"
    )
    token = _access_token(client, "recruiter@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": new_member.email, "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_cannot_add_unknown_user(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Admin Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": "unknown@example.test", "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active registered user not found."


def test_admin_cannot_add_inactive_user(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    inactive_user = _add_user(factory, "inactive@example.test")

    with factory.begin() as session:
        stored_user = session.get(User, inactive_user.id)
        stored_user.is_active = False

    workspace = _add_workspace_membership(
        factory, admin, "Admin Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": inactive_user.email, "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Active registered user not found."


def test_admin_cannot_add_existing_workspace_member_again(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    existing_member = _add_user(factory, "member@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Admin Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=existing_member.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.post(
        f"/workspaces/{workspace.id}/members",
        json={"email": existing_member.email, "role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "User is already a member of this workspace."
    )


def test_admin_can_update_workspace_name_and_records_audit(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Original Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}",
        json={"name": "Updated Workspace"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Updated Workspace"
    assert response.json()["slug"].startswith("updated-workspace-")
    assert response.json()["slug"] != workspace.slug
    assert response.json()["role"] == "ADMIN"

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
        assert audit.entity_id == workspace.id
        assert audit.details["old_name"] == "Original Workspace"
        assert audit.details["new_name"] == "Updated Workspace"
        assert audit.details["old_slug"] == workspace.slug
        assert audit.details["new_slug"] == response.json()["slug"]


def test_recruiter_cannot_update_workspace_name(workspace_client):
    client, factory = workspace_client
    recruiter = _add_user(factory, "recruiter@example.test")
    workspace = _add_workspace_membership(
        factory, recruiter, "Recruiter Workspace", "RECRUITER"
    )
    token = _access_token(client, "recruiter@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}",
        json={"name": "Unauthorized Change"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403

    with factory() as session:
        unchanged = session.get(Workspace, workspace.id)
        assert unchanged.name == "Recruiter Workspace"


def test_workspace_name_cannot_be_blank(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Valid Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_workspace_update_rejects_unexpected_fields(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Valid Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}",
        json={
            "name": "Updated Workspace",
            "slug": "changed-slug",
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422


def test_admin_can_promote_recruiter_and_records_audit(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    recruiter = _add_user(factory, "recruiter@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=recruiter.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{recruiter.id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "ADMIN"

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == recruiter.id,
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


def test_admin_can_demote_member_when_another_admin_exists(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    second_admin = _add_user(factory, "secondadmin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=second_admin.id,
                role="ADMIN",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{second_admin.id}",
        json={"role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["role"] == "RECRUITER"


def test_last_admin_cannot_be_demoted(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{admin.id}",
        json={"role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The last workspace administrator cannot be demoted."
    )


def test_recruiter_cannot_change_member_role(workspace_client):
    client, factory = workspace_client
    recruiter = _add_user(factory, "recruiter@example.test")
    another_member = _add_user(factory, "member@example.test")
    workspace = _add_workspace_membership(
        factory, recruiter, "Team Workspace", "RECRUITER"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=another_member.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "recruiter@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{another_member.id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_cannot_change_role_of_non_member(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    outsider = _add_user(factory, "outsider@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{outsider.id}",
        json={"role": "RECRUITER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_invalid_workspace_member_role_is_rejected(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    recruiter = _add_user(factory, "recruiter@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=recruiter.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.patch(
        f"/workspaces/{workspace.id}/members/{recruiter.id}",
        json={"role": "OWNER"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 422

def test_admin_can_remove_member_and_records_audit(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    recruiter = _add_user(factory, "recruiter@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=recruiter.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.delete(
        f"/workspaces/{workspace.id}/members/{recruiter.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["message"] == "Workspace member removed."

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == recruiter.id,
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
        assert audit.details["user_id"] == str(recruiter.id)
        assert audit.details["email"] == recruiter.email
        assert audit.details["role"] == "RECRUITER"


def test_recruiter_cannot_remove_workspace_member(workspace_client):
    client, factory = workspace_client
    recruiter = _add_user(factory, "recruiter@example.test")
    another_member = _add_user(factory, "member@example.test")
    workspace = _add_workspace_membership(
        factory, recruiter, "Team Workspace", "RECRUITER"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=another_member.id,
                role="RECRUITER",
            )
        )

    token = _access_token(client, "recruiter@example.test")

    response = client.delete(
        f"/workspaces/{workspace.id}/members/{another_member.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_cannot_remove_non_member(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    outsider = _add_user(factory, "outsider@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.delete(
        f"/workspaces/{workspace.id}/members/{outsider.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_last_admin_cannot_be_removed(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )
    token = _access_token(client, "admin@example.test")

    response = client.delete(
        f"/workspaces/{workspace.id}/members/{admin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 409
    assert response.json()["detail"] == (
        "The last workspace administrator cannot be removed."
    )

    with factory() as session:
        membership = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == admin.id,
            )
        ).scalar_one()

        assert membership.role == "ADMIN"


def test_admin_can_remove_another_admin_when_one_remains(workspace_client):
    client, factory = workspace_client
    admin = _add_user(factory, "admin@example.test")
    second_admin = _add_user(factory, "secondadmin@example.test")
    workspace = _add_workspace_membership(
        factory, admin, "Team Workspace", "ADMIN"
    )

    with factory.begin() as session:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=second_admin.id,
                role="ADMIN",
            )
        )

    token = _access_token(client, "admin@example.test")

    response = client.delete(
        f"/workspaces/{workspace.id}/members/{second_admin.id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200

    with factory() as session:
        remaining_admins = session.execute(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.role == "ADMIN",
            )
        ).scalars().all()

        assert len(remaining_admins) == 1
        assert remaining_admins[0].user_id == admin.id
