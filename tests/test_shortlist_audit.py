from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.models import (
    AuditLog,
    Candidate,
    Job,
    JobCandidate,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "audit-test-password"


@pytest.fixture
def audit_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-audit")
    monkeypatch.setenv("JWT_AUDIENCE", "test-audit-clients")
    monkeypatch.setattr("ml_project.config.load_dotenv", lambda *_args, **_kwargs: None)
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    from ml_project.models import Base

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
        user = User(email="recruiter@example.test", password_hash=hash_password(TEST_PASSWORD), full_name="Recruiter", is_active=True)
        workspace = Workspace(name="Workspace", slug="workspace")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="RECRUITER"))
        job = Job(workspace_id=workspace.id, title="Job", description="Desc", status="OPEN")
        candidate = Candidate(workspace_id=workspace.id, full_name="Candidate", summary="Summary")
        session.add_all([job, candidate])
        session.flush()
        session.add(
            JobCandidate(
                workspace_id=workspace.id,
                job_id=job.id,
                candidate_id=candidate.id,
            )
        )
        return user.email, workspace.id, job.id, candidate.id


def _token(client, email):
    response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_audit_add_and_remove(audit_client):
    client, factory = audit_client
    email, workspace_id, job_id, candidate_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    add = client.post(
        "/shortlists",
        json={"workspace_id": str(workspace_id), "job_id": str(job_id), "candidate_id": str(candidate_id)},
        headers=headers,
    )
    assert add.status_code == 201
    shortlist_id = add.json()["shortlist_id"]

    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 1
        event = events[0]
        assert event.action == "shortlist.added"
        assert event.entity_type == "shortlist"
        assert str(event.entity_id) == shortlist_id
        assert event.details == {"job_id": str(job_id), "candidate_id": str(candidate_id)}

    delete = client.delete(f"/shortlists/{shortlist_id}", params={"workspace_id": str(workspace_id)}, headers=headers)
    assert delete.status_code == 204

    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 2
        assert events[-1].action == "shortlist.removed"


def test_audit_duplicate_add_no_extra(audit_client):
    client, factory = audit_client
    email, workspace_id, job_id, candidate_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"workspace_id": str(workspace_id), "job_id": str(job_id), "candidate_id": str(candidate_id)}
    first = client.post("/shortlists", json=payload, headers=headers)
    assert first.status_code == 201
    second = client.post("/shortlists", json=payload, headers=headers)
    assert second.status_code == 200

    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 1


def test_audit_failed_no_record(audit_client):
    client, factory = audit_client
    email, workspace_id, _job_id, candidate_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.post(
        "/shortlists",
        json={"workspace_id": str(workspace_id), "job_id": str(uuid4()), "candidate_id": str(candidate_id)},
        headers=headers,
    )
    assert response.status_code == 404
    with factory() as session:
        assert session.query(AuditLog).count() == 0
def test_shortlist_audit_fields_and_cross_workspace(audit_client, monkeypatch):
    client, factory = audit_client
    email, workspace_id, job_id, candidate_id = _seed(factory)
    # create second workspace/member not accessible
    with factory.begin() as session:
        from ml_project.models import Candidate, Job, Workspace
        other = Workspace(name="Other", slug="other")
        session.add(other)
        session.flush()
        job2 = Job(workspace_id=other.id, title="Job2", description="Desc", status="OPEN")
        cand2 = Candidate(workspace_id=other.id, full_name="Candidate2", summary="Summary")
        session.add_all([job2, cand2])
        session.flush()
        other_ids = (other.id, job2.id, cand2.id)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"workspace_id": str(workspace_id), "job_id": str(job_id), "candidate_id": str(candidate_id)}
    response = client.post("/shortlists", json=payload, headers=headers)
    assert response.status_code == 201
    shortlist_id = response.json()["shortlist_id"]

    from ml_project.models import AuditLog
    with factory() as session:
        event = session.query(AuditLog).one()
        assert str(event.actor_id)  # authenticated user exists
        assert str(event.workspace_id) == str(workspace_id)
        assert event.action == "shortlist.added"
        assert event.entity_type == "shortlist"
        assert str(event.entity_id) == shortlist_id
        assert set(event.details) == {"job_id", "candidate_id"}
        assert "password" not in str(event.details).lower()

    # cross-workspace cannot create audit in other workspace
    other_workspace_id, other_job_id, other_candidate_id = other_ids
    cross = client.post(
        "/shortlists",
        json={"workspace_id": str(other_workspace_id), "job_id": str(other_job_id), "candidate_id": str(other_candidate_id)},
        headers=headers,
    )
    assert cross.status_code == 403
    with factory() as session:
        assert session.query(AuditLog).count() == 1


def test_shortlist_audit_insertion_failure_rolls_back(audit_client, monkeypatch):
    client, factory = audit_client
    email, workspace_id, job_id, candidate_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("ml_project.api.routers.shortlists.record_audit_event", boom)
    payload = {"workspace_id": str(workspace_id), "job_id": str(job_id), "candidate_id": str(candidate_id)}
    with pytest.raises(RuntimeError):
        client.post("/shortlists", json=payload, headers=headers)
    with factory() as session:
        from ml_project.models import AuditLog, Shortlist
        assert session.query(Shortlist).count() == 0
        assert session.query(AuditLog).count() == 0
