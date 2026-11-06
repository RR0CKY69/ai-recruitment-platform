"""PostgreSQL integration tests for jobs, candidates, and job-candidate assignments.

These tests exercise the same business rules as tests/test_jobs_candidates_api.py
but run against a dedicated PostgreSQL test database via the postgres_client
fixture. No SQLite-specific constructs (PRAGMA, StaticPool) are used.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from ml_project.models import (
    Candidate,
    CandidateSkill,
    CandidateSource,
    EvaluationLabel,
    Job,
    JobCandidate,
    JobRequirement,
    MatchResult,
    Shortlist,
    User,
    Workspace,
    WorkspaceMember,
)
from ml_project.security import hash_password

TEST_PASSWORD = "Read-only API test password"


def _seed_records(factory: sessionmaker):
    """Seed one user, two workspaces, two jobs, two candidates, and requirements."""
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
        return {
            "email": user.email,
            "user_id": user.id,
            "workspace_a": workspace_a.id,
            "workspace_b": workspace_b.id,
            "unassigned_workspace": unassigned_workspace.id,
            "job_a": job_a.id,
            "job_b": job_b.id,
            "candidate_a": candidate_a.id,
            "candidate_b": candidate_b.id,
        }


def _token(client, email: str) -> str:
    response = client.post(
        "/auth/login",
        json={"email": email, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _post_job(client, workspace_id, payload, token):
    return client.post(
        "/jobs",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _put_job(client, job_id, workspace_id, payload, token):
    return client.put(
        f"/jobs/{job_id}",
        json={**payload, "workspace_id": str(workspace_id)},
        headers={"Authorization": f"Bearer {token}"},
    )


def _post_candidate(client, workspace_id, payload, token):
    return client.post(
        "/candidates",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )


def _put_candidate(client, candidate_id, workspace_id, payload, token):
    return client.put(
        f"/candidates/{candidate_id}",
        json={**payload, "workspace_id": str(workspace_id)},
        headers={"Authorization": f"Bearer {token}"},
    )


def test_member_retrieves_workspace_jobs(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    response = client.get(
        "/jobs",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(records["job_a"])
    assert body[0]["title"] == "Backend Engineer"
    assert body[0]["workspace_id"] == str(records["workspace_a"])
    assert body[0]["candidate_count"] == 0


def test_job_candidate_count_uses_workspace_associations(postgres_client):
    client, factory = postgres_client
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


def test_results_are_scoped_to_requested_workspace(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])
    headers = {"Authorization": f"Bearer {token}"}

    jobs = client.get(
        "/jobs", params={"workspace_id": str(records["workspace_b"])}, headers=headers
    )
    candidates = client.get(
        "/candidates",
        params={"workspace_id": str(records["workspace_b"])},
        headers=headers,
    )

    assert jobs.status_code == candidates.status_code == 200
    assert [row["id"] for row in jobs.json()] == [str(records["job_b"])]
    assert [row["id"] for row in candidates.json()] == [str(records["candidate_b"])]
    assert all(row["workspace_id"] == str(records["workspace_b"]) for row in jobs.json())
    assert all(row["workspace_id"] == str(records["workspace_b"]) for row in candidates.json())


def test_nonmember_cannot_read_jobs_or_candidates(postgres_client):
    client, factory = postgres_client
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


def test_successful_job_creation(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "title": "Platform Engineer",
        "description": "Build services.",
        "required_skills": ["Python", "PostgreSQL", "python"],
        "employment_type": "Full-time",
        "location": "Remote",
        "minimum_experience_years": 4,
        "status": "OPEN",
    }

    response = _post_job(client, records["workspace_a"], payload, token)

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Platform Engineer"
    assert body["description"] == "Build services."
    assert body["required_skills"] == ["PostgreSQL", "Python"]
    assert body["minimum_experience_years"] == 4
    assert body["location"] == "Remote"
    assert body["employment_type"] == "Full-time"
    assert body["status"] == "OPEN"
    assert body["candidate_count"] == 0
    assert body["workspace_id"] == str(records["workspace_a"])

    with factory.begin() as session:
        job = session.get(Job, UUID(body["id"]))
        assert job is not None
        assert job.workspace_id == records["workspace_a"]
        assert job.status == "OPEN"
        skills = sorted(
            req.description
            for req in job.requirements
            if req.requirement_type == "REQUIRED_SKILL"
        )
        assert skills == ["PostgreSQL", "Python"]
        assert len(job.requirements) == 2


def test_successful_job_update(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "title": "Senior Platform Engineer",
        "description": "Updated description.",
        "required_skills": ["Go", "Kubernetes"],
        "employment_type": "Contract",
        "location": "Hybrid",
        "minimum_experience_years": 6,
        "status": "ON_HOLD",
    }

    response = _put_job(
        client, records["job_a"], records["workspace_a"], payload, token
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(records["job_a"])
    assert body["title"] == "Senior Platform Engineer"
    assert body["description"] == "Updated description."
    assert body["required_skills"] == ["Go", "Kubernetes"]
    assert body["employment_type"] == "Contract"
    assert body["location"] == "Hybrid"
    assert body["minimum_experience_years"] == 6
    assert body["status"] == "ON_HOLD"
    assert body["candidate_count"] == 0

    with factory.begin() as session:
        job = session.get(Job, records["job_a"])
        assert job.title == "Senior Platform Engineer"
        assert job.status == "ON_HOLD"
        skills = sorted(
            req.description
            for req in job.requirements
            if req.requirement_type == "REQUIRED_SKILL"
        )
        assert skills == ["Go", "Kubernetes"]
        assert len(job.requirements) == 2


def test_job_creation_rejects_invalid_status(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "title": "Engineer",
        "description": "Build.",
        "required_skills": [],
        "status": "ARCHIVED",
    }

    response = _post_job(client, records["workspace_a"], payload, token)
    assert response.status_code == 422


def test_job_update_rejects_missing_job(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "title": "Engineer",
        "description": "Build.",
        "required_skills": [],
        "status": "OPEN",
    }

    response = _put_job(client, uuid4(), records["workspace_a"], payload, token)
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found in workspace."}


def test_job_update_rejects_unauthorized_workspace(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "workspace_id": str(records["unassigned_workspace"]),
        "title": "Engineer",
        "description": "Build.",
        "required_skills": [],
        "status": "OPEN",
    }

    response = _put_job(
        client, records["job_a"], records["unassigned_workspace"], payload, token
    )
    assert response.status_code == 403


def test_job_update_rejects_cross_workspace_job(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "title": "Engineer",
        "description": "Build.",
        "required_skills": [],
        "status": "OPEN",
    }

    response = _put_job(
        client, records["job_b"], records["workspace_a"], payload, token
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "Job not found in workspace."}


def test_member_retrieves_workspace_candidates_skills_and_sources(postgres_client):
    client, factory = postgres_client
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
    assert candidate["email"] == "private-a@example.test"
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


def test_candidate_detail_returns_workspace_associations(postgres_client):
    client, factory = postgres_client
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
    assert body["email"] == "private-a@example.test"


def test_candidate_detail_is_workspace_scoped(postgres_client):
    client, factory = postgres_client
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


def test_successful_assignment_returns_assignment_card(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    response = client.post(
        f"/jobs/{records['job_a']}/candidates",
        json={"workspace_id": str(records["workspace_a"]), "candidate_id": str(records["candidate_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["candidate_id"] == str(records["candidate_a"])
    assert body["workspace_id"] == str(records["workspace_a"])
    assert body["full_name"] == "Candidate A"
    assert body["email"] == "private-a@example.test"
    assert body["current_title"] == "Backend Developer"
    assert body["summary"] == "Builds reliable services."
    assert body["experience_years"] == 5
    assert body["location"] == "Remote"
    assert body["stage"] == "SOURCED"
    assert {skill["name"] for skill in body["skills"]} == {"Python", "PostgreSQL"}


def test_assigned_candidate_listing_returns_only_explicit_assignments(postgres_client):
    client, factory = postgres_client
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
    headers = {"Authorization": f"Bearer {token}"}

    response = client.get(
        f"/jobs/{records['job_a']}/candidates",
        params={"workspace_id": str(records["workspace_a"])},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert [item["candidate_id"] for item in body] == [str(records["candidate_a"])]
    assert body[0]["stage"] == "SOURCED"
    assert body[0]["full_name"] == "Candidate A"


def test_candidate_crud_and_update(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    # Create a new candidate
    payload = {
        "workspace_id": str(records["workspace_a"]),
        "full_name": "New Candidate",
        "email": "new-candidate@example.test",
        "current_title": "Backend Developer",
        "summary": "Builds reliable services.",
        "experience_years": 5,
        "location": "Remote",
        "skills": ["Python", "SQL"],
        "sources": [],
    }

    response = _post_candidate(client, records["workspace_a"], payload, token)
    assert response.status_code == 201
    body = response.json()
    assert body["full_name"] == "New Candidate"
    assert body["email"] == "new-candidate@example.test"

    # Update the candidate
    update_payload = {
        "workspace_id": str(records["workspace_a"]),
        "full_name": "Updated Candidate",
        "email": "new-candidate-updated@example.test",
        "current_title": "Senior Developer",
        "summary": "Updated summary.",
        "experience_years": 8,
        "location": "Hybrid",
        "skills": ["Go", "Kubernetes"],
        "sources": [],
    }

    response = _put_candidate(
        client, UUID(body["id"]), records["workspace_a"], update_payload, token
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(UUID(body["id"]))
    assert body["full_name"] == "Updated Candidate"
    assert body["email"] == "new-candidate-updated@example.test"
    assert body["skills"] == [
        {"name": "Go", "normalized_name": "go", "years_experience": None},
        {"name": "Kubernetes", "normalized_name": "kubernetes", "years_experience": None},
    ]


def test_candidate_update_preserves_existing_assignments(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

    with factory.begin() as session:
        association = JobCandidate(
            workspace_id=records["workspace_a"],
            job_id=records["job_a"],
            candidate_id=records["candidate_a"],
        )
        session.add(association)
        session.flush()
        association_id = association.id

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "full_name": "Renamed Candidate",
        "email": "private-a@example.test",
        "current_title": "Senior Developer",
        "summary": "Updated.",
        "skills": ["Go"],
        "sources": [],
    }

    response = _put_candidate(
        client, records["candidate_a"], records["workspace_a"], payload, token
    )
    assert response.status_code == 200

    listing = client.get(
        f"/jobs/{records['job_a']}/candidates",
        params={"workspace_id": str(records["workspace_a"])},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert listing.status_code == 200
    assert [item["candidate_id"] for item in listing.json()] == [
        str(records["candidate_a"])
    ]

    with factory.begin() as session:
        assert session.get(JobCandidate, association_id) is not None


def test_candidate_update_preserves_recruitment_history(postgres_client):
    client, factory = postgres_client
    records = _seed_records(factory)
    token = _token(client, records["email"])

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
        session.add(
            Shortlist(
                job_candidate_id=association.id,
                added_by_id=records["user_id"],
            )
        )
        session.add(
            EvaluationLabel(
                job_candidate_id=association.id,
                reviewer_id=records["user_id"],
                relevance_label=1,
                review_status="reviewed",
            )
        )
        association_id = association.id
        match_result_id = session.scalar(
            select(MatchResult.id).where(
                MatchResult.job_candidate_id == association.id
            )
        )
        shortlist_id = session.scalar(
            select(Shortlist.id).where(
                Shortlist.job_candidate_id == association.id
            )
        )
        label_id = session.scalar(
            select(EvaluationLabel.id).where(
                EvaluationLabel.job_candidate_id == association.id
            )
        )

    payload = {
        "workspace_id": str(records["workspace_a"]),
        "full_name": "Renamed Candidate",
        "email": "private-a@example.test",
        "current_title": "Senior Developer",
        "summary": "Updated.",
        "skills": ["Go"],
        "sources": [],
    }

    response = _put_candidate(
        client, records["candidate_a"], records["workspace_a"], payload, token
    )
    assert response.status_code == 200

    with factory.begin() as session:
        assert session.get(JobCandidate, association_id) is not None
        assert session.get(MatchResult, match_result_id) is not None
        assert session.get(Shortlist, shortlist_id) is not None
        assert session.get(EvaluationLabel, label_id) is not None
