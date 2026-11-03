
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session
from ml_project.api.main import app
from ml_project.models import (
    Candidate,
    Job,
    JobCandidate,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "evaluation-audit-password"


@pytest.fixture
def eval_audit_client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET_KEY", "a" * 32)
    monkeypatch.setenv("JWT_ACCESS_TOKEN_MINUTES", "15")
    monkeypatch.setenv("JWT_ISSUER", "test-eval-audit")
    monkeypatch.setenv("JWT_AUDIENCE", "test-eval-audit-clients")
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
        user = User(email="reviewer@example.test", password_hash=hash_password(TEST_PASSWORD), full_name="Reviewer", is_active=True)
        workspace = Workspace(name="Workspace", slug="workspace")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="RECRUITER"))
        job = Job(workspace_id=workspace.id, title="Job", description="Desc", status="OPEN")
        candidate = Candidate(workspace_id=workspace.id, full_name="Candidate", summary="Summary")
        session.add_all([job, candidate])
        session.flush()
        association = JobCandidate(workspace_id=workspace.id, job_id=job.id, candidate_id=candidate.id)
        session.add(association)
        session.flush()
        return user.email, workspace.id, job.id, candidate.id, association.id


def _token(client, email):
    response = client.post("/auth/login", json={"email": email, "password": TEST_PASSWORD})
    assert response.status_code == 200
    return response.json()["access_token"]


def test_eval_audit_label_create_and_update(eval_audit_client):
    client, factory = eval_audit_client
    email, workspace_id, job_id, candidate_id, _association_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    create = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": None,
            "relevance_label": 2,
            "review_status": "reviewed",
        },
        headers=headers,
    )
    assert create.status_code == 200

    from ml_project.models import AuditLog

    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 1
        assert events[0].action == "evaluation.label_created"
        assert events[0].entity_type == "evaluation_label"

    update = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": create.json()["updated_at"],
            "relevance_label": 1,
            "review_status": "reviewed",
        },
        headers=headers,
    )
    assert update.status_code == 200

    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 2
        assert events[-1].action == "evaluation.label_updated"


def test_eval_audit_note_create_and_update(eval_audit_client):
    client, factory = eval_audit_client
    email, workspace_id, job_id, candidate_id, _association_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    label = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": None,
            "relevance_label": 2,
            "review_status": "reviewed",
            "note": "first note",
        },
        headers=headers,
    )
    assert label.status_code == 200
    note_id = label.json()["notes"][0]["note_id"]

    from ml_project.models import AuditLog

    with factory() as session:
        actions = [e.action for e in session.query(AuditLog).all()]
        assert "evaluation.label_created" in actions
        assert "evaluation.note_created" in actions

    updated = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": label.json()["updated_at"],
            "relevance_label": 2,
            "review_status": "reviewed",
            "note": "updated note",
            "note_id": note_id,
        },
        headers=headers,
    )
    assert updated.status_code == 200

    with factory() as session:
        actions = [e.action for e in session.query(AuditLog).all()]
        assert actions.count("evaluation.note_updated") == 1


def test_eval_audit_stale_no_record(eval_audit_client):
    client, factory = eval_audit_client
    email, workspace_id, job_id, candidate_id, _association_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    first = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": None,
            "relevance_label": 2,
            "review_status": "reviewed",
        },
        headers=headers,
    )
    assert first.status_code == 200

    stale = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": "2020-01-01T00:00:00Z",
            "relevance_label": 1,
            "review_status": "reviewed",
        },
        headers=headers,
    )
    assert stale.status_code == 409

    from ml_project.models import AuditLog

    with factory() as session:
        # creation audit only, no update audit
        assert session.query(AuditLog).count() == 1
def test_eval_audit_fields_and_sensitive_data(eval_audit_client):
    client, factory = eval_audit_client
    email, workspace_id, job_id, candidate_id, _association_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.put(
        "/evaluations",
        json={
            "workspace_id": str(workspace_id),
            "job_id": str(job_id),
            "candidate_id": str(candidate_id),
            "expected_updated_at": None,
            "relevance_label": 2,
            "review_status": "reviewed",
            "note": "secret note text",
        },
        headers=headers,
    )
    assert response.status_code == 200
    from ml_project.models import AuditLog
    with factory() as session:
        events = session.query(AuditLog).all()
        assert len(events) == 2
        for event in events:
            assert str(event.workspace_id) == str(workspace_id)
            assert event.actor_id is not None
            assert event.details is not None
            assert "secret note text" not in str(event.details)
            assert "password" not in str(event.details).lower()


def test_eval_audit_insertion_failure_rolls_back(eval_audit_client, monkeypatch):
    client, factory = eval_audit_client
    email, workspace_id, job_id, candidate_id, _association_id = _seed(factory)
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}

    def boom(*_args, **_kwargs):
        raise RuntimeError("audit failed")

    monkeypatch.setattr("ml_project.api.routers.evaluations.record_audit_event", boom)
    with pytest.raises(RuntimeError):
        client.put(
            "/evaluations",
            json={
                "workspace_id": str(workspace_id),
                "job_id": str(job_id),
                "candidate_id": str(candidate_id),
                "expected_updated_at": None,
                "relevance_label": 2,
                "review_status": "reviewed",
            },
            headers=headers,
        )
    from ml_project.models import AuditLog, EvaluationLabel
    with factory() as session:
        assert session.query(EvaluationLabel).count() == 0
        assert session.query(AuditLog).count() == 0


def test_eval_audit_cross_workspace(eval_audit_client):
    client, factory = eval_audit_client
    email, _workspace_id, _job_id, _candidate_id, _association_id = _seed(factory)
    # second workspace inaccessible to this user
    with factory.begin() as session:
        from ml_project.models import Candidate, Job, JobCandidate, Workspace
        other = Workspace(name="Other", slug="other-eval")
        session.add(other)
        session.flush()
        job2 = Job(workspace_id=other.id, title="Job2", description="Desc", status="OPEN")
        cand2 = Candidate(workspace_id=other.id, full_name="Candidate2", summary="Summary")
        session.add_all([job2, cand2])
        session.flush()
        session.add(JobCandidate(workspace_id=other.id, job_id=job2.id, candidate_id=cand2.id))
    token = _token(client, email)
    headers = {"Authorization": f"Bearer {token}"}
    response = client.put(
        "/evaluations",
        json={
            "workspace_id": str(other.id),
            "job_id": str(job2.id),
            "candidate_id": str(cand2.id),
            "expected_updated_at": None,
            "relevance_label": 2,
            "review_status": "reviewed",
        },
        headers=headers,
    )
    assert response.status_code == 403
    from ml_project.models import AuditLog
    with factory() as session:
        assert session.query(AuditLog).count() == 0
