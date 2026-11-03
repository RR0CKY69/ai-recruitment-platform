from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.models import (
    Base,
    Candidate,
    CandidateSkill,
    CandidateSource,
    Job,
    JobCandidate,
    JobRequirement,
    MatchResult,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "Read-only API test password"


@pytest.fixture
def workspace_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "jobs-candidates-test-secret-key-at-least-32-bytes")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-jobs-candidates-api")
    monkeypatch.setenv("JWT_AUDIENCE", "test-jobs-candidates-clients")
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


def _seed_records(factory, *, include_records=True):
    with factory.begin() as session:
        user = User(
            email="api-reader@example.test",
            password_hash=hash_password(TEST_PASSWORD),
            full_name="API Reader",
            is_active=True,
        )
        workspace_a = Workspace(name="Workspace A", slug="workspace-a")
        workspace_b = Workspace(name="Workspace B", slug="workspace-b")
        unassigned_workspace = Workspace(name="Unassigned", slug="unassigned")
        session.add_all([user, workspace_a, workspace_b, unassigned_workspace])
        session.flush()
        session.add_all(
            [
                WorkspaceMember(user_id=user.id, workspace_id=workspace_a.id, role="ADMIN"),
                WorkspaceMember(user_id=user.id, workspace_id=workspace_b.id, role="RECRUITER"),
            ]
        )
        session.flush()

        ids = {
            "email": user.email,
            "workspace_a": workspace_a.id,
            "workspace_b": workspace_b.id,
            "unassigned_workspace": unassigned_workspace.id,
        }
        if include_records:
            job_a = Job(
                workspace_id=workspace_a.id,
                legacy_job_id="J001",
                title="Backend Engineer",
                description="Build backend systems.",
                minimum_experience_years=3,
                location="Remote",
                employment_type="Full-time",
                status="OPEN",
            )
            job_b = Job(
                workspace_id=workspace_b.id,
                legacy_job_id="J001",
                title="Data Engineer",
                description="Build data systems.",
                status="DRAFT",
            )
            candidate_a = Candidate(
                workspace_id=workspace_a.id,
                legacy_candidate_id="C001",
                full_name="Candidate A",
                email="private-a@example.test",
                current_title="Backend Developer",
                summary="Builds reliable services.",
                experience_years=5,
                location="Remote",
            )
            candidate_b = Candidate(
                workspace_id=workspace_b.id,
                legacy_candidate_id="C001",
                full_name="Candidate B",
                email="private-b@example.test",
                current_title="Data Developer",
                summary="Builds data platforms.",
            )
            session.add_all([job_a, job_b, candidate_a, candidate_b])
            session.flush()
            session.add_all(
                [
                    JobRequirement(
                        job_id=job_a.id,
                        requirement_type="REQUIRED_SKILL",
                        description="Python",
                        normalized_value="python",
                    ),
                    JobRequirement(
                        job_id=job_a.id,
                        requirement_type="PREFERRED_SKILL",
                        description="Docker",
                        normalized_value="docker",
                    ),
                    CandidateSkill(
                        candidate_id=candidate_a.id,
                        name="Python",
                        normalized_name="python",
                        years_experience=4,
                    ),
                    CandidateSkill(
                        candidate_id=candidate_a.id,
                        name="PostgreSQL",
                        normalized_name="postgresql",
                    ),
                    CandidateSource(
                        candidate_id=candidate_a.id,
                        provider="csv_migration",
                        source_record_id="C001",
                        source_url="https://example.test/profile",
                        authorized_basis="Candidate provided profile",
                        source_metadata={"internal": "must not be returned"},
                    ),
                ]
            )
            session.flush()
            ids.update(
                {
                    "job_a": job_a.id,
                    "job_b": job_b.id,
                    "candidate_a": candidate_a.id,
                    "candidate_b": candidate_b.id,
                }
            )
        return ids


def _token(client, email):
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def test_member_retrieves_workspace_jobs_with_legacy_and_uuid_ids(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    response = client.get(
        "/jobs",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "id": str(records["job_a"]),
            "workspace_id": str(records["workspace_a"]),
            "legacy_job_id": "J001",
            "title": "Backend Engineer",
            "description": "Build backend systems.",
            "required_skills": ["Python"],
            "minimum_experience_years": 3,
            "location": "Remote",
            "employment_type": "Full-time",
            "status": "OPEN",
            "candidate_count": 0,
        }
    ]
    assert "created_by_id" not in response.text


