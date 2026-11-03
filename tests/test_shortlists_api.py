from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from ml_project.api.dependencies import get_api_session, get_current_user
from ml_project.api.main import app
from ml_project.models import (
    Candidate,
    Job,
    JobCandidate,
    Shortlist,
    User,
    WorkspaceMember,
)

WORKSPACE_ID = UUID("10000000-0000-4000-8000-000000000001")
JOB_ID = UUID("20000000-0000-4000-8000-000000000001")
CANDIDATE_ID = UUID("30000000-0000-4000-8000-000000000001")
USER_ID = UUID("40000000-0000-4000-8000-000000000001")
SHORTLIST_ID = UUID("50000000-0000-4000-8000-000000000001")
ASSOCIATION_ID = UUID("60000000-0000-4000-8000-000000000001")

USER = User(
    id=USER_ID,
    email="recruiter@example.test",
    password_hash="not-returned",
    full_name="Recruiter Example",
    is_active=True,
)
JOB = Job(
    id=JOB_ID,
    workspace_id=WORKSPACE_ID,
    title="Engineer",
    description="Build systems",
    status="OPEN",
)
CANDIDATE = Candidate(
    id=CANDIDATE_ID,
    workspace_id=WORKSPACE_ID,
    full_name="Candidate Example",
    current_title="Developer",
    summary="Experienced developer.",
    experience_years=5,
    location="Lahore",
)
MEMBERSHIP = WorkspaceMember(
    id=uuid4(), workspace_id=WORKSPACE_ID, user_id=USER_ID, role="RECRUITER"
)


class FakeResult:
    def __init__(self, rows=()):
        self.rows = list(rows)

    def one_or_none(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class FakeSession:
    """Minimal session double for API behavior tests; it never opens a database."""

    def __init__(self, scalar_values=(), execute_results=()):
        self.scalar_values = list(scalar_values)
        self.execute_results = list(execute_results)
        self.statements = []
        self.added = []
        self.commits = 0
        self.rollbacks = 0

    def scalar(self, _statement):
        return self.scalar_values.pop(0) if self.scalar_values else None

    def execute(self, statement):
        self.statements.append(statement)
        return self.execute_results.pop(0) if self.execute_results else FakeResult()

    def add(self, record):
        self.added.append(record)

    def flush(self):
        for record in self.added:
            if isinstance(record, JobCandidate) and record.id is None:
                record.id = uuid4()
            if isinstance(record, Shortlist) and record.id is None:
                record.id = uuid4()

    def commit(self):
        self.commits += 1
        for record in self.added:
            if isinstance(record, Shortlist):
                record.id = record.id or uuid4()
                record.created_at = record.created_at or datetime.now(timezone.utc)

    def rollback(self):
        self.rollbacks += 1


def _row(status="ACTIVE"):
    association = JobCandidate(
        id=ASSOCIATION_ID,
        workspace_id=WORKSPACE_ID,
        job_id=JOB_ID,
        candidate_id=CANDIDATE_ID,
    )
    shortlist = Shortlist(
        id=SHORTLIST_ID,
        job_candidate_id=association.id,
        added_by_id=USER_ID,
        status=status,
        created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
    )
    return shortlist, association, JOB, CANDIDATE, USER


def _client(monkeypatch, session, *, authenticated=True):
    monkeypatch.setitem(app.dependency_overrides, get_api_session, lambda: session)
    if authenticated:
        monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: USER)
    else:
        monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    return TestClient(app)


def test_post_creates_shortlist_and_returns_valid_public_response(monkeypatch):
    row = _row()
    session = FakeSession(
        scalar_values=[MEMBERSHIP, JOB, CANDIDATE, None, None],
        execute_results=[FakeResult([row])],
    )
    client = _client(monkeypatch, session)

    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(WORKSPACE_ID),
            "job_id": str(JOB_ID),
            "candidate_id": str(CANDIDATE_ID),
        },
    )

    assert response.status_code == 201
    assert response.json()["candidate_name"] == "Candidate Example"
    assert response.json()["job_title"] == "Engineer"
    assert response.json()["recruiter_name"] == "Recruiter Example"
    assert "password_hash" not in response.json()
    assert session.commits == 1
    saved_pair = next(record for record in session.added if isinstance(record, JobCandidate))
    saved_shortlist = next(record for record in session.added if isinstance(record, Shortlist))
    assert saved_pair.workspace_id == WORKSPACE_ID
    assert saved_shortlist.added_by_id == USER_ID


