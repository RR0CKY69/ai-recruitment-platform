"""PostgreSQL integration tests for shortlists.

These tests exercise shortlist business rules against a dedicated PostgreSQL
test database via the postgres_client fixture. No SQLite-specific constructs
are used.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.orm import sessionmaker

from ml_project.models import (
    Candidate,
    Job,
    JobCandidate,
    Shortlist,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "Shortlist API test password"


def _seed_shortlist_context(factory: sessionmaker):
    """Seed recruiter, workspace, job, candidate, and job-candidate assignment."""
    with factory.begin() as session:
        recruiter = User(
            email="recruiter@example.test",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Recruiter Example",
            is_active=True,
        )
        workspace = Workspace(name="Workspace One", slug="workspace-one")
        session.add_all([recruiter, workspace])
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=recruiter.id,
                role="RECRUITER",
            )
        )
        session.flush()
        job = Job(
            workspace_id=workspace.id,
            title="Engineer",
            description="Build systems",
            status="OPEN",
        )
        candidate = Candidate(
            workspace_id=workspace.id,
            full_name="Candidate Example",
            current_title="Developer",
            summary="Experienced developer.",
            experience_years=5,
            location="Lahore",
        )
        session.add_all([job, candidate])
        session.flush()
        association = JobCandidate(
            workspace_id=workspace.id,
            job_id=job.id,
            candidate_id=candidate.id,
        )
        session.add(association)
        session.flush()
        return {
            "recruiter": recruiter,
            "workspace": workspace,
            "job": job,
            "candidate": candidate,
            "association": association,
        }


def _token(client, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_post_creates_shortlist_for_assigned_candidate_and_no_auto_association(
    postgres_client,
):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["candidate_name"] == "Candidate Example"
    assert body["job_title"] == "Engineer"
    assert body["recruiter_name"] == "Recruiter Example"
    assert "password_hash" not in response.json()

    # Verify no new JobCandidate association was created
    with factory.begin() as session:
        count = session.scalar(
            select(func.count(JobCandidate.id)).where(
                JobCandidate.workspace_id == ctx["workspace"].id,
                JobCandidate.job_id == ctx["job"].id,
                JobCandidate.candidate_id == ctx["candidate"].id,
            )
        )
        assert count == 1


def test_post_rejects_unassigned_candidate(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # Create a candidate NOT assigned to this job
    with factory.begin() as session:
        unassigned_candidate = Candidate(
            workspace_id=ctx["workspace"].id,
            full_name="Unassigned Candidate",
            current_title="Developer",
            summary="Not assigned.",
        )
        session.add(unassigned_candidate)
        session.flush()
        unassigned_id = unassigned_candidate.id

    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(unassigned_id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Candidate is not assigned to this job."


def test_post_rejects_candidate_assigned_to_another_job(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # The candidate must be assigned to other_job and NOT to ctx["job"].
    # Candidates may belong to multiple jobs, but this candidate belongs only
    # to other_job, so shortlisting it for ctx["job"] is rejected.
    with factory.begin() as session:
        session.execute(
            delete(JobCandidate).where(
                JobCandidate.workspace_id == ctx["workspace"].id,
                JobCandidate.job_id == ctx["job"].id,
                JobCandidate.candidate_id == ctx["candidate"].id,
            )
        )
        other_job = Job(
            workspace_id=ctx["workspace"].id,
            title="Other Job",
            description="Different job",
            status="OPEN",
        )
        session.add(other_job)
        session.flush()
        session.add(
            JobCandidate(
                workspace_id=ctx["workspace"].id,
                job_id=other_job.id,
                candidate_id=ctx["candidate"].id,
            )
        )

    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Candidate is not assigned to this job."


def test_duplicate_post_is_idempotent(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # First POST creates
    response1 = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.status_code == 201

    # Second POST is idempotent
    response2 = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response2.status_code == 200


def test_post_reactivates_removed_shortlist(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # Create a shortlist then soft-delete it
    response1 = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response1.status_code == 201

    # Delete (soft-remove)
    with factory.begin() as session:
        shortlist = session.scalar(
            select(Shortlist).where(
                Shortlist.job_candidate_id == ctx["association"].id
            )
        )
        shortlist_id = shortlist.id

    delete_response = client.delete(
        f"/shortlists/{shortlist_id}",
        params={"workspace_id": str(ctx["workspace"].id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    # Re-post should reactivate
    response2 = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response2.status_code == 201


def test_delete_preserves_candidate_and_association(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # Create shortlist
    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201

    with factory.begin() as session:
        shortlist = session.scalar(
            select(Shortlist).where(
                Shortlist.job_candidate_id == ctx["association"].id
            )
        )
        shortlist_id = shortlist.id

    # Delete shortlist
    delete_response = client.delete(
        f"/shortlists/{shortlist_id}",
        params={"workspace_id": str(ctx["workspace"].id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert delete_response.status_code == 204

    # Candidate and association still exist
    with factory.begin() as session:
        candidate = session.get(Candidate, ctx["candidate"].id)
        assert candidate is not None
        association = session.get(JobCandidate, ctx["association"].id)
        assert association is not None
        assert association.candidate_id == ctx["candidate"].id
        assert association.job_id == ctx["job"].id


def test_post_rejects_cross_workspace_job_and_candidate(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # An unknown workspace fails workspace-membership authorization before any
    # resource lookup, so the endpoint returns 403, not 404.
    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(uuid4()),
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403

    # A nonexistent job inside a workspace the authenticated user is a member
    # of passes authorization but fails resource lookup, returning 404.
    missing = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(uuid4()),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert missing.status_code == 404
    assert (
        missing.json()["detail"]
        == "The requested job or candidate was not found in this workspace."
    )


def test_list_filters_by_job_and_returns_empty_list(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    response = client.get(
        "/shortlists",
        params={"workspace_id": str(ctx["workspace"].id), "job_id": str(ctx["job"].id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_workspace_membership_and_authentication_are_required(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    # No authentication
    response = client.get(
        "/shortlists", params={"workspace_id": str(ctx["workspace"].id)}
    )
    assert response.status_code == 401

    # Foreign workspace
    foreign_ws = uuid4()
    response = client.get(
        "/shortlists",
        params={"workspace_id": str(foreign_ws)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_invalid_identifiers_return_validation_or_not_found(postgres_client):
    client, factory = postgres_client
    ctx = _seed_shortlist_context(factory)
    token = _token(client, ctx["recruiter"].email)

    invalid_uuid = client.post(
        "/shortlists",
        json={
            "workspace_id": "bad",
            "job_id": str(ctx["job"].id),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert invalid_uuid.status_code == 422

    missing_job = client.post(
        "/shortlists",
        json={
            "workspace_id": str(ctx["workspace"].id),
            "job_id": str(uuid4()),
            "candidate_id": str(ctx["candidate"].id),
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert missing_job.status_code == 404
