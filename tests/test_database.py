import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, event, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ml_project import config
from ml_project.config import get_database_url
from ml_project.database import create_session_factory, get_session, initialize_database
from ml_project.models import (
    AuditLog,
    Candidate,
    CandidateSkill,
    CandidateSource,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    JobRequirement,
    MatchResult,
    RefreshSession,
    SearchQuery,
    Shortlist,
    SourcingTask,
    User,
    Workspace,
    WorkspaceMember,
)

EXPECTED_TABLES = {
    "workspaces",
    "users",
    "workspace_members",
    "jobs",
    "job_requirements",
    "candidates",
    "candidate_skills",
    "candidate_sources",
    "search_queries",
    "sourcing_tasks",
    "job_candidates",
    "match_results",
    "shortlists",
    "evaluation_labels",
    "evaluation_notes",
    "audit_logs",
    "refresh_sessions",
}
PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _sqlite_engine(database_url: str = "sqlite+pysqlite:///:memory:"):
    engine = create_engine(database_url)

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def test_database_initialization_creates_all_tables_and_timestamps():
    engine = _sqlite_engine()
    initialize_database(engine)
    initialize_database(engine)

    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == EXPECTED_TABLES
    for table_name in EXPECTED_TABLES:
        assert {"created_at", "updated_at"}.issubset(
            {column["name"] for column in inspector.get_columns(table_name)}
        )


def test_core_relationships_and_json_records_persist():
    engine = _sqlite_engine()
    initialize_database(engine)
    factory = create_session_factory(engine)

    with factory() as session:
        user = User(email="recruiter@example.com", password_hash="hashed-value", full_name="Recruiter")
        workspace = Workspace(name="Shared Team", slug="shared-team", created_by_id=None)
        session.add_all([user, workspace])
        session.flush()
        workspace.created_by_id = user.id
        member = WorkspaceMember(workspace=workspace, user=user, role="ADMIN")
        job = Job(workspace=workspace, title="Engineer", description="Build systems", status="OPEN")
        candidate = Candidate(workspace=workspace, full_name="Candidate", email="candidate@example.com")
        job.requirements.append(
            JobRequirement(requirement_type="REQUIRED_SKILL", description="Python")
        )
        candidate.skills.append(CandidateSkill(name="Python", normalized_name="python"))
        candidate.sources.append(
            CandidateSource(provider="Authorized import", source_metadata={"batch": "A"})
        )
        session.add_all([member, job, candidate])
        session.flush()

        association = JobCandidate(workspace_id=workspace.id, job=job, candidate=candidate)
        session.add(association)
        session.flush()
        association.match_results.append(
            MatchResult(
                model_name="tfidf",
                model_version="baseline-v1",
                tfidf_similarity=0.5,
                explanation={"note": "text similarity only"},
            )
        )
        association.shortlist_entries.append(Shortlist(added_by_id=user.id))
        label = EvaluationLabel(
            job_candidate=association, reviewer_id=user.id, relevance_label=2
        )
        label.notes.append(EvaluationNote(author_id=user.id, note="Reviewed manually."))
        session.add_all(
            [
                SearchQuery(
                    workspace_id=workspace.id,
                    job_id=job.id,
                    created_by_id=user.id,
                    name="Python search",
                    query_text="Python AND API",
                ),
                SourcingTask(
                    workspace_id=workspace.id,
                    job_id=job.id,
                    requested_by_id=user.id,
                    source_provider="Authorized API",
                ),
                AuditLog(
                    workspace_id=workspace.id,
                    actor_id=user.id,
                    action="job.created",
                    entity_type="job",
                    entity_id=job.id,
                ),
                label,
            ]
        )
        session.commit()

        assert session.scalar(select(JobCandidate)).candidate.full_name == "Candidate"
        assert session.scalar(select(EvaluationLabel)).notes[0].note == "Reviewed manually."
        assert len(session.scalars(select(MatchResult)).all()) == 1


def test_refresh_session_creation_user_relationship_token_hash_expiration_and_revocation():
    from datetime import datetime, timedelta, timezone
    import uuid

    engine = _sqlite_engine()
    initialize_database(engine)
    factory = create_session_factory(engine)

    with factory() as session:
        user = User(email="refresh@example.com", password_hash="hashed", full_name="Refresh User")
        session.add(user)
        session.flush()

        family_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=7)
        refresh_session = RefreshSession(
            user_id=user.id,
            token_hash="test-hash-value-123",
            family_id=family_id,
            expires_at=expires_at,
        )
        session.add(refresh_session)
        session.commit()

        loaded = session.scalar(select(RefreshSession))
        assert loaded is not None
        assert loaded.user_id == user.id
        assert loaded.token_hash == "test-hash-value-123"
        assert loaded.family_id == family_id
        assert loaded.expires_at == expires_at
        assert loaded.revoked_at is None
        assert loaded.user.email == "refresh@example.com"
        assert loaded in user.refresh_sessions


