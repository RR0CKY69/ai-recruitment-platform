from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from ml_project.api.dependencies import get_api_session, get_current_user
from ml_project.api.main import app
from ml_project.models import (
    Base,
    Candidate,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    User,
    Workspace,
    WorkspaceMember,
)


@pytest.fixture
def evaluation_api(monkeypatch):
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine, expire_on_commit=False)
    reviewer = User(
        email="reviewer@example.test",
        password_hash="never-return-this",
        full_name="Reviewer One",
        is_active=True,
    )
    other_reviewer = User(
        email="reviewer-two@example.test",
        password_hash="also-private",
        full_name="Reviewer Two",
        is_active=True,
    )
    workspace = Workspace(name="Workspace One", slug="workspace-one")
    other_workspace = Workspace(name="Workspace Two", slug="workspace-two")
    session.add_all([reviewer, other_reviewer, workspace, other_workspace])
    session.flush()
    workspace.created_by_id = reviewer.id
    other_workspace.created_by_id = other_reviewer.id
    session.add_all(
        [
            WorkspaceMember(workspace_id=workspace.id, user_id=reviewer.id, role="RECRUITER"),
            WorkspaceMember(
                workspace_id=other_workspace.id,
                user_id=other_reviewer.id,
                role="ADMIN",
            ),
        ]
    )
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
    other_job = Job(
        workspace_id=other_workspace.id,
        legacy_job_id="J001",
        title="Other Workspace Job",
        status="OPEN",
    )
    other_candidate = Candidate(
        workspace_id=other_workspace.id,
        legacy_candidate_id="C001",
        full_name="Other Candidate",
    )
    session.add_all([job, candidate, other_job, other_candidate])
    session.flush()
    pair = JobCandidate(
        workspace_id=workspace.id,
        job_id=job.id,
        candidate_id=candidate.id,
        created_by_id=reviewer.id,
    )
    other_pair = JobCandidate(
        workspace_id=other_workspace.id,
        job_id=other_job.id,
        candidate_id=other_candidate.id,
    )
    session.add_all([pair, other_pair])
    session.commit()

    def session_dependency():
        yield session

    monkeypatch.setitem(app.dependency_overrides, get_api_session, session_dependency)
    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: reviewer)
    yield SimpleNamespace(
        client=TestClient(app),
        session=session,
        reviewer=reviewer,
        other_reviewer=other_reviewer,
        workspace=workspace,
        other_workspace=other_workspace,
        job=job,
        candidate=candidate,
        pair=pair,
        other_pair=other_pair,
    )
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


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


def test_get_evaluations_returns_workspace_labels_pending_pairs_and_notes(evaluation_api):
    label = EvaluationLabel(
        job_candidate_id=evaluation_api.pair.id,
        reviewer_id=evaluation_api.reviewer.id,
        relevance_label=2,
        review_status="REVIEWED",
    )
    label.notes.append(
        EvaluationNote(author_id=evaluation_api.reviewer.id, note="Strong Python evidence.")
    )
    evaluation_api.session.add(label)
    evaluation_api.session.commit()

    response = evaluation_api.client.get(
        "/evaluations", params={"workspace_id": str(evaluation_api.workspace.id)}
    )

    assert response.status_code == 200
    item = response.json()[0]
    assert item["job_id"] == str(evaluation_api.job.id)
    assert item["legacy_job_id"] == "J001"
    assert item["candidate_id"] == str(evaluation_api.candidate.id)
    assert item["legacy_candidate_id"] == "C001"
    assert item["relevance_label"] == 2
    assert item["review_status"] == "reviewed"
    assert item["reviewer_name"] == "Reviewer One"
    assert item["notes"][0]["note"] == "Strong Python evidence."
    assert "password_hash" not in response.text
    assert "private-candidate@example.test" not in response.text


def test_get_evaluations_returns_pending_for_pair_without_label(evaluation_api):
    response = evaluation_api.client.get(
        "/evaluations", params={"workspace_id": str(evaluation_api.workspace.id)}
    )

    assert response.status_code == 200
    assert response.json()[0]["relevance_label"] is None
    assert response.json()[0]["review_status"] == "needs_human_review"


def test_evaluation_retrieval_requires_authentication_and_workspace_membership(
    evaluation_api, monkeypatch
):
    url = "/evaluations"
    params = {"workspace_id": str(evaluation_api.workspace.id)}
    monkeypatch.delitem(app.dependency_overrides, get_current_user, raising=False)
    assert evaluation_api.client.get(url, params=params).status_code == 401

    monkeypatch.setitem(app.dependency_overrides, get_current_user, lambda: evaluation_api.reviewer)
    forbidden = evaluation_api.client.get(
        url, params={"workspace_id": str(evaluation_api.other_workspace.id)}
    )
    assert forbidden.status_code == 403


