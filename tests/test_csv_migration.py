import json
from pathlib import Path
from uuid import UUID

import pandas as pd
import pytest
from sqlalchemy import create_engine, event, select

from ml_project import csv_migration
from ml_project.csv_migration import (
    MigrationConflict,
    execute_migration,
    validate_csv_data,
    write_report,
)
from ml_project.database import create_session_factory, initialize_database
from ml_project.models import (
    Candidate,
    CandidateSource,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    User,
    Workspace,
    WorkspaceMember,
)


def _write_fixture_data(directory: Path) -> None:
    pd.DataFrame(
        [
            {
                "job_id": "J001",
                "job_title": "Engineer",
                "description": "Build systems with Python.",
                "required_skills": "Python; SQL",
                "min_experience": 3,
                "location": "Remote",
            },
            {
                "job_id": "J002",
                "job_title": "Analyst",
                "description": "Analyze data.",
                "required_skills": "Pandas",
                "min_experience": 1,
                "location": "Lahore",
            },
        ]
    ).to_csv(directory / "jobs.csv", index=False)
    pd.DataFrame(
        [
            {
                "candidate_id": "C001",
                "name": "Ayesha Khan",
                "current_title": "Python Engineer",
                "summary": "Builds data services.",
                "skills": "Python; PostgreSQL",
                "experience_years": 4,
                "location": "Remote",
            },
            {
                "candidate_id": "C002",
                "name": "Bilal Ahmed",
                "current_title": "Data Analyst",
                "summary": "Creates reports.",
                "skills": "Pandas; Excel",
                "experience_years": 2,
                "location": "Lahore",
            },
        ]
    ).to_csv(directory / "candidates.csv", index=False)
    pd.DataFrame(
        [
            {"job_id": "J001", "candidate_id": "C001", "relevance_label": 2, "label_review_status": "reviewed"},
            {"job_id": "J001", "candidate_id": "C002", "relevance_label": None, "label_review_status": "needs_human_review"},
            {"job_id": "J002", "candidate_id": "C001", "relevance_label": 1, "label_review_status": "reviewed"},
        ]
    ).to_csv(directory / "evaluation.csv", index=False)
    pd.DataFrame(
        [
            {"job_id": "J001", "candidate_id": "C001", "reviewer_notes": "Manually reviewed profile."},
            {"job_id": "J001", "candidate_id": "C002", "reviewer_notes": ""},
            {"job_id": "J002", "candidate_id": "C001", "reviewer_notes": "Relevant transferable background."},
        ]
    ).to_csv(directory / "evaluation_notes.csv", index=False)


def _sqlite_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    initialize_database(engine)
    return engine, create_session_factory(engine)


def _seed_workspace(factory):
    with factory.begin() as session:
        user = User(email="reviewer@example.com", password_hash="hash", full_name="Reviewer")
        workspace = Workspace(name="Recruitment Team", slug="recruitment-team")
        session.add_all([user, workspace])
        session.flush()
        session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="ADMIN"))
        session.flush()
        return workspace.id, user.id


def test_dry_run_counts_records_and_does_not_open_database(tmp_path):
    _write_fixture_data(tmp_path)

    plan = validate_csv_data(tmp_path)

    assert plan.report["source_counts"] == {
        "jobs": 2,
        "candidates": 2,
        "evaluation_records": 3,
        "evaluation_notes_records": 3,
    }
    assert plan.report["validation"]["invalid_records_total"] == 0
    assert plan.report["expected_insert_counts_if_target_empty"]["job_candidates"] == 3
    assert plan.report["expected_insert_counts_if_target_empty"]["evaluation_labels"] == 2
    assert plan.report["expected_insert_counts_if_target_empty"]["pending_evaluations_not_stored_as_labels"] == 1
    assert plan.report["expected_insert_counts_if_target_empty"]["evaluation_notes"] == 2
    report_path = tmp_path / "migration-report.json"
    write_report(plan.report, report_path)
    assert json.loads(report_path.read_text(encoding="utf-8"))["target_database_inspected"] is False


def test_missing_required_columns_are_reported(tmp_path):
    _write_fixture_data(tmp_path)
    pd.DataFrame([{"job_id": "J1", "job_title": "Incomplete"}]).to_csv(
        tmp_path / "jobs.csv", index=False
    )

    plan = validate_csv_data(tmp_path)

    assert plan.has_errors
    assert any(
        issue["dataset"] == "jobs" and issue["issue"] == "required column is missing"
        for issue in plan.report["validation"]["issues"]
    )