def test_job_candidate_count_uses_workspace_associations(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    with factory.begin() as session:
        session.add(
            JobCandidate(
                workspace_id=records["workspace_a"],
                job_id=records["job_a"],
                candidate_id=records["candidate_a"],
            )
        )
    token = _token(client, records["email"])

    response = client.get(
        "/jobs",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()[0]["candidate_count"] == 1


def test_member_retrieves_workspace_candidates_skills_and_sources(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    response = client.get(
        "/candidates",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    candidate = response.json()[0]
    assert candidate["id"] == str(records["candidate_a"])
    assert candidate["workspace_id"] == str(records["workspace_a"])
    assert candidate["legacy_candidate_id"] == "C001"
    skills_by_name = {skill["name"]: skill for skill in candidate["skills"]}
    assert set(skills_by_name) == {"Python", "PostgreSQL"}
    assert skills_by_name["Python"]["years_experience"] == 4
    assert candidate["sources"] == [
        {
            "provider": "csv_migration",
            "source_record_id": "C001",
            "source_url": "https://example.test/profile",
            "authorized_basis": "Candidate provided profile",
        }
    ]
    assert "source_metadata" not in response.text
    assert "password_hash" not in response.text
    assert "private-a@example.test" not in response.text


def test_candidate_detail_returns_workspace_associations_and_stored_matches(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    with factory.begin() as session:
        association = JobCandidate(
            workspace_id=records["workspace_a"],
            job_id=records["job_a"],
            candidate_id=records["candidate_a"],
        )
        session.add(association)
        session.flush()
        session.add(
            MatchResult(
                job_candidate_id=association.id,
                model_name="tfidf-cosine",
                model_version="1.0",
                tfidf_similarity=0.75,
                skill_coverage=0.5,
                experience_compatibility="Meets minimum",
                location_compatibility="Exact match",
                hybrid_score=68.0,
                explanation={},
            )
        )
    token = _token(client, records["email"])

    response = client.get(
        f"/candidates/{records['candidate_a']}",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["full_name"] == "Candidate A"
    assert body["skills"][0]["name"] == "PostgreSQL"
    assert body["associated_jobs"] == [
        {
            "job_id": str(records["job_a"]),
            "title": "Backend Engineer",
            "status": "OPEN",
            "stage": "SOURCED",
            "matching_results": [
                {
                    "model_name": "tfidf-cosine",
                    "model_version": "1.0",
                    "tfidf_similarity": 0.75,
                    "skill_coverage": 0.5,
                    "experience_compatibility": "Meets minimum",
                    "location_compatibility": "Exact match",
                    "hybrid_score": 68.0,
                    "updated_at": body["associated_jobs"][0]["matching_results"][0]["updated_at"],
                }
            ],
        }
    ]
    assert "private-a@example.test" not in response.text
    assert "source_metadata" not in response.text


def test_candidate_detail_is_workspace_scoped(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    token = _token(client, records["email"])
    headers = {"Authorization": f"Bearer {token}"}

    unassigned = client.get(
        f"/candidates/{records['candidate_a']}",
        params={"workspace_id": str(records["unassigned_workspace"])},
        headers=headers,
    )
    foreign = client.get(
        f"/candidates/{records['candidate_a']}",
        params={"workspace_id": str(records["workspace_b"])},
        headers=headers,
    )

    assert unassigned.status_code == 403
    assert foreign.status_code == 404


def test_results_are_scoped_to_requested_workspace(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    token = _token(client, records["email"])
    headers = {"Authorization": f"Bearer {token}"}

    jobs = client.get("/jobs", params={"workspace_id": str(records["workspace_b"])}, headers=headers)
    candidates = client.get(
        "/candidates", params={"workspace_id": str(records["workspace_b"])}, headers=headers
    )

    assert jobs.status_code == candidates.status_code == 200
    assert [row["id"] for row in jobs.json()] == [str(records["job_b"])]
    assert [row["id"] for row in candidates.json()] == [str(records["candidate_b"])]
    assert all(row["workspace_id"] == str(records["workspace_b"]) for row in jobs.json())
    assert all(row["workspace_id"] == str(records["workspace_b"]) for row in candidates.json())


def test_nonmember_cannot_read_jobs_or_candidates(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory)
    token = _token(client, records["email"])
    headers = {"Authorization": f"Bearer {token}"}

    for path in ("/jobs", "/candidates"):
        response = client.get(
            path,
            params={"workspace_id": str(records["unassigned_workspace"])},
            headers=headers,
        )
        assert response.status_code == 403
        assert response.json() == {"detail": "Workspace membership is required for this operation."}


def test_unauthenticated_jobs_and_candidates_requests_are_rejected(workspace_client):
    client, _factory = workspace_client
    workspace_id = uuid4()

    for path in ("/jobs", "/candidates"):
        response = client.get(path, params={"workspace_id": str(workspace_id)})
        assert response.status_code == 401


def test_empty_member_workspace_returns_empty_lists(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory, include_records=False)
    token = _token(client, records["email"])
    headers = {"Authorization": f"Bearer {token}"}

    jobs = client.get(
        "/jobs", params={"workspace_id": str(records["workspace_a"])}, headers=headers
    )
    candidates = client.get(
        "/candidates", params={"workspace_id": str(records["workspace_a"])}, headers=headers
    )

    assert jobs.status_code == candidates.status_code == 200
    assert jobs.json() == []
    assert candidates.json() == []


def test_unassigned_workspace_response_is_forbidden_even_when_empty(workspace_client):
    client, factory = workspace_client
    records = _seed_records(factory, include_records=False)
    token = _token(client, records["email"])

    response = client.get(
        "/jobs",
        params={"workspace_id": str(records["unassigned_workspace"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403
