"""PostgreSQL integration tests for matching.

These tests exercise the same business rules as tests/test_matching_api.py
but run against a dedicated PostgreSQL test database via the postgres_client
fixture. No SQLite-specific constructs are used.
"""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ml_project.models import (
    Candidate,
    CandidateSkill,
    Job,
    JobCandidate,
    JobRequirement,
    MatchResult,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "Matching API test password"


def _seed(factory: sessionmaker):
    """Seed user, workspace, job, 4 candidates with assignments."""
    with factory.begin() as session:
        user = User(
            email="m@example.test",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="Matcher",
            is_active=True,
        )
        ws = Workspace(name="WS", slug="ws")
        session.add_all([user, ws])
        session.flush()
        session.add(WorkspaceMember(user_id=user.id, workspace_id=ws.id, role="ADMIN"))
        session.flush()
        job = Job(
            workspace_id=ws.id,
            created_by_id=user.id,
            title="Python Dev",
            description="python django",
            location="Remote",
            minimum_experience_years=2,
            status="OPEN",
        )
        session.add(job)
        session.flush()
        session.add(
            JobRequirement(
                job_id=job.id,
                requirement_type="REQUIRED_SKILL",
                description="python",
                normalized_value="python",
            )
        )
        c1 = Candidate(
            workspace_id=ws.id,
            created_by_id=user.id,
            full_name="Alice",
            current_title="Dev",
            summary="python django",
            experience_years=3,
            location="Remote",
        )
        c2 = Candidate(
            workspace_id=ws.id,
            created_by_id=user.id,
            full_name="Bob",
            current_title="QA",
            summary="java",
            experience_years=1,
            location="NYC",
        )
        c3 = Candidate(
            workspace_id=ws.id,
            created_by_id=user.id,
            full_name="Carol",
            current_title="PM",
            summary="agile",
            experience_years=5,
            location="Remote",
        )
        c4 = Candidate(
            workspace_id=ws.id,
            created_by_id=user.id,
            full_name="Dan",
            current_title="Ops",
            summary="linux",
            experience_years=4,
            location="Remote",
        )
        session.add_all([c1, c2, c3, c4])
        session.flush()
        session.add(CandidateSkill(candidate_id=c1.id, name="python", normalized_name="python"))
        session.add(CandidateSkill(candidate_id=c2.id, name="java", normalized_name="java"))
        # c1 and c2 are explicitly assigned to job; c3 is unassigned; c4 is assigned only to job2.
        session.add(JobCandidate(workspace_id=ws.id, job_id=job.id, candidate_id=c1.id))
        session.add(JobCandidate(workspace_id=ws.id, job_id=job.id, candidate_id=c2.id))
        job2 = Job(
            workspace_id=ws.id,
            created_by_id=user.id,
            title="Java Dev",
            description="java spring",
            location="NYC",
            minimum_experience_years=1,
            status="OPEN",
        )
        session.add(job2)
        session.flush()
        session.add(JobCandidate(workspace_id=ws.id, job_id=job2.id, candidate_id=c2.id))
        session.add(JobCandidate(workspace_id=ws.id, job_id=job2.id, candidate_id=c4.id))
        return user.email, ws.id, job.id, c1.id, c2.id, c3.id, c4.id, job2.id


def _login(client, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    return r.json()["access_token"]


def test_run_matching_matches_only_assigned_candidates(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, c1_id, c2_id, c3_id, c4_id, _job2_id = _seed(factory)
    token = _login(client, email)
    r = client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    returned_ids = {row["candidate_id"] for row in data}
    assert returned_ids == {str(c1_id), str(c2_id)}
    assert str(c3_id) not in returned_ids
    assert str(c4_id) not in returned_ids
    for row in data:
        assert row["tfidf_similarity"] is not None
        assert row["semantic_similarity"] is None
        assert row["hybrid_score"] is not None


def test_unassigned_workspace_candidate_excluded(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, _c1, _c2, c3_id, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    r = client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert str(c3_id) not in {row["candidate_id"] for row in r.json()}


def test_candidate_assigned_only_to_another_job_excluded(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, _c1, _c2, _c3, c4_id, _job2_id = _seed(factory)
    token = _login(client, email)
    r = client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert str(c4_id) not in {row["candidate_id"] for row in r.json()}


def test_run_matching_does_not_create_or_duplicate_associations(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    with factory() as session:
        before = session.scalars(
            select(JobCandidate).where(
                JobCandidate.workspace_id == ws_id,
                JobCandidate.job_id == job_id,
            )
        ).all()
        before_count = len(before)

    client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    with factory() as session:
        after = session.scalars(
            select(JobCandidate).where(
                JobCandidate.workspace_id == ws_id,
                JobCandidate.job_id == job_id,
            )
        ).all()
        assert len(after) == before_count
        results = session.execute(
            select(MatchResult)
            .join(JobCandidate, MatchResult.job_candidate_id == JobCandidate.id)
            .where(
                MatchResult.model_name == "tfidf-cosine",
                MatchResult.model_version == "1.0",
                JobCandidate.workspace_id == ws_id,
                JobCandidate.job_id == job_id,
            )
        ).scalars().all()
        assert len(results) == before_count


def test_match_result_references_correct_job_candidate(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, c1_id, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )

    with factory() as session:
        result = session.scalar(
            select(MatchResult).join(JobCandidate).where(
                MatchResult.model_name == "tfidf-cosine",
                MatchResult.model_version == "1.0",
                JobCandidate.candidate_id == c1_id,
            )
        )
        assert result is not None
        assert result.job_candidate_id is not None


def test_empty_assigned_candidates_safe(postgres_client):
    client, factory = postgres_client
    email, _ws_id, _job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)

    with factory.begin() as session:
        user = session.scalar(select(User).where(User.email == email))
        empty_job = Job(
            workspace_id=_ws_id,
            created_by_id=user.id,
            title="Empty Job",
            description="No candidates assigned",
            location="Remote",
            minimum_experience_years=0,
            status="DRAFT",
        )
        session.add(empty_job)
        session.flush()
        empty_job_id = empty_job.id

    r = client.post(
        "/matching/run",
        json={"workspace_id": str(_ws_id), "job_id": str(empty_job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert r.json() == []


def test_cross_workspace_access_rejected(postgres_client):
    client, factory = postgres_client
    _email, _ws_id, _job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, _email)

    # Try to run matching against a job in a different workspace (not seeded)
    foreign_job_id = uuid4()
    r = client.post(
        "/matching/run",
        json={"workspace_id": str(uuid4()), "job_id": str(foreign_job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code in (401, 403, 404)


def test_invalid_job(postgres_client):
    client, factory = postgres_client
    email, ws_id, _job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)

    r = client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(uuid4())},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 404


def test_unauthorized(postgres_client):
    client, factory = postgres_client
    _email, ws_id, job_id, *_rest = _seed(factory)
    r = client.post(
        "/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}
    )
    assert r.status_code in (401, 403)


def test_get_matching(postgres_client):
    client, factory = postgres_client
    email, ws_id, job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    client.post(
        "/matching/run",
        json={"workspace_id": str(ws_id), "job_id": str(job_id)},
        headers={"Authorization": f"Bearer {token}"},
    )
    r = client.get(
        f"/matching?workspace_id={ws_id}&job_id={job_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    assert len(r.json()) == 2