def test_duplicate_jobs_and_candidates_are_reported(tmp_path):
    _write_fixture_data(tmp_path)
    jobs = pd.read_csv(tmp_path / "jobs.csv")
    pd.concat([jobs, jobs.iloc[[0]]]).to_csv(tmp_path / "jobs.csv", index=False)
    candidates = pd.read_csv(tmp_path / "candidates.csv")
    pd.concat([candidates, candidates.iloc[[0]]]).to_csv(tmp_path / "candidates.csv", index=False)

    plan = validate_csv_data(tmp_path)

    assert plan.report["validation"]["duplicate_record_counts"]["jobs"] == 1
    assert plan.report["validation"]["duplicate_record_counts"]["candidates"] == 1
    assert plan.has_errors


def test_duplicate_candidate_profile_with_new_legacy_id_is_reported(tmp_path):
    _write_fixture_data(tmp_path)
    candidates = pd.read_csv(tmp_path / "candidates.csv")
    duplicate = candidates.iloc[[0]].copy()
    duplicate.loc[:, "candidate_id"] = "C999"
    pd.concat([candidates, duplicate]).to_csv(tmp_path / "candidates.csv", index=False)

    plan = validate_csv_data(tmp_path)

    assert plan.report["validation"]["duplicate_record_counts"]["candidates"] == 1
    assert any("duplicate candidate profile content" in issue["issue"] for issue in plan.report["validation"]["issues"])


def test_invalid_experience_and_orphan_evaluation_pairs_are_reported(tmp_path):
    _write_fixture_data(tmp_path)
    jobs = pd.read_csv(tmp_path / "jobs.csv")
    jobs["min_experience"] = jobs["min_experience"].astype("string")
    jobs.loc[0, "min_experience"] = "several"
    jobs.to_csv(tmp_path / "jobs.csv", index=False)
    evaluations = pd.read_csv(tmp_path / "evaluation.csv")
    evaluations.loc[0, "job_id"] = "J999"
    evaluations.to_csv(tmp_path / "evaluation.csv", index=False)

    plan = validate_csv_data(tmp_path)

    issues = plan.report["validation"]["issues"]
    assert any(issue["field"] == "min_experience" for issue in issues)
    assert any("nonexistent" in issue["issue"] for issue in issues)


def test_invalid_candidate_reference_is_reported(tmp_path):
    _write_fixture_data(tmp_path)
    evaluations = pd.read_csv(tmp_path / "evaluation.csv", dtype="string")
    evaluations.loc[0, "candidate_id"] = "C999"
    evaluations.to_csv(tmp_path / "evaluation.csv", index=False)

    plan = validate_csv_data(tmp_path)

    assert any(
        issue["dataset"] == "evaluations"
        and issue["field"] == "candidate_id"
        and "nonexistent" in issue["issue"]
        for issue in plan.report["validation"]["issues"]
    )


def test_nonempty_note_without_reviewed_label_is_reported(tmp_path):
    _write_fixture_data(tmp_path)
    notes = pd.read_csv(tmp_path / "evaluation_notes.csv", dtype="string")
    notes.loc[(notes["job_id"] == "J001") & (notes["candidate_id"] == "C002"), "reviewer_notes"] = "Note on pending pair"
    notes.to_csv(tmp_path / "evaluation_notes.csv", index=False)

    plan = validate_csv_data(tmp_path)

    assert plan.has_errors
    assert any("no reviewed evaluation label" in issue["issue"] for issue in plan.report["validation"]["issues"])


def test_uuid_mapping_relationships_labels_notes_and_reconciliation(tmp_path):
    _write_fixture_data(tmp_path)
    candidates = pd.read_csv(tmp_path / "candidates.csv")
    candidates["source_provider"] = "Authorized CSV provider"
    candidates["source_url"] = "https://example.invalid/profile"
    candidates["authorized_basis"] = "consented export"
    candidates.to_csv(tmp_path / "candidates.csv", index=False)
    _engine, factory = _sqlite_factory()
    workspace_id, reviewer_id = _seed_workspace(factory)
    plan = validate_csv_data(tmp_path)

    report = execute_migration(
        plan,
        factory,
        workspace_id=workspace_id,
        reviewer_user_id=reviewer_id,
    )

    imported = report["actual_import"]
    assert imported["legacy_job_id_to_uuid"]["J001"] != "J001"
    assert imported["legacy_candidate_id_to_uuid"]["C001"] != "C001"
    assert report["reconciliation"]["all_checks_passed"]
    assert report["reconciliation"]["job_candidates"]["database_mapped"] == 3
    assert report["reconciliation"]["evaluation_labels"]["database_for_reviewer"] == 2
    assert report["reconciliation"]["reviewer_notes"]["database_matching_notes"] == 2
    assert report["reconciliation"]["pending_evaluations"]["database_pending_pairs"] == 1

    with factory() as session:
        pair = session.scalar(
            select(JobCandidate).where(
                JobCandidate.workspace_id == workspace_id,
                JobCandidate.job_id == UUID(imported["legacy_job_id_to_uuid"]["J001"]),
                JobCandidate.candidate_id == UUID(imported["legacy_candidate_id_to_uuid"]["C001"]),
            )
        )
        label = session.scalar(
            select(EvaluationLabel).where(EvaluationLabel.job_candidate_id == pair.id)
        )
        note = session.scalar(
            select(EvaluationNote).where(EvaluationNote.evaluation_label_id == label.id)
        )
        assert label.relevance_label == 2
        assert note.note == "Manually reviewed profile."
        assert session.scalar(select(Job).where(Job.id == pair.job_id)).legacy_job_id == "J001"
        assert session.scalar(select(Candidate).where(Candidate.id == pair.candidate_id)).legacy_candidate_id == "C001"
        source = session.scalar(
            select(CandidateSource).where(CandidateSource.candidate_id == pair.candidate_id)
        )
        assert source.provider == "Authorized CSV provider"
        assert source.source_url == "https://example.invalid/profile"
        assert source.authorized_basis == "consented export"