def test_duplicate_post_is_idempotent(monkeypatch):
    row = _row()
    session = FakeSession(
        scalar_values=[MEMBERSHIP, JOB, CANDIDATE, row[1], row[0]],
        execute_results=[FakeResult([row])],
    )
    client = _client(monkeypatch, session)

    response = client.post(
        "/shortlists",
        json={
            "workspace_id": str(WORKSPACE_ID),
            "job_id": str(JOB_ID),
            "candidate_id": str(CANDIDATE_ID),
        },
    )

    assert response.status_code == 200
    assert response.json()["shortlist_id"] == str(SHORTLIST_ID)
    assert session.commits == 0


def test_list_filters_by_job_and_returns_empty_list(monkeypatch):
    row = _row()
    session = FakeSession(
        scalar_values=[MEMBERSHIP],
        execute_results=[FakeResult([row])],
    )
    client = _client(monkeypatch, session)

    response = client.get(
        "/shortlists",
        params={"workspace_id": str(WORKSPACE_ID), "job_id": str(JOB_ID)},
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert "job_candidates.job_id" in str(
        session.statements[0].compile(compile_kwargs={"literal_binds": True})
    )

    empty_session = FakeSession(scalar_values=[MEMBERSHIP], execute_results=[FakeResult()])
    empty_response = _client(monkeypatch, empty_session).get(
        "/shortlists", params={"workspace_id": str(WORKSPACE_ID)}
    )
    assert empty_response.status_code == 200
    assert empty_response.json() == []


def test_delete_soft_removes_record(monkeypatch):
    row = _row()
    session = FakeSession(
        scalar_values=[MEMBERSHIP],
        execute_results=[FakeResult([row])],
    )
    client = _client(monkeypatch, session)

    response = client.delete(
        f"/shortlists/{SHORTLIST_ID}", params={"workspace_id": str(WORKSPACE_ID)}
    )

    assert response.status_code == 204
    assert row[0].status == "REMOVED"
    assert session.commits == 1


def test_workspace_membership_and_authentication_are_required(monkeypatch):
    forbidden_client = _client(monkeypatch, FakeSession(scalar_values=[None]))
    response = forbidden_client.get("/shortlists", params={"workspace_id": str(WORKSPACE_ID)})
    assert response.status_code == 403

    unauthenticated_client = _client(monkeypatch, FakeSession(), authenticated=False)
    response = unauthenticated_client.get(
        "/shortlists", params={"workspace_id": str(WORKSPACE_ID)}
    )
    assert response.status_code == 401


def test_database_errors_return_generic_response(monkeypatch):
    class BrokenSession(FakeSession):
        def scalar(self, _statement):
            raise SQLAlchemyError("internal connection detail")

    response = _client(monkeypatch, BrokenSession()).get(
        "/shortlists", params={"workspace_id": str(WORKSPACE_ID)}
    )

    assert response.status_code == 500
    assert response.json() == {"detail": "The database operation could not be completed."}
    assert "internal connection detail" not in response.text


def test_invalid_identifiers_return_validation_or_not_found(monkeypatch):
    client = _client(monkeypatch, FakeSession())
    invalid_uuid = client.post(
        "/shortlists",
        json={"workspace_id": "bad", "job_id": str(JOB_ID), "candidate_id": str(CANDIDATE_ID)},
    )
    assert invalid_uuid.status_code == 422

    missing_job = _client(monkeypatch, FakeSession(scalar_values=[MEMBERSHIP, None])).post(
        "/shortlists",
        json={
            "workspace_id": str(WORKSPACE_ID),
            "job_id": str(JOB_ID),
            "candidate_id": str(CANDIDATE_ID),
        },
    )
    assert missing_job.status_code == 404

    missing_candidate = _client(
        monkeypatch, FakeSession(scalar_values=[MEMBERSHIP, JOB, None])
    ).post(
        "/shortlists",
        json={
            "workspace_id": str(WORKSPACE_ID),
            "job_id": str(JOB_ID),
            "candidate_id": str(CANDIDATE_ID),
        },
    )
    assert missing_candidate.status_code == 404
