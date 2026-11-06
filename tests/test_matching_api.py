from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
        c3 = Candidate(workspace_id=ws.id, created_by_id=user.id, full_name="Carol", current_title="PM", summary="agile", experience_years=5, location="Remote")
        c4 = Candidate(workspace_id=ws.id, created_by_id=user.id, full_name="Dan", current_title="Ops", summary="linux", experience_years=4, location="Remote")
        session.add_all([c1, c2, c3, c4])
        session.flush()
        session.add(CandidateSkill(candidate_id=c1.id, name="python", normalized_name="python"))
        session.add(CandidateSkill(candidate_id=c2.id, name="java", normalized_name="java"))
        # c1 and c2 are explicitly assigned to job; c3 is unassigned; c4 is assigned only to job2.
        session.add(JobCandidate(workspace_id=ws.id, job_id=job.id, candidate_id=c1.id))
        session.add(JobCandidate(workspace_id=ws.id, job_id=job.id, candidate_id=c2.id))
        job2 = Job(workspace_id=ws.id, created_by_id=user.id, title="Java Dev", description="java spring", location="NYC", minimum_experience_years=1, status="OPEN")
        session.add(job2)
        session.flush()
        session.add(JobCandidate(workspace_id=ws.id, job_id=job2.id, candidate_id=c2.id))
        session.add(JobCandidate(workspace_id=ws.id, job_id=job2.id, candidate_id=c4.id))
        return user.email, ws.id, job.id, c1.id, c2.id, c3.id, c4.id, job2.id


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    return r.json()["access_token"]


def _job_ids(session, ws_id, job_id):
    assocs = session.scalars(
        select(JobCandidate).where(
            JobCandidate.workspace_id == ws_id,
            JobCandidate.job_id == job_id,
        )
    ).all()
    return assocs


def test_run_matching_matches_only_assigned_candidates(matching_client):
    client, factory = matching_client
    email, ws_id, job_id, c1_id, c2_id, c3_id, c4_id, _job2_id = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
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


def test_unassigned_workspace_candidate_excluded(matching_client):
    client, factory = matching_client
    email, ws_id, job_id, _c1, _c2, c3_id, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert str(c3_id) not in {row["candidate_id"] for row in r.json()}


def test_candidate_assigned_only_to_another_job_excluded(matching_client):
    client, factory = matching_client
    email, ws_id, job_id, _c1, _c2, _c3, c4_id, _job2_id = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert str(c4_id) not in {row["candidate_id"] for row in r.json()}


def test_run_matching_does_not_create_or_duplicate_associations(matching_client):
    client, factory = matching_client
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

    client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})

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


def test_match_result_references_correct_job_candidate(matching_client):
    client, factory = matching_client
    email, ws_id, job_id, c1_id, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    with factory() as session:
        assoc = session.scalar(
            select(JobCandidate).where(
                JobCandidate.workspace_id == ws_id,
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == c1_id,
            )
        )
        assert assoc is not None
        mr = session.scalar(
            select(MatchResult).where(MatchResult.job_candidate_id == assoc.id)
        )
        assert mr is not None
        assert mr.job_candidate_id == assoc.id
        assert assoc.job_id == job_id
        assert assoc.candidate_id == c1_id


def test_empty_assigned_candidates_safe(matching_client):
    client, factory = matching_client
    email, ws_id, _job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    with factory.begin() as session:
        user = session.scalar(select(User).where(User.email == email))
        ws = session.scalar(select(Workspace).where(Workspace.id == ws_id))
        empty_job = Job(workspace_id=ws.id, created_by_id=user.id, title="Empty Job", description="", location="Remote", minimum_experience_years=1, status="OPEN")
        session.add(empty_job)
        session.flush()
        empty_job_id = empty_job.id

    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(empty_job_id)}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json() == []

    with factory() as session:
        assocs = session.scalars(
            select(JobCandidate).where(JobCandidate.job_id == empty_job_id)
        ).all()
        assert assocs == []


def test_cross_workspace_access_rejected(matching_client):
    client, factory = matching_client
    _email, ws_id, job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    with factory.begin() as session:
        other_user = User(email="other@example.test", password_hash=hash_password(TEST_PASSWORD), full_name="O", is_active=True)
        other_ws = Workspace(name="Other", slug="other-ws")
        session.add_all([other_user, other_ws])
        session.flush()
        session.add(WorkspaceMember(user_id=other_user.id, workspace_id=other_ws.id, role="ADMIN"))
        session.flush()
    other_token = _login(client, other_user.email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {other_token}"})
    assert r.status_code == 403


def test_invalid_job(matching_client):
    client, factory = matching_client
    email, ws_id, _job_id, *_rest = _seed(factory)
    token = _login(client, email)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(uuid4())}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 404


def test_unauthorized(matching_client):
    client, factory = matching_client
    _email, ws_id, job_id, *_rest = _seed(factory)
    r = client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)})
    assert r.status_code in (401, 403)


def test_get_matching(matching_client):
    client, factory = matching_client
    email, ws_id, job_id, _c1, _c2, _c3, _c4, _job2 = _seed(factory)
    token = _login(client, email)
    client.post("/matching/run", json={"workspace_id": str(ws_id), "job_id": str(job_id)}, headers={"Authorization": f"Bearer {token}"})
    r = client.get(f"/matching?workspace_id={ws_id}&job_id={job_id}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_score_distribution_empty_and_workspace_authorized(matching_client):
    client, factory = matching_client
    email, ws_id, _job_id, *_rest = _seed(factory)
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
    email, ws_id, job_id, *_rest = _seed(factory)
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