def test_workspace_creation_requires_explicit_values_and_existing_reviewer(tmp_path):
    _write_fixture_data(tmp_path)
    _, factory = _sqlite_factory()
    with factory.begin() as session:
        reviewer = User(email="bootstrap@example.com", password_hash="hash", full_name="Bootstrap")
        session.add(reviewer)
        session.flush()
        reviewer_id = reviewer.id
    plan = validate_csv_data(tmp_path)

    report = execute_migration(
        plan,
        factory,
        workspace_name="Explicit Team",
        workspace_slug="explicit-team",
        workspace_member_role="ADMIN",
        reviewer_user_id=reviewer_id,
    )

    assert report["actual_import"]["inserted"]["workspace"] == 1
    assert report["actual_import"]["inserted"]["workspace_member"] == 1
    with factory() as session:
        workspace = session.scalar(select(Workspace).where(Workspace.slug == "explicit-team"))
        assert workspace.name == "Explicit Team"
        assert session.scalar(select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace.id)).role == "ADMIN"


def test_rerun_is_idempotent_and_preserves_existing_label_and_note(tmp_path):
    _write_fixture_data(tmp_path)
    _, factory = _sqlite_factory()
    workspace_id, reviewer_id = _seed_workspace(factory)

    first = execute_migration(
        validate_csv_data(tmp_path), factory, workspace_id=workspace_id, reviewer_user_id=reviewer_id
    )
    second = execute_migration(
        validate_csv_data(tmp_path), factory, workspace_id=workspace_id, reviewer_user_id=reviewer_id
    )

    assert first["reconciliation"]["all_checks_passed"]
    assert second["reconciliation"]["all_checks_passed"]
    assert second["actual_import"]["inserted"]["jobs"] == 0
    assert second["actual_import"]["inserted"]["evaluation_labels"] == 0
    assert second["actual_import"]["skipped_idempotent"]["evaluation_labels"] == 2
    with factory() as session:
        assert len(session.scalars(select(EvaluationLabel)).all()) == 2
        assert len(session.scalars(select(EvaluationNote)).all()) == 2


def test_changed_csv_label_never_overwrites_existing_human_label(tmp_path):
    _write_fixture_data(tmp_path)
    _, factory = _sqlite_factory()
    workspace_id, reviewer_id = _seed_workspace(factory)
    execute_migration(
        validate_csv_data(tmp_path), factory, workspace_id=workspace_id, reviewer_user_id=reviewer_id
    )

    evaluations = pd.read_csv(tmp_path / "evaluation.csv")
    evaluations.loc[
        (evaluations["job_id"] == "J001") & (evaluations["candidate_id"] == "C001"),
        "relevance_label",
    ] = 0
    evaluations.to_csv(tmp_path / "evaluation.csv", index=False)
    with pytest.raises(MigrationConflict, match="human label conflicts"):
        execute_migration(
            validate_csv_data(tmp_path), factory, workspace_id=workspace_id, reviewer_user_id=reviewer_id
        )

    with factory() as session:
        assert session.scalar(select(EvaluationLabel)).relevance_label == 2


def test_conflicting_existing_data_rolls_back_whole_import(tmp_path):
    _write_fixture_data(tmp_path)
    _, factory = _sqlite_factory()
    workspace_id, reviewer_id = _seed_workspace(factory)
    with factory.begin() as session:
        session.add(
            Job(
                workspace_id=workspace_id,
                legacy_job_id="J002",
                title="Conflicting existing title",
                description="Different source value",
                status="DRAFT",
            )
        )

    plan = validate_csv_data(tmp_path)
    with pytest.raises(MigrationConflict, match="differs from CSV"):
        execute_migration(
            plan, factory, workspace_id=workspace_id, reviewer_user_id=reviewer_id
        )

    with factory() as session:
        jobs = session.scalars(select(Job).where(Job.workspace_id == workspace_id)).all()
        candidates = session.scalars(select(Candidate).where(Candidate.workspace_id == workspace_id)).all()
        assert [job.legacy_job_id for job in jobs] == ["J002"]
        assert candidates == []
        assert session.scalars(select(JobCandidate)).all() == []


