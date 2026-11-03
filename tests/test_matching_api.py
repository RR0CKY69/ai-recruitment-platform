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


@pytest.fixture
def matching_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "matching-api-test-secret-key-at-least-32-bytes")
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-matching-api")
    monkeypatch.setenv("JWT_AUDIENCE", "test-matching-clients")
    monkeypatch.setattr("ml_project.config.load_dotenv", lambda *_args, **_kwargs: None)
    engine = create_engine("sqlite+pysqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override_session():
        with factory() as session:
            yield session

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_api_session] = override_session
    try:
        with TestClient(app) as client:
            yield client, factory
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)
        engine.dispose()


def _seed(factory):
    with factory.begin() as session:
        user = User(email="m@example.test", password_hash=hash_password(TEST_PASSWORD), full_name="M", is_active=True)
        ws = Workspace(name="WS", slug="ws")
        session.add_all([user, ws])
        session.flush()
        session.add(WorkspaceMember(user_id=user.id, workspace_id=ws.id, role="ADMIN"))
        session.flush()
        job = Job(workspace_id=ws.id, created_by_id=user.id, title="Python Dev", description="python django", location="Remote", minimum_experience_years=2, status="OPEN")
        session.add(job)
        session.flush()
        session.add(JobRequirement(job_id=job.id, requirement_type="REQUIRED_SKILL", description="python", normalized_value="python"))
        c1 = Candidate(workspace_id=ws.id, created_by_id=user.id, full_name="Alice", current_title="Dev", summary="python django", experience_years=3, location="Remote")
        c2 = Candidate(workspace_id=ws.id, created_by_id=user.id, full_name="Bob", current_title="QA", summary="java", experience_years=1, location="NYC")
        session.add_all([c1, c2])
        session.flush()
        session.add(CandidateSkill(candidate_id=c1.id, name="python", normalized_name="python"))
        session.add(CandidateSkill(candidate_id=c2.id, name="java", normalized_name="java"))
        return user.email, ws.id, job.id


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    return r.json()["access_token"]


def test_run_matching(matching_client):
    client, factory = matching_client
    email, ws_id, job_id = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 2
    assert data[0]["tfidf_similarity"] is not None
    assert data[0]["semantic_similarity"] is None
    assert data[0]["hybrid_score"] is None


def test_get_matching(matching_client):
    client, factory = matching_client
    email, ws_id, job_id = _seed(factory)
    token = _login(client, email)
    client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    r = client.get(f"/matching?workspace_id={ws_id}&job_id={job_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_invalid_job(matching_client):
    client, factory = matching_client
    email, ws_id, _job_id = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(uuid4())}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_unauthorized(matching_client):
    client, factory = matching_client
    _email, ws_id, job_id = _seed(factory)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)})
    assert r.status_code in (401, 403)


def test_score_distribution_empty_and_workspace_authorized(matching_client):
    client, factory = matching_client
    email, ws_id, _job_id = _seed(factory)
    token = _login(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.get(f"/matching/score-distribution?workspace_id={ws_id}", headers=headers)

    assert response.status_code == 200
    data = response.json()
    assert data["experimental_combined_score"]["total_scored_matches"] == 0
    assert data["tfidf_similarity"]["total_scored_matches"] == 0
    assert [bucket["count"] for bucket in data["experimental_combined_score"]["buckets"]] == [0] * 5

    forbidden = client.get(f"/matching/score-distribution?workspace_id={uuid4()}", headers=headers)
    assert forbidden.status_code == 403


def test_score_distribution_aggregates_real_scores_and_isolates_workspaces(matching_client):
    client, factory = matching_client
    email, ws_id, job_id = _seed(factory)
    token = _login(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    target_scores = [
        (0.0, 0.0),
        (20.0, 0.2),
        (20.01, 0.2001),
        (40.0, 0.4),
        (40.01, 0.4001),
        (60.0, 0.6),
        (60.01, 0.6001),
        (80.0, 0.8),
        (80.01, 0.8001),
        (100.0, 1.0),
        (None, 0.5),
        (50.0, None),
        (None, None),
        (-1.0, 1.1),
        (101.0, -0.1),
    ]
    with factory.begin() as session:
        for index, (hybrid_score, tfidf_similarity) in enumerate(target_scores):
            candidate = Candidate(
                workspace_id=ws_id,
                full_name=f"Target Candidate {index}",
                summary="",
            )
            session.add(candidate)
            session.flush()
            association = JobCandidate(
                workspace_id=ws_id,
                job_id=job_id,
                candidate_id=candidate.id,
            )
            session.add(association)
            session.flush()
            session.add(
                MatchResult(
                    job_candidate_id=association.id,
                    model_name="test-model",
                    model_version=str(index),
                    hybrid_score=hybrid_score,
                    tfidf_similarity=tfidf_similarity,
                )
            )

        other_workspace = Workspace(name="Other", slug=f"other-{uuid4().hex}")
        session.add(other_workspace)
        session.flush()
        other_job = Job(
            workspace_id=other_workspace.id,
            title="Other workspace job",
            description="",
        )
        other_candidate = Candidate(
            workspace_id=other_workspace.id,
            full_name="Other Workspace Candidate",
            summary="",
        )
        session.add_all([other_job, other_candidate])
        session.flush()
        other_association = JobCandidate(
            workspace_id=other_workspace.id,
            job_id=other_job.id,
            candidate_id=other_candidate.id,
        )
        session.add(other_association)
        session.flush()
        session.add(
            MatchResult(
                job_candidate_id=other_association.id,
                model_name="other-model",
                model_version="1",
                hybrid_score=100.0,
                tfidf_similarity=1.0,
            )
        )

    response = client.get(f"/matching/score-distribution?workspace_id={ws_id}", headers=headers)
    assert response.status_code == 200
    data = response.json()
    combined = data["experimental_combined_score"]
    tfidf = data["tfidf_similarity"]
    assert combined["score_scale"] == "0–100 experimental combined score"
    assert combined["total_scored_matches"] == 11
    assert [bucket["range"] for bucket in combined["buckets"]] == ["0–20", ">20–40", ">40–60", ">60–80", ">80–100"]
    assert [bucket["count"] for bucket in combined["buckets"]] == [2, 2, 3, 2, 2]
    assert tfidf["score_scale"] == "0–100 scale (cosine similarity × 100)"
    assert tfidf["total_scored_matches"] == 11
    assert [bucket["count"] for bucket in tfidf["buckets"]] == [2, 2, 3, 2, 2]