def test_refresh_session_migration_creates_table_with_indexes_and_timestamps(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    database_file = tmp_path / "refresh-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_file.as_posix()}")
    engine = create_engine(f"sqlite+pysqlite:///{database_file.as_posix()}")
    config_obj = Config(str(PROJECT_ROOT / "alembic.ini"))

    command.upgrade(config_obj, "head")

    inspector = inspect(engine)
    assert "refresh_sessions" in inspector.get_table_names()
    columns = {c["name"] for c in inspector.get_columns("refresh_sessions")}
    assert {"id", "user_id", "token_hash", "family_id", "created_at", "updated_at", "expires_at", "revoked_at"}.issubset(columns)
    indexes = {idx["name"] for idx in inspector.get_indexes("refresh_sessions")}
    assert "ix_refresh_sessions_user_id" in indexes
    assert "ix_refresh_sessions_family_id" in indexes
    assert "ix_refresh_sessions_expires_at" in indexes


def test_constraints_reject_duplicate_email_and_cross_workspace_pair():
    engine = _sqlite_engine()
    initialize_database(engine)
    with Session(engine) as session:
        first_workspace = Workspace(name="One", slug="one")
        second_workspace = Workspace(name="Two", slug="two")
        session.add_all([first_workspace, second_workspace])
        session.commit()
        session.add_all(
            [
                Candidate(
                    workspace_id=first_workspace.id,
                    full_name="First",
                    email="person@example.com",
                ),
                Candidate(
                    workspace_id=first_workspace.id,
                    full_name="Duplicate",
                    email="PERSON@example.com",
                ),
            ]
        )
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        first_workspace = session.scalar(select(Workspace).where(Workspace.slug == "one"))
        second_workspace = session.scalar(select(Workspace).where(Workspace.slug == "two"))
        job = Job(workspace_id=first_workspace.id, title="Private job")
        candidate = Candidate(workspace_id=second_workspace.id, full_name="Other workspace")
        session.add_all([job, candidate])
        session.flush()
        session.add(
            JobCandidate(workspace_id=first_workspace.id, job_id=job.id, candidate_id=candidate.id)
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_role_and_evaluation_label_checks_reject_invalid_values():
    engine = _sqlite_engine()
    initialize_database(engine)
    with Session(engine) as session:
        user = User(email="user@example.com", password_hash="hash", full_name="User")
        workspace = Workspace(name="Workspace", slug="workspace")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="OWNER"))
        with pytest.raises(IntegrityError):
            session.flush()
        session.rollback()

        user = User(email="user2@example.com", password_hash="hash", full_name="User Two")
        workspace = Workspace(name="Workspace Two", slug="workspace-two")
        session.add_all([user, workspace])
        session.flush()
        job = Job(workspace_id=workspace.id, title="Engineer")
        candidate = Candidate(workspace_id=workspace.id, full_name="Candidate")
        session.add_all([job, candidate])
        session.flush()
        association = JobCandidate(
            workspace_id=workspace.id, job_id=job.id, candidate_id=candidate.id
        )
        session.add(association)
        session.flush()
        session.add(
            EvaluationLabel(
                job_candidate_id=association.id, reviewer_id=user.id, relevance_label=5
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()


def test_alembic_initial_migration_applies_to_isolated_sqlite(tmp_path, monkeypatch):
    database_file = tmp_path / "migration-test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{database_file.as_posix()}")
    config = Config(str(PROJECT_ROOT / "alembic.ini"))

    command.upgrade(config, "head")

    engine = create_engine(f"sqlite+pysqlite:///{database_file.as_posix()}")
    assert set(inspect(engine).get_table_names()) == EXPECTED_TABLES | {"alembic_version"}
    assert "uq_jobs_workspace_legacy_job_id" in {
        constraint["name"] for constraint in inspect(engine).get_unique_constraints("jobs")
    }
    assert "uq_candidates_workspace_legacy_candidate_id" in {
        constraint["name"] for constraint in inspect(engine).get_unique_constraints("candidates")
    }
    with engine.connect() as connection:
        candidate_email_indexes = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'index' "
            "AND name = 'uq_candidates_workspace_email_ci'"
        ).all()
    assert len(candidate_email_indexes) == 1

    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT version_num FROM alembic_version").all() == []


def test_postgresql_migration_path_does_not_recreate_initial_email_index():
    revision_path = (
        PROJECT_ROOT
        / "migrations"
        / "versions"
        / "2b4d7f0a91c3_add_legacy_id_uniqueness.py"
    )
    spec = importlib.util.spec_from_file_location("legacy_id_migration", revision_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))

    migration._restore_candidate_email_index_if_sqlite(bind)


def test_database_url_is_read_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:secret@localhost/app")

    assert get_database_url() == "postgresql+psycopg://user:secret@localhost/app"


def test_missing_database_url_is_an_actionable_error(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(config, "load_dotenv", lambda *_args, **_kwargs: None)

    with pytest.raises(RuntimeError, match="Copy .env.example to .env"):
        get_database_url()


def test_session_dependency_closes_session():
    engine = _sqlite_engine()
    initialize_database(engine)
    class TrackingSession(Session):
        was_closed = False

        def close(self):
            self.was_closed = True
            super().close()

    factory = sessionmaker(bind=engine, class_=TrackingSession, expire_on_commit=False)
    session_generator = get_session(factory)
    session = next(session_generator)

    session_generator.close()

    assert session.was_closed