def test_put_creates_and_updates_reviewers_own_evaluation(evaluation_api):
    created = evaluation_api.client.put(
        "/evaluations",
        json=_payload(evaluation_api, reviewer_id=str(evaluation_api.other_reviewer.id)),
    )

    assert created.status_code == 200
    first = created.json()
    saved = evaluation_api.session.query(EvaluationLabel).one()
    assert first["reviewer_id"] == str(evaluation_api.reviewer.id)
    assert saved.reviewer_id == evaluation_api.reviewer.id
    assert saved.relevance_label == 2

    updated = evaluation_api.client.put(
        "/evaluations",
        json=_payload(
            evaluation_api,
            relevance_label=1,
            expected_updated_at=first["updated_at"],
        ),
    )
    assert updated.status_code == 200
    assert updated.json()["evaluation_id"] == first["evaluation_id"]
    assert updated.json()["relevance_label"] == 1
    assert evaluation_api.session.query(EvaluationLabel).count() == 1


@pytest.mark.parametrize("label", [0, 1, 2])
def test_put_accepts_each_supported_relevance_label(evaluation_api, label):
    response = evaluation_api.client.put(
        "/evaluations", json=_payload(evaluation_api, relevance_label=label)
    )

    assert response.status_code == 200
    assert response.json()["relevance_label"] == label
    assert evaluation_api.session.query(EvaluationLabel).one().relevance_label == label


def test_put_rejects_invalid_pair_and_cross_workspace(evaluation_api):
    invalid_pair = evaluation_api.client.put(
        "/evaluations", json=_payload(evaluation_api, candidate_id=str(uuid4()))
    )
    assert invalid_pair.status_code == 404

    cross_workspace = evaluation_api.client.put(
        "/evaluations",
        json={
            "workspace_id": str(evaluation_api.other_workspace.id),
            "job_id": str(evaluation_api.other_pair.job_id),
            "candidate_id": str(evaluation_api.other_pair.candidate_id),
                "expected_updated_at": None,
            "relevance_label": 1,
            "review_status": "reviewed",
        },
    )
    assert cross_workspace.status_code == 403
    assert evaluation_api.session.query(EvaluationLabel).count() == 0


@pytest.mark.parametrize(
    "updates",
    [
        {"relevance_label": 3},
        {"relevance_label": -1},
        {"relevance_label": True},
        {"review_status": "pending"},
        {"relevance_label": None},
        {"relevance_label": None, "review_status": "needs_human_review", "note": "invalid"},
    ],
)
def test_put_rejects_invalid_evaluation_values(evaluation_api, updates):
    response = evaluation_api.client.put("/evaluations", json=_payload(evaluation_api, **updates))
    assert response.status_code == 422


def test_put_supports_note_create_and_author_owned_update(evaluation_api):
    created = evaluation_api.client.put(
        "/evaluations", json=_payload(evaluation_api, note="Initial reviewer note.")
    )
    assert created.status_code == 200
    note = created.json()["notes"][0]
    assert note["author_id"] == str(evaluation_api.reviewer.id)

    updated = evaluation_api.client.put(
        "/evaluations",
        json=_payload(
            evaluation_api,
            note="Updated reviewer note.",
            note_id=note["note_id"],
            expected_updated_at=created.json()["updated_at"],
        ),
    )
    assert updated.status_code == 200
    assert len(updated.json()["notes"]) == 1
    assert updated.json()["notes"][0]["note"] == "Updated reviewer note."


def test_put_cannot_update_another_reviewers_note(evaluation_api):
    label = EvaluationLabel(
        job_candidate_id=evaluation_api.pair.id,
        reviewer_id=evaluation_api.reviewer.id,
        relevance_label=1,
        review_status="REVIEWED",
    )
    label.notes.append(
        EvaluationNote(author_id=evaluation_api.other_reviewer.id, note="Another reviewer's note")
    )
    evaluation_api.session.add(label)
    evaluation_api.session.commit()
    note = evaluation_api.session.query(EvaluationNote).one()

    response = evaluation_api.client.put(
        "/evaluations",
        json=_payload(
            evaluation_api,
            note="Attempted overwrite",
            note_id=str(note.id),
            expected_updated_at=note.evaluation_label.updated_at.isoformat(),
        ),
    )

    assert response.status_code == 404
    assert evaluation_api.session.get(EvaluationNote, note.id).note == "Another reviewer's note"


def test_put_rejects_stale_evaluation_timestamp(evaluation_api):
    created = evaluation_api.client.put("/evaluations", json=_payload(evaluation_api))
    assert created.status_code == 200
    updated = evaluation_api.client.put(
        "/evaluations",
        json=_payload(
            evaluation_api,
            relevance_label=1,
            expected_updated_at="2000-01-01T00:00:00Z",
        ),
    )
    assert updated.status_code == 409
    assert evaluation_api.session.query(EvaluationLabel).one().relevance_label == 2


def test_needs_human_review_is_not_persisted_as_a_fake_label(evaluation_api):
    response = evaluation_api.client.put(
        "/evaluations",
        json=_payload(
            evaluation_api,
            relevance_label=None,
            review_status="needs_human_review",
        ),
    )

    assert response.status_code == 200
    assert response.json()["evaluation_id"] is None
    assert response.json()["review_status"] == "needs_human_review"
    assert evaluation_api.session.query(EvaluationLabel).count() == 0
