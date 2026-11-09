"""PostgreSQL concurrency tests for workspace administration."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, func, select

from ml_project.api.routers.workspaces import _lock_workspace_for_admin
from ml_project.models import AuditLog, User, Workspace, WorkspaceMember
from ml_project.security import hash_password

TEST_PASSWORD = "Workspace concurrency test password"


def test_concurrent_admin_self_demotion_preserves_one_admin(
    postgres_concurrency_client,
    jwt_test_configuration,
):
    client, factory = postgres_concurrency_client
    suffix = uuid4().hex
    emails = [
        f"admin-one-{suffix}@example.test",
        f"admin-two-{suffix}@example.test",
    ]

    workspace_id = None
    user_ids = []

    try:
        with factory.begin() as session:
            users = [
                User(
                    email=email,
                    password_hash=hash_password(TEST_PASSWORD),
                    full_name=f"Concurrency Admin {index}",
                    is_active=True,
                )
                for index, email in enumerate(emails, start=1)
            ]
            session.add_all(users)
            session.flush()
            user_ids = [user.id for user in users]

            workspace = Workspace(
                name=f"Concurrency Test {suffix}",
                slug=f"concurrency-test-{suffix}",
            )
            session.add(workspace)
            session.flush()
            workspace_id = workspace.id

            session.add_all(
                [
                    WorkspaceMember(
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role="ADMIN",
                    )
                    for user in users
                ]
            )

        tokens = []
        for email in emails:
            response = client.post(
                "/auth/login",
                json={"email": email, "password": TEST_PASSWORD},
            )
            assert response.status_code == 200
            tokens.append(response.json()["access_token"])

        barrier = Barrier(2)

        def demote(index: int):
            barrier.wait(timeout=10)
            return client.patch(
                f"/workspaces/{workspace_id}/members/{user_ids[index]}",
                headers={"Authorization": f"Bearer {tokens[index]}"},
                json={"role": "RECRUITER"},
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(demote, index)
                for index in range(2)
            ]
            responses = [future.result(timeout=30) for future in futures]

        assert sorted(response.status_code for response in responses) == [200, 409], [(response.status_code, response.json()) for response in responses]

        with factory() as session:
            roles = session.scalars(
                select(WorkspaceMember.role).where(
                    WorkspaceMember.workspace_id == workspace_id
                )
            ).all()
            audit_count = session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.action == "workspace.member.role_updated",
                )
            )

        assert roles.count("ADMIN") == 1
        assert roles.count("RECRUITER") == 1
        assert audit_count == 1

    finally:
        if workspace_id is not None:
            with factory.begin() as session:
                session.execute(
                    delete(Workspace).where(Workspace.id == workspace_id)
                )
                session.execute(
                    delete(User).where(User.id.in_(user_ids))
                )




def test_admin_recheck_rejects_stale_membership_after_concurrent_demotion(
    postgres_concurrency_client,
):
    _, factory = postgres_concurrency_client
    suffix = uuid4().hex
    emails = [
        f"stale-admin-{suffix}@example.test",
        f"remaining-admin-{suffix}@example.test",
    ]

    workspace_id = None
    user_ids = []

    try:
        with factory.begin() as session:
            users = [
                User(
                    email=email,
                    password_hash=hash_password(TEST_PASSWORD),
                    full_name=f"Stale Admin {index}",
                    is_active=True,
                )
                for index, email in enumerate(emails, start=1)
            ]
            session.add_all(users)
            session.flush()
            user_ids = [user.id for user in users]

            workspace = Workspace(
                name=f"Stale Admin Test {suffix}",
                slug=f"stale-admin-test-{suffix}",
            )
            session.add(workspace)
            session.flush()
            workspace_id = workspace.id

            session.add_all(
                [
                    WorkspaceMember(
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role="ADMIN",
                    )
                    for user in users
                ]
            )

        with factory() as stale_session:
            actor = stale_session.get(User, user_ids[0])
            assert actor is not None

            # Load and retain the ADMIN membership in this session.
            from ml_project.api.dependencies import require_workspace_admin

            require_workspace_admin(stale_session, actor, workspace_id)

            # A separate transaction demotes the actor and commits.
            with factory.begin() as demotion_session:
                membership = demotion_session.scalar(
                    select(WorkspaceMember).where(
                        WorkspaceMember.workspace_id == workspace_id,
                        WorkspaceMember.user_id == user_ids[0],
                    )
                )
                assert membership is not None
                membership.role = "RECRUITER"

            # The stale session must not retain ADMIN authorization.
            with pytest.raises(HTTPException) as error:
                _lock_workspace_for_admin(
                    stale_session,
                    actor,
                    workspace_id,
                )

            assert error.value.status_code == 403

    finally:
        if workspace_id is not None:
            with factory.begin() as session:
                session.execute(
                    delete(Workspace).where(Workspace.id == workspace_id)
                )
                session.execute(
                    delete(User).where(User.id.in_(user_ids))
                )
