"""PostgreSQL integration tests for evaluations.

These tests exercise evaluation business rules against a dedicated PostgreSQL
test database via the postgres_client fixture. No SQLite-specific constructs
are used.
"""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from ml_project.models import (
    Candidate,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "Evaluation API test password"


def _seed_evaluation_context(factory: sessionmaker):
    """Seed reviewer, workspace, job, candidate, and job-candidate pair."""
    with factory.begin() as session:
        reviewer = User(
            email="reviewer@example.test",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Reviewer One",
            is_active=True,
        )
        workspace = Workspace(name="Workspace One", slug="workspace-one")
        session.add_all([reviewer, workspace])
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id, user_id=reviewer.id, role="RECRUITER"
            )
        )
        session.flush()
        job = Job(
            workspace_id=workspace.id,
            legacy_job_id="J001",
            title="Backend Engineer",
            description="Build services",
            status="OPEN",
        )
        candidate = Candidate(
            workspace_id=workspace.id,
            legacy_candidate_id="C001",
            full_name="Candidate One",
            email="private-candidate@example.test",
            current_title="Developer",
            summary="Candidate profile",
        )
        session.add_all([job, candidate])
        session.flush()
        pair = JobCandidate(
            workspace_id=workspace.id,
            job_id=job.id,
            candidate_id=candidate.id,
            created_by_id=reviewer.id,
        )
        session.add(pair)
        session.flush()
        return SimpleNamespace(
            reviewer=reviewer,
            workspace=workspace,
            job=job,
            candidate=candidate,
            pair=pair,
        )


def _payload(context, **updates):
    return {
        "workspace_id": str(context.workspace.id),
        "job_id": str(context.job.id),
        "candidate_id": str(context.candidate.id),
        "expected_updated_at": None,
        "relevance_label": 2,
        "review_status": "reviewed",
        **updates,
    }


def _token(client, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_get_evaluations_returns_workspace_labels_and_notes(postgres_client):
    client, factory = postgres_client
    ctx = _seed_evaluation_context(factory)
    token = _token(client, ctx.reviewer.email)

    label = EvaluationLabel(
        job_candidate_id=ctx.pair.id,
        reviewer_id=ctx.reviewer.id,
        relevance_label=2,
        review_status="REVIEWED",
    )
    label.notes.append(
        EvaluationNote(author_id=ctx.reviewer.id, note="Strong Python evidence.")
    )
    with factory.begin() as session:
        session.add(label)
        session.flush()

    response = client.get(
        "/evaluations",
        params={"workspace_id": str(ctx.workspace.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["job_id"] == str(ctx.job.id)
    assert item["legacy_job_id"] == "J001"
    assert item["candidate_id"] == str(ctx.candidate.id)
    assert item["legacy_candidate_id"] == "C001"
    assert item["relevance_label"] == 2
    assert item["review_status"] == "reviewed"
    assert item["reviewer_name"] == "Reviewer One"
    assert item["notes"][0]["note"] == "Strong Python evidence."
    assert "password_hash" not in response.text
    assert "private-candidate@example.test" not in response.text


def test_get_evaluations_returns_pending_for_pair_without_label(postgres_client):
    client, factory = postgres_client
    ctx = _seed_evaluation_context(factory)
    token = _token(client, ctx.reviewer.email)

    response = client.get(
        "/evaluations",
        params={"workspace_id": str(ctx.workspace.id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["relevance_label"] is None
    assert response.json()[0]["review_status"] == "needs_human_review"


def test_evaluation_retrieval_requires_authentication_and_workspace_membership(
    postgres_client,
):
    client, factory = postgres_client
    ctx = _seed_evaluation_context(factory)
    token = _token(client, ctx.reviewer.email)

    # No token at all
    response = client.get(
        "/evaluations", params={"workspace_id": str(ctx.workspace.id)}
    )
    assert response.status_code == 401

    # Wrong workspace (foreign workspace)
    foreign_ws = uuid4()
    response = client.get(
        "/evaluations",
        params={"workspace_id": str(foreign_ws)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 403


def test_put_creates_and_updates_reviewers_own_evaluation(postgres_client):
    client, factory = postgres_client
    ctx = _seed_evaluation_context(factory)
    token = _token(client, ctx.reviewer.email)

    created = client.put(
        "/evaluations",
        json=_payload(ctx, reviewer_id=str(ctx.reviewer.id)),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert created.status_code == 200
    assert created.json()["relevance_label"] == 2

    # Updating the same pair again should not duplicate; carry the
    # previously returned updated_at for optimistic concurrency.
    previous_updated_at = created.json()["updated_at"]
    updated = client.put(
        "/evaluations",
        json=_payload(
            ctx,
            reviewer_id=str(ctx.reviewer.id),
            relevance_label=1,
            expected_updated_at=previous_updated_at,
        ),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert updated.status_code == 200

    # Verify only one label exists for this pair
    with factory.begin() as session:
        count = session.scalar(
            select(func.count(EvaluationLabel.id)).where(
                EvaluationLabel.job_candidate_id == ctx.pair.id
            )
        )
        assert count == 1