def test_dry_run_does_not_write_to_database(tmp_path):
    _write_fixture_data(tmp_path)
    engine, _factory = _sqlite_factory()
    before = len(inspect_tables(engine))

    plan = validate_csv_data(tmp_path)

    assert not plan.has_errors
    assert len(inspect_tables(engine)) == before


def test_cli_dry_run_never_creates_database_factory(tmp_path, monkeypatch, capsys):
    _write_fixture_data(tmp_path)
    report_path = tmp_path / "dry-run-report.json"

    def unexpected_database_access():
        raise AssertionError("dry-run must not create a database session factory")

    monkeypatch.setattr(csv_migration, "create_session_factory", unexpected_database_access)
    monkeypatch.setattr(
        csv_migration,
        "execute_migration",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("dry-run must not call execute_migration")
        ),
    )

    exit_code = csv_migration.main(
        ["--dry-run", "--data-dir", str(tmp_path), "--report", str(report_path)]
    )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["mode"] == "dry_run"
    assert report["actual_import"] is None
    assert "Database modified: no (dry run)" in output


def test_cli_execute_reaches_import_path_without_running_database_import(
    tmp_path, monkeypatch, capsys
):
    _write_fixture_data(tmp_path)
    report_path = tmp_path / "execute-report.json"
    workspace_id = UUID("22222222-2222-4222-8222-222222222222")
    reviewer_id = UUID("33333333-3333-4333-8333-333333333333")
    factory_sentinel = object()
    execution_calls = []

    def fake_execute(plan, factory, **kwargs):
        execution_calls.append((plan, factory, kwargs))
        execution_report = dict(plan.report)
        execution_report.update(
            {
                "mode": "execute",
                "actual_import": {"workspace_id": str(workspace_id)},
                "reconciliation": {"all_checks_passed": True},
            }
        )
        return execution_report

    monkeypatch.setattr(csv_migration, "create_session_factory", lambda: factory_sentinel)
    monkeypatch.setattr(csv_migration, "execute_migration", fake_execute)

    exit_code = csv_migration.main(
        [
            "--execute",
            "--workspace-id",
            str(workspace_id),
            "--reviewer-user-id",
            str(reviewer_id),
            "--data-dir",
            str(tmp_path),
            "--report",
            str(report_path),
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert len(execution_calls) == 1
    assert execution_calls[0][1] is factory_sentinel
    assert execution_calls[0][2]["workspace_id"] == workspace_id
    assert execution_calls[0][2]["reviewer_user_id"] == reviewer_id
    assert report["mode"] == "execute"
    assert "Database modified: no (dry run)" not in output


@pytest.mark.parametrize(
    ("extra_args", "message"),
    [
        (["--workspace-id", "22222222-2222-4222-8222-222222222222"], "--reviewer-user-id"),
        (["--reviewer-user-id", "33333333-3333-4333-8333-333333333333"], "--workspace-id"),
        (["--workspace-id", "YOUR-WORKSPACE-UUID", "--reviewer-user-id", "33333333-3333-4333-8333-333333333333"], "--workspace-id must be a UUID"),
        (["--workspace-id", "22222222-2222-4222-8222-222222222222", "--reviewer-user-id", "YOUR-USER-UUID"], "--reviewer-user-id must be a UUID"),
    ],
)
def test_cli_execute_invalid_identity_details_fail_not_dry_run(
    tmp_path, monkeypatch, capsys, extra_args, message
):
    _write_fixture_data(tmp_path)
    report_path = tmp_path / "failed-execute-report.json"

    def unexpected_database_access():
        raise AssertionError("invalid execution details must fail before database setup")

    monkeypatch.setattr(csv_migration, "create_session_factory", unexpected_database_access)
    exit_code = csv_migration.main(
        [
            "--execute",
            *extra_args,
            "--data-dir",
            str(tmp_path),
            "--report",
            str(report_path),
        ]
    )

    output = capsys.readouterr().out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 1
    assert report["mode"] == "execute_failed"
    assert message in report["failure"]
    assert "Execution failed; database import was not completed." in output
    assert "Database modified: no (dry run)" not in output


def inspect_tables(engine):
    from sqlalchemy import inspect

    return inspect(engine).get_table_names()
