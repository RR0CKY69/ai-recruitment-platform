"""Validate and transactionally migrate the legacy recruitment CSV files."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import pandas as pd
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from ml_project.config import PROJECT_ROOT
from ml_project.database import create_session_factory
from ml_project.models import (
    Candidate,
    CandidateSkill,
    CandidateSource,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    JobRequirement,
    User,
    Workspace,
    WorkspaceMember,
)

DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "csv_migration_report.json"
JOB_COLUMNS = {"job_id", "job_title", "description", "required_skills", "min_experience", "location"}
CANDIDATE_COLUMNS = {
    "candidate_id",
    "name",
    "current_title",
    "summary",
    "skills",
    "experience_years",
    "location",
}
EVALUATION_COLUMNS = {"job_id", "candidate_id", "relevance_label", "label_review_status"}
NOTE_COLUMNS = {"job_id", "candidate_id", "reviewer_notes"}
JOB_STATUSES = {"DRAFT", "OPEN", "ON_HOLD", "CLOSED"}
REVIEW_STATUSES = {"reviewed", "needs_human_review"}


class MigrationValidationError(ValueError):
    """Raised when input data cannot be imported without dropping or changing records."""


class MigrationConflict(RuntimeError):
    """Raised when a rerun finds database records that conflict with CSV source values."""


@dataclass
class MigrationPlan:
    """Validated source rows and the dry-run report derived from them."""

    data_dir: Path
    jobs: list[dict[str, Any]]
    candidates: list[dict[str, Any]]
    evaluations: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    report: dict[str, Any]

    @property
    def has_errors(self) -> bool:
        return bool(self.report["validation"]["issues"])


def _missing(value: object) -> bool:
    if value is None or pd.isna(value):
        return True
    return isinstance(value, str) and not value.strip()


def _clean_text(value: object) -> str | None:
    if _missing(value):
        return None
    return str(value).strip()


def _parse_years(value: object, *, dataset: str, row_number: int, field: str, issues: list[dict]) -> int | None:
    if _missing(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = math.nan
    if not math.isfinite(numeric) or numeric < 0 or not numeric.is_integer():
        issues.append(
            {
                "dataset": dataset,
                "row": row_number,
                "record_id": None,
                "field": field,
                "issue": "experience must be a non-negative whole number or blank",
            }
        )
        return None
    return int(numeric)


def _label_value(value: object) -> int | None:
    if _missing(value):
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError("relevance label must be 0, 1, 2, or blank") from error
    if not math.isfinite(numeric) or not numeric.is_integer() or int(numeric) not in {0, 1, 2}:
        raise ValueError("relevance label must be 0, 1, 2, or blank")
    return int(numeric)


def _skills(value: object) -> list[str]:
    text = _clean_text(value)
    if not text:
        return []
    unique: dict[str, str] = {}
    for item in text.split(";"):
        cleaned = item.strip()
        if cleaned:
            unique.setdefault(" ".join(cleaned.casefold().split()), cleaned)
    return list(unique.values())


def _read_csv(path: Path, *, optional: bool = False) -> pd.DataFrame:
    if not path.exists() and optional:
        return pd.DataFrame(columns=sorted(NOTE_COLUMNS))
    if not path.is_file():
        raise FileNotFoundError(f"Required migration file not found: {path}")
    return pd.read_csv(path, dtype={"job_id": "string", "candidate_id": "string"})


def _missing_value_summary(frames: dict[str, pd.DataFrame]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for dataset, frame in frames.items():
        counts: dict[str, int] = {}
        for column in frame.columns:
            missing_count = sum(_missing(value) for value in frame[column].tolist())
            if missing_count:
                counts[column] = int(missing_count)
        result[dataset] = counts
    return result


def validate_csv_data(data_dir: Path = DEFAULT_DATA_DIR) -> MigrationPlan:
    """Read and validate source CSVs without opening or modifying a database."""
    data_dir = Path(data_dir)
    paths = {
        "jobs": data_dir / "jobs.csv",
        "candidates": data_dir / "candidates.csv",
        "evaluations": data_dir / "evaluation.csv",
        "notes": data_dir / "evaluation_notes.csv",
    }
    frames = {
        "jobs": _read_csv(paths["jobs"]),
        "candidates": _read_csv(paths["candidates"]),
        "evaluations": _read_csv(paths["evaluations"]),
        "notes": _read_csv(paths["notes"], optional=True),
    }
    required_by_dataset = {
        "jobs": JOB_COLUMNS,
        "candidates": CANDIDATE_COLUMNS,
        "evaluations": EVALUATION_COLUMNS,
        "notes": NOTE_COLUMNS,
    }
    issues: list[dict[str, Any]] = []
    duplicate_rows: dict[str, set[int]] = {dataset: set() for dataset in frames}
    invalid_record_keys: set[tuple[str, int]] = set()
    valid_jobs: list[dict[str, Any]] = []
    valid_candidates: list[dict[str, Any]] = []
    valid_evaluations: list[dict[str, Any]] = []
    valid_notes: list[dict[str, Any]] = []

    for dataset, required in required_by_dataset.items():
        missing_columns = required.difference(frames[dataset].columns)
        for column in sorted(missing_columns):
            issues.append(
                {
                    "dataset": dataset,
                    "row": None,
                    "record_id": None,
                    "field": column,
                    "issue": "required column is missing",
                }
            )

    normalized_rows: dict[str, list[dict[str, Any]]] = {}
    for dataset, frame in frames.items():
        normalized_rows[dataset] = []
        for offset, raw in enumerate(frame.to_dict(orient="records"), start=2):
            row = {str(key): value for key, value in raw.items()}
            normalized_rows[dataset].append(row)
            if not required_by_dataset[dataset].issubset(frame.columns):
                invalid_record_keys.add((dataset, offset))

    def add_issue(dataset: str, row_number: int, record_id: object, field: str, message: str) -> None:
        issues.append(
            {
                "dataset": dataset,
                "row": row_number,
                "record_id": _clean_text(record_id),
                "field": field,
                "issue": message,
            }
        )
        invalid_record_keys.add((dataset, row_number))

    job_rows = normalized_rows["jobs"]
    candidate_rows = normalized_rows["candidates"]
    evaluation_rows = normalized_rows["evaluations"]
    note_rows = normalized_rows["notes"]

    seen_job_ids: set[str] = set()
    valid_job_ids: set[str] = set()
    for row_number, row in enumerate(job_rows, start=2):
        legacy_id = _clean_text(row.get("job_id"))
        title = _clean_text(row.get("job_title"))
        if not legacy_id:
            add_issue("jobs", row_number, legacy_id, "job_id", "job ID is required")
        elif legacy_id in seen_job_ids:
            duplicate_rows["jobs"].add(row_number)
            add_issue("jobs", row_number, legacy_id, "job_id", "duplicate job ID")
        else:
            seen_job_ids.add(legacy_id)
        if not title:
            add_issue("jobs", row_number, legacy_id, "job_title", "job title is required")

        years = _parse_years(
            row.get("min_experience"),
            dataset="jobs",
            row_number=row_number,
            field="min_experience",
            issues=issues,
        )
        if any(issue["dataset"] == "jobs" and issue["row"] == row_number for issue in issues):
            invalid_record_keys.add(("jobs", row_number))
            continue

        raw_status = _clean_text(row.get("status"))
        status = raw_status.upper() if raw_status else "DRAFT"
        if status not in JOB_STATUSES:
            add_issue("jobs", row_number, legacy_id, "status", "unsupported job status")
            continue
        skills = _skills(row.get("required_skills"))
        valid_job_ids.add(legacy_id)
        valid_jobs.append(
            {
                "legacy_id": legacy_id,
                "title": title,
                "description": _clean_text(row.get("description")) or "",
                "required_skills": skills,
                "minimum_experience_years": years,
                "location": _clean_text(row.get("location")),
                "status": status,
                "row": row_number,
            }
        )

    seen_candidate_ids: set[str] = set()
    seen_candidate_emails: set[str] = set()
    seen_candidate_profiles: set[tuple[object, ...]] = set()
    valid_candidate_ids: set[str] = set()
    for row_number, row in enumerate(candidate_rows, start=2):
        legacy_id = _clean_text(row.get("candidate_id"))
        name = _clean_text(row.get("name"))
        if not legacy_id:
            add_issue("candidates", row_number, legacy_id, "candidate_id", "candidate ID is required")
        elif legacy_id in seen_candidate_ids:
            duplicate_rows["candidates"].add(row_number)
            add_issue("candidates", row_number, legacy_id, "candidate_id", "duplicate candidate ID")
        else:
            seen_candidate_ids.add(legacy_id)
        if not name:
            add_issue("candidates", row_number, legacy_id, "name", "candidate name is required")

        years = _parse_years(
            row.get("experience_years"),
            dataset="candidates",
            row_number=row_number,
            field="experience_years",
            issues=issues,
        )
        email = _clean_text(row.get("email"))
        if email:
            email_key = email.casefold()
            if email_key in seen_candidate_emails:
                duplicate_rows["candidates"].add(row_number)
                add_issue("candidates", row_number, legacy_id, "email", "duplicate candidate email")
            seen_candidate_emails.add(email_key)

        profile_key = (
            " ".join((name or "").casefold().split()),
            " ".join((_clean_text(row.get("current_title")) or "").casefold().split()),
            " ".join((_clean_text(row.get("summary")) or "").casefold().split()),
            tuple(sorted(_normalize_skill(skill) for skill in _skills(row.get("skills")))),
            _clean_text(row.get("experience_years")),
            " ".join((_clean_text(row.get("location")) or "").casefold().split()),
        )
        if profile_key[0] and profile_key in seen_candidate_profiles:
            duplicate_rows["candidates"].add(row_number)
            add_issue(
                "candidates",
                row_number,
                legacy_id,
                "candidate_id",
                "duplicate candidate profile content; review identity before importing",
            )
        seen_candidate_profiles.add(profile_key)

        if any(
            issue["dataset"] == "candidates" and issue["row"] == row_number for issue in issues
        ):
            invalid_record_keys.add(("candidates", row_number))
            continue
        valid_candidate_ids.add(legacy_id)
        valid_candidates.append(
            {
                "legacy_id": legacy_id,
                "name": name,
                "email": email,
                "current_title": _clean_text(row.get("current_title")),
                "summary": _clean_text(row.get("summary")) or "",
                "skills": _skills(row.get("skills")),
                "experience_years": years,
                "location": _clean_text(row.get("location")),
                "source_provider": _clean_text(row.get("source_provider"))
                or _clean_text(row.get("source"))
                or "csv_migration",
                "source_record_id": _clean_text(row.get("source_record_id")) or legacy_id,
                "source_url": _clean_text(row.get("source_url"))
                or _clean_text(row.get("profile_url")),
                "authorized_basis": _clean_text(row.get("authorized_basis")),
                "row": row_number,
            }
        )

    valid_pair_keys: set[tuple[str, str]] = set()
    reviewed_pair_keys: set[tuple[str, str]] = set()
    seen_pair_keys: set[tuple[str, str]] = set()
    for row_number, row in enumerate(evaluation_rows, start=2):
        job_id = _clean_text(row.get("job_id"))
        candidate_id = _clean_text(row.get("candidate_id"))
        status = _clean_text(row.get("label_review_status"))
        if not job_id:
            add_issue("evaluations", row_number, None, "job_id", "job ID is required")
        if not candidate_id:
            add_issue("evaluations", row_number, None, "candidate_id", "candidate ID is required")
        if job_id and job_id not in valid_job_ids:
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "job_id", "evaluation references nonexistent or invalid job")
        if candidate_id and candidate_id not in valid_candidate_ids:
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "candidate_id", "evaluation references nonexistent or invalid candidate")
        pair = (job_id or "", candidate_id or "")
        if all(pair) and pair in seen_pair_keys:
            duplicate_rows["evaluations"].add(row_number)
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "candidate_id", "duplicate evaluation pair")
        seen_pair_keys.add(pair)

        try:
            label = _label_value(row.get("relevance_label"))
        except ValueError as error:
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "relevance_label", str(error))
            continue
        if status not in REVIEW_STATUSES:
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "label_review_status", "status must be reviewed or needs_human_review")
            continue
        if label is None and status != "needs_human_review":
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "relevance_label", "reviewed evaluation is missing its label")
            continue
        if label is not None and status != "reviewed":
            add_issue("evaluations", row_number, f"{job_id}/{candidate_id}", "label_review_status", "labeled evaluation must have reviewed status")
            continue
        if job_id in valid_job_ids and candidate_id in valid_candidate_ids and pair not in valid_pair_keys:
            valid_pair_keys.add(pair)
            if label is not None:
                reviewed_pair_keys.add(pair)
            valid_evaluations.append(
                {
                    "job_id": job_id,
                    "candidate_id": candidate_id,
                    "label": label,
                    "status": status,
                    "row": row_number,
                }
            )

    seen_note_pairs: set[tuple[str, str]] = set()
    for row_number, row in enumerate(note_rows, start=2):
        job_id = _clean_text(row.get("job_id"))
        candidate_id = _clean_text(row.get("candidate_id"))
        note_text = _clean_text(row.get("reviewer_notes")) or ""
        pair = (job_id or "", candidate_id or "")
        if not job_id or job_id not in valid_job_ids:
            add_issue("notes", row_number, f"{job_id}/{candidate_id}", "job_id", "note references nonexistent or invalid job")
        if not candidate_id or candidate_id not in valid_candidate_ids:
            add_issue("notes", row_number, f"{job_id}/{candidate_id}", "candidate_id", "note references nonexistent or invalid candidate")
        if all(pair) and pair in seen_note_pairs:
            duplicate_rows["notes"].add(row_number)
            add_issue("notes", row_number, f"{job_id}/{candidate_id}", "candidate_id", "duplicate note pair")
        seen_note_pairs.add(pair)
        if note_text and pair not in reviewed_pair_keys:
            add_issue("notes", row_number, f"{job_id}/{candidate_id}", "reviewer_notes", "non-empty note has no reviewed evaluation label")
            continue
        if job_id in valid_job_ids and candidate_id in valid_candidate_ids and pair not in {
            (note["job_id"], note["candidate_id"]) for note in valid_notes
        }:
            valid_notes.append(
                {"job_id": job_id, "candidate_id": candidate_id, "note": note_text, "row": row_number}
            )

    # An evaluation pair is the source of JobCandidate relationships; notes must point to
    # one of those same pairs, including rows whose note text is blank.
    evaluation_pair_keys = {(item["job_id"], item["candidate_id"]) for item in valid_evaluations}
    for note in valid_notes:
        if (note["job_id"], note["candidate_id"]) not in evaluation_pair_keys:
            add_issue(
                "notes",
                note["row"],
                f"{note['job_id']}/{note['candidate_id']}",
                "reviewer_notes",
                "note has no evaluation row",
            )

    for dataset, rows in (
        ("jobs", valid_jobs),
        ("candidates", valid_candidates),
        ("evaluations", valid_evaluations),
        ("notes", valid_notes),
    ):
        for item in rows:
            if (dataset, item["row"]) in invalid_record_keys:
                item["_invalid"] = True

    valid_jobs = [row for row in valid_jobs if not row.get("_invalid")]
    valid_candidates = [row for row in valid_candidates if not row.get("_invalid")]
    valid_evaluations = [row for row in valid_evaluations if not row.get("_invalid")]
    valid_notes = [row for row in valid_notes if not row.get("_invalid")]

    source_hashes = {
        name: hashlib.sha256(path.read_bytes()).hexdigest()
        for name, path in paths.items()
        if path.exists()
    }
    reviewed_labels = sum(item["label"] is not None for item in valid_evaluations)
    pending_evaluations = sum(item["label"] is None for item in valid_evaluations)
    expected = {
        "workspace": "operator-selected: 0 if existing, 1 if explicitly created",
        "workspace_member": "operator-selected: 0 if membership exists, otherwise 1",
        "jobs": len(valid_jobs),
        "candidates": len(valid_candidates),
        "job_requirements": sum(len(item["required_skills"]) for item in valid_jobs),
        "candidate_skills": sum(len(item["skills"]) for item in valid_candidates),
        "candidate_sources": len(valid_candidates),
        "job_candidates": len(valid_evaluations),
        "evaluation_labels": reviewed_labels,
        "evaluation_notes": sum(bool(item["note"]) for item in valid_notes),
        "pending_evaluations_not_stored_as_labels": pending_evaluations,
    }
    invalid_counts = {
        dataset: len({row for source, row in invalid_record_keys if source == dataset})
        for dataset in frames
    }
    duplicate_counts = {dataset: len(rows) for dataset, rows in duplicate_rows.items()}
    duplicate_total = sum(duplicate_counts.values())
    report = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "dry_run",
        "data_dir": str(data_dir.resolve()),
        "source_hashes_sha256": source_hashes,
        "source_counts": {
            "jobs": len(frames["jobs"]),
            "candidates": len(frames["candidates"]),
            "evaluation_records": len(frames["evaluations"]),
            "evaluation_notes_records": len(frames["notes"]),
        },
        "validation": {
            "valid_records": {
                "jobs": len(valid_jobs),
                "candidates": len(valid_candidates),
                "evaluation_records": len(valid_evaluations),
                "evaluation_notes_records": len(valid_notes),
            },
            "invalid_record_counts": invalid_counts,
            "invalid_records_total": sum(invalid_counts.values()),
            "duplicate_record_counts": duplicate_counts,
            "duplicate_records_total": duplicate_total,
            "missing_values_by_column": _missing_value_summary(frames),
            "orphan_relationships": [
                issue for issue in issues if "nonexistent" in issue["issue"] or "no evaluation row" in issue["issue"]
            ],
            "issues": issues,
        },
        "expected_insert_counts_if_target_empty": expected,
        "target_database_inspected": False,
        "actual_import": None,
        "reconciliation": None,
    }
    return MigrationPlan(
        data_dir=data_dir,
        jobs=valid_jobs,
        candidates=valid_candidates,
        evaluations=valid_evaluations,
        notes=valid_notes,
        report=report,
    )


def _normalize_skill(skill: str) -> str:
    return " ".join(skill.casefold().split())


def _same_job(existing: Job, source: dict[str, Any]) -> bool:
    return (
        existing.title == source["title"]
        and existing.description == source["description"]
        and existing.location == source["location"]
        and existing.minimum_experience_years == source["minimum_experience_years"]
        and existing.status == source["status"]
    )


def _same_candidate(existing: Candidate, source: dict[str, Any]) -> bool:
    return (
        existing.full_name == source["name"]
        and existing.email == source["email"]
        and existing.current_title == source["current_title"]
        and existing.summary == source["summary"]
        and existing.experience_years == source["experience_years"]
        and existing.location == source["location"]
    )


def _validate_workspace_and_reviewer(
    session: Session,
    *,
    workspace_id: UUID | None,
    workspace_name: str | None,
    workspace_slug: str | None,
    workspace_member_role: str | None,
    reviewer_user_id: UUID | None,
) -> tuple[Workspace, User, bool, bool]:
    if reviewer_user_id is None:
        raise MigrationValidationError("An existing --reviewer-user-id is required to preserve labels and notes.")
    reviewer = session.get(User, reviewer_user_id)
    if reviewer is None or not reviewer.is_active:
        raise MigrationValidationError("Reviewer user must exist and be active; no user is created by this migration.")

    if workspace_id is not None:
        workspace = session.get(Workspace, workspace_id)
        if workspace is None:
            raise MigrationValidationError(f"Workspace {workspace_id} does not exist.")
        membership = session.scalar(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == reviewer.id,
            )
        )
        if membership is None:
            raise MigrationValidationError("The reviewer must already be a member of the selected workspace.")
        return workspace, reviewer, False, False

    if not workspace_name or not workspace_slug:
        raise MigrationValidationError(
            "Choose an existing --workspace-id or provide both --create-workspace-name and --create-workspace-slug."
        )
    if workspace_member_role not in {"ADMIN", "RECRUITER"}:
        raise MigrationValidationError(
            "Creating a workspace requires --workspace-member-role ADMIN or RECRUITER."
        )
    workspace = session.scalar(select(Workspace).where(Workspace.slug == workspace_slug))
    created_workspace = workspace is None
    if workspace is None:
        workspace = Workspace(
            name=workspace_name,
            slug=workspace_slug,
            created_by_id=reviewer.id,
        )
        session.add(workspace)
        session.flush()
    elif workspace.name != workspace_name:
        raise MigrationConflict("The requested workspace slug already exists with a different name.")

    membership = session.scalar(
        select(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == reviewer.id,
        )
    )
    created_membership = membership is None
    if membership is None:
        session.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=reviewer.id,
                role=workspace_member_role,
            )
        )
        session.flush()
    elif membership.role != workspace_member_role:
        raise MigrationConflict("Existing workspace member role differs from the requested role.")
    return workspace, reviewer, created_workspace, created_membership


def _reconcile(
    session: Session,
    plan: MigrationPlan,
    workspace: Workspace,
    reviewer: User,
) -> dict[str, Any]:
    jobs = session.scalars(select(Job).where(Job.workspace_id == workspace.id)).all()
    candidates = session.scalars(select(Candidate).where(Candidate.workspace_id == workspace.id)).all()
    jobs_by_legacy = {job.legacy_job_id: job for job in jobs if job.legacy_job_id}
    candidates_by_legacy = {
        candidate.legacy_candidate_id: candidate
        for candidate in candidates
        if candidate.legacy_candidate_id
    }
    source_job_ids = {row["legacy_id"] for row in plan.jobs}
    source_candidate_ids = {row["legacy_id"] for row in plan.candidates}
    job_map = {key: jobs_by_legacy[key].id for key in source_job_ids if key in jobs_by_legacy}
    candidate_map = {
        key: candidates_by_legacy[key].id
        for key in source_candidate_ids
        if key in candidates_by_legacy
    }

    associations = session.scalars(
        select(JobCandidate).where(JobCandidate.workspace_id == workspace.id)
    ).all()
    pairs_by_legacy: dict[tuple[str, str], JobCandidate] = {}
    relationship_mismatches: list[dict[str, str]] = []
    for association in associations:
        job = jobs_by_legacy.get(association.job.legacy_job_id)
        candidate = candidates_by_legacy.get(association.candidate.legacy_candidate_id)
        if job is None or candidate is None:
            continue
        pair = (job.legacy_job_id, candidate.legacy_candidate_id)
        pairs_by_legacy[pair] = association
        if association.job_id != job_map.get(pair[0]) or association.candidate_id != candidate_map.get(pair[1]):
            relationship_mismatches.append(
                {"job_id": pair[0], "candidate_id": pair[1], "issue": "association UUID mapping mismatch"}
            )

    source_pairs = {(item["job_id"], item["candidate_id"]) for item in plan.evaluations}
    matched_associations = {pair: pairs_by_legacy[pair] for pair in source_pairs if pair in pairs_by_legacy}
    if len(matched_associations) != len(source_pairs):
        missing_pairs = sorted(source_pairs.difference(matched_associations))
        relationship_mismatches.extend(
            {"job_id": job_id, "candidate_id": candidate_id, "issue": "missing association"}
            for job_id, candidate_id in missing_pairs
        )

    reviewed_pairs = {
        (row["job_id"], row["candidate_id"])
        for row in plan.evaluations
        if row["label"] is not None
    }
    label_count = 0
    labeled_pairs_in_database: set[tuple[str, str]] = set()
    for pair in reviewed_pairs.intersection(matched_associations):
        association = matched_associations[pair]
        label = session.scalar(
            select(EvaluationLabel).where(
                EvaluationLabel.job_candidate_id == association.id,
                EvaluationLabel.reviewer_id == reviewer.id,
            )
        )
        if label:
            label_count += 1
            labeled_pairs_in_database.add(pair)

    note_rows = [item for item in plan.notes if item["note"]]
    notes_count = 0
    for item in note_rows:
        association = matched_associations.get((item["job_id"], item["candidate_id"]))
        if association is None:
            continue
        label = session.scalar(
            select(EvaluationLabel).where(
                EvaluationLabel.job_candidate_id == association.id,
                EvaluationLabel.reviewer_id == reviewer.id,
            )
        )
        if label is None:
            continue
        matching_note = session.scalar(
            select(EvaluationNote.id).where(
                EvaluationNote.evaluation_label_id == label.id,
                EvaluationNote.author_id == reviewer.id,
                EvaluationNote.note == item["note"],
            )
        )
        if matching_note:
            notes_count += 1

    pending = sum(item["label"] is None for item in plan.evaluations)
    pending_pairs_in_database = sum(
        item["label"] is None
        and (item["job_id"], item["candidate_id"]) in matched_associations
        and (item["job_id"], item["candidate_id"]) not in labeled_pairs_in_database
        for item in plan.evaluations
    )
    source_note_count = sum(bool(item["note"]) for item in plan.notes)
    result = {
        "workspace_id": str(workspace.id),
        "jobs": {
            "source_valid": len(plan.jobs),
            "database_mapped": len(job_map),
            "workspace_total": len(jobs),
            "matches": len(job_map) == len(plan.jobs),
        },
        "candidates": {
            "source_valid": len(plan.candidates),
            "database_mapped": len(candidate_map),
            "workspace_total": len(candidates),
            "matches": len(candidate_map) == len(plan.candidates),
        },
        "job_candidates": {
            "source_valid": len(plan.evaluations),
            "database_mapped": len(matched_associations),
            "matches": len(matched_associations) == len(plan.evaluations),
            "relationship_mismatches": relationship_mismatches,
        },
        "evaluation_labels": {
            "source_reviewed": sum(item["label"] is not None for item in plan.evaluations),
            "database_for_reviewer": label_count,
            "matches": label_count == sum(item["label"] is not None for item in plan.evaluations),
        },
        "reviewer_notes": {
            "source_nonempty": source_note_count,
            "database_matching_notes": notes_count,
            "matches": notes_count == source_note_count,
        },
        "pending_evaluations": {
            "source_pending": pending,
            "database_pending_pairs": pending_pairs_in_database,
            "matches": pending_pairs_in_database == pending,
            "note": "Pending pairs are represented by JobCandidate links with no EvaluationLabel; none are fabricated.",
        },
    }
    result["all_checks_passed"] = all(
        result[key]["matches"]
        for key in ("jobs", "candidates", "job_candidates", "evaluation_labels", "reviewer_notes")
    ) and not relationship_mismatches
    result["all_checks_passed"] = result["all_checks_passed"] and result[
        "pending_evaluations"
    ]["matches"]
    return result


def execute_migration(
    plan: MigrationPlan,
    session_factory: sessionmaker[Session],
    *,
    workspace_id: UUID | None = None,
    workspace_name: str | None = None,
    workspace_slug: str | None = None,
    workspace_member_role: str | None = None,
    reviewer_user_id: UUID | None = None,
) -> dict[str, Any]:
    """Import all valid CSV data in one transaction; conflicting records roll back."""
    if plan.has_errors:
        raise MigrationValidationError(
            f"Import refused: source contains {plan.report['validation']['invalid_records_total']} invalid records."
        )
    if reviewer_user_id is None:
        raise MigrationValidationError("An existing reviewer user UUID must be explicitly provided.")

    inserted = {
        "workspace": 0,
        "workspace_member": 0,
        "jobs": 0,
        "candidates": 0,
        "job_requirements": 0,
        "candidate_skills": 0,
        "candidate_sources": 0,
        "job_candidates": 0,
        "evaluation_labels": 0,
        "evaluation_notes": 0,
    }
    skipped = {key: 0 for key in inserted}
    job_id_map: dict[str, UUID] = {}
    candidate_id_map: dict[str, UUID] = {}
    pair_map: dict[tuple[str, str], UUID] = {}

    with session_factory.begin() as session:
        workspace, reviewer, workspace_created, membership_created = _validate_workspace_and_reviewer(
            session,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            workspace_slug=workspace_slug,
            workspace_member_role=workspace_member_role,
            reviewer_user_id=reviewer_user_id,
        )
        inserted["workspace"] = int(workspace_created)
        inserted["workspace_member"] = int(membership_created)

        for source in plan.jobs:
            existing = session.scalar(
                select(Job).where(
                    Job.workspace_id == workspace.id,
                    Job.legacy_job_id == source["legacy_id"],
                )
            )
            if existing:
                if not _same_job(existing, source):
                    raise MigrationConflict(f"Existing job {source['legacy_id']} differs from CSV; no overwrite performed.")
                job = existing
                skipped["jobs"] += 1
            else:
                job = Job(
                    workspace_id=workspace.id,
                    created_by_id=reviewer.id,
                    legacy_job_id=source["legacy_id"],
                    title=source["title"],
                    description=source["description"],
                    location=source["location"],
                    minimum_experience_years=source["minimum_experience_years"],
                    status=source["status"],
                )
                session.add(job)
                session.flush()
                inserted["jobs"] += 1
            job_id_map[source["legacy_id"]] = job.id

            existing_requirements = {
                _normalize_skill(requirement.normalized_value or requirement.description)
                for requirement in session.scalars(
                    select(JobRequirement).where(JobRequirement.job_id == job.id)
                ).all()
            }
            for skill in source["required_skills"]:
                normalized = _normalize_skill(skill)
                if normalized in existing_requirements:
                    skipped["job_requirements"] += 1
                    continue
                session.add(
                    JobRequirement(
                        job_id=job.id,
                        requirement_type="REQUIRED_SKILL",
                        description=skill,
                        normalized_value=normalized,
                    )
                )
                existing_requirements.add(normalized)
                inserted["job_requirements"] += 1

        for source in plan.candidates:
            existing = session.scalar(
                select(Candidate).where(
                    Candidate.workspace_id == workspace.id,
                    Candidate.legacy_candidate_id == source["legacy_id"],
                )
            )
            if existing is None and source["email"]:
                email_match = session.scalar(
                    select(Candidate).where(
                        Candidate.workspace_id == workspace.id,
                        func.lower(Candidate.email) == source["email"].casefold(),
                    )
                )
                if email_match is not None:
                    raise MigrationConflict(
                        f"Candidate {source['legacy_id']} email already belongs to legacy candidate "
                        f"{email_match.legacy_candidate_id!r}; resolve identity before importing."
                    )
            if existing:
                if not _same_candidate(existing, source):
                    raise MigrationConflict(
                        f"Existing candidate {source['legacy_id']} differs from CSV; no overwrite performed."
                    )
                candidate = existing
                skipped["candidates"] += 1
            else:
                candidate = Candidate(
                    workspace_id=workspace.id,
                    created_by_id=reviewer.id,
                    legacy_candidate_id=source["legacy_id"],
                    full_name=source["name"],
                    email=source["email"],
                    current_title=source["current_title"],
                    summary=source["summary"],
                    experience_years=source["experience_years"],
                    location=source["location"],
                )
                session.add(candidate)
                session.flush()
                inserted["candidates"] += 1
            candidate_id_map[source["legacy_id"]] = candidate.id

            existing_skills = {
                skill.normalized_name
                for skill in session.scalars(
                    select(CandidateSkill).where(CandidateSkill.candidate_id == candidate.id)
                ).all()
            }
            for skill in source["skills"]:
                normalized = _normalize_skill(skill)
                if normalized in existing_skills:
                    skipped["candidate_skills"] += 1
                    continue
                session.add(
                    CandidateSkill(
                        candidate_id=candidate.id,
                        name=skill,
                        normalized_name=normalized,
                    )
                )
                existing_skills.add(normalized)
                inserted["candidate_skills"] += 1

            source_record = session.scalar(
                select(CandidateSource).where(
                    CandidateSource.candidate_id == candidate.id,
                    CandidateSource.provider == source["source_provider"],
                    CandidateSource.source_record_id == source["source_record_id"],
                )
            )
            if source_record:
                skipped["candidate_sources"] += 1
            else:
                session.add(
                    CandidateSource(
                        candidate_id=candidate.id,
                        provider=source["source_provider"],
                        source_record_id=source["source_record_id"],
                        source_url=source["source_url"],
                        authorized_basis=source["authorized_basis"],
                        source_metadata={
                            "source_file": "candidates.csv",
                            "legacy_candidate_id": source["legacy_id"],
                            "source_provider_from_csv": source["source_provider"] != "csv_migration",
                        },
                    )
                )
                inserted["candidate_sources"] += 1

        for evaluation in plan.evaluations:
            job_id = job_id_map[evaluation["job_id"]]
            candidate_id = candidate_id_map[evaluation["candidate_id"]]
            association = session.scalar(
                select(JobCandidate).where(
                    JobCandidate.workspace_id == workspace.id,
                    JobCandidate.job_id == job_id,
                    JobCandidate.candidate_id == candidate_id,
                )
            )
            if association:
                skipped["job_candidates"] += 1
            else:
                association = JobCandidate(
                    workspace_id=workspace.id,
                    job_id=job_id,
                    candidate_id=candidate_id,
                    created_by_id=reviewer.id,
                )
                session.add(association)
                session.flush()
                inserted["job_candidates"] += 1
            pair_map[(evaluation["job_id"], evaluation["candidate_id"])] = association.id

            label_value = evaluation["label"]
            if label_value is None:
                continue
            existing_label = session.scalar(
                select(EvaluationLabel).where(
                    EvaluationLabel.job_candidate_id == association.id,
                    EvaluationLabel.reviewer_id == reviewer.id,
                )
            )
            if existing_label:
                if existing_label.relevance_label != label_value:
                    raise MigrationConflict(
                        f"Existing human label conflicts with CSV for {evaluation['job_id']}/{evaluation['candidate_id']}; it was not overwritten."
                    )
                skipped["evaluation_labels"] += 1
            else:
                existing_label = EvaluationLabel(
                    job_candidate_id=association.id,
                    reviewer_id=reviewer.id,
                    relevance_label=label_value,
                    review_status="REVIEWED",
                )
                session.add(existing_label)
                session.flush()
                inserted["evaluation_labels"] += 1

        for note_source in plan.notes:
            if not note_source["note"]:
                continue
            association_id = pair_map.get((note_source["job_id"], note_source["candidate_id"]))
            if association_id is None:
                raise MigrationValidationError("Reviewer note does not have an imported job-candidate pair.")
            label = session.scalar(
                select(EvaluationLabel).where(
                    EvaluationLabel.job_candidate_id == association_id,
                    EvaluationLabel.reviewer_id == reviewer.id,
                )
            )
            if label is None:
                raise MigrationValidationError("Non-empty reviewer note has no reviewed evaluation label.")
            existing_note = session.scalar(
                select(EvaluationNote).where(
                    EvaluationNote.evaluation_label_id == label.id,
                    EvaluationNote.author_id == reviewer.id,
                    EvaluationNote.note == note_source["note"],
                )
            )
            if existing_note:
                skipped["evaluation_notes"] += 1
            else:
                session.add(
                    EvaluationNote(
                        evaluation_label_id=label.id,
                        author_id=reviewer.id,
                        note=note_source["note"],
                    )
                )
                inserted["evaluation_notes"] += 1

        session.flush()
        reconciliation = _reconcile(session, plan, workspace, reviewer)
        if not reconciliation["all_checks_passed"]:
            raise MigrationConflict("Post-import reconciliation failed; transaction rolled back.")
        result = {
            "workspace_id": str(workspace.id),
            "reviewer_user_id": str(reviewer.id),
            "inserted": inserted,
            "skipped_idempotent": skipped,
            "legacy_job_id_to_uuid": {key: str(value) for key, value in job_id_map.items()},
            "legacy_candidate_id_to_uuid": {
                key: str(value) for key, value in candidate_id_map.items()
            },
            "job_candidate_pair_to_uuid": {
                f"{job_id}/{candidate_id}": str(value)
                for (job_id, candidate_id), value in pair_map.items()
            },
            "reconciliation": reconciliation,
        }

    plan.report["mode"] = "execute"
    plan.report["actual_import"] = result
    plan.report["reconciliation"] = reconciliation
    return plan.report


def write_report(report: dict[str, Any], report_path: Path = DEFAULT_REPORT) -> None:
    """Write a JSON migration report without modifying any source CSV."""
    report_path = Path(report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(report: dict[str, Any]) -> None:
    """Print an operator-readable migration summary."""
    counts = report["source_counts"]
    validation = report["validation"]
    print("CSV migration summary")
    print(f"  Jobs: {counts['jobs']}")
    print(f"  Candidates: {counts['candidates']}")
    print(f"  Evaluation records: {counts['evaluation_records']}")
    print(f"  Evaluation notes rows: {counts['evaluation_notes_records']}")
    print(f"  Invalid records: {validation['invalid_records_total']}")
    print(f"  Duplicate records: {validation['duplicate_records_total']}")
    print(f"  Orphan relationships: {len(validation['orphan_relationships'])}")
    if report.get("actual_import"):
        print(f"  Workspace: {report['actual_import']['workspace_id']}")
        print(f"  Reconciliation passed: {report['reconciliation']['all_checks_passed']}")
    elif report.get("mode") == "execute_failed":
        print("  Execution failed; database import was not completed.")
        print(f"  Failure: {report.get('failure', 'unknown error')}")
    else:
        print("  Database modified: no (dry run)")
        print(f"  Expected inserts if target is empty: {report['expected_insert_counts_if_target_empty']}")
    print(f"  Report: {report.get('report_path', DEFAULT_REPORT)}")


def _parse_uuid(value: str | None, option: str) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(value)
    except ValueError as error:
        raise MigrationValidationError(f"{option} must be a UUID") from error


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safely migrate recruitment CSV data to PostgreSQL.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate CSVs and write a report; never connects to or writes a database")
    mode.add_argument("--execute", action="store_true", help="perform the transactional import")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--workspace-id", help="existing workspace UUID")
    parser.add_argument("--create-workspace-name", help="explicitly create or reuse this workspace name")
    parser.add_argument("--create-workspace-slug", help="explicitly create or reuse this workspace slug")
    parser.add_argument(
        "--workspace-member-role", choices=["ADMIN", "RECRUITER"],
        help="required when creating a workspace; assigned to the specified existing reviewer user",
    )
    parser.add_argument("--reviewer-user-id", help="existing active user UUID for human labels and notes")
    args = parser.parse_args(argv)

    try:
        plan = validate_csv_data(args.data_dir)
        report = plan.report
        if args.execute:
            workspace_id = _parse_uuid(args.workspace_id, "--workspace-id")
            reviewer_id = _parse_uuid(args.reviewer_user_id, "--reviewer-user-id")
            if reviewer_id is None:
                raise MigrationValidationError(
                    "Execution requires an existing --reviewer-user-id UUID."
                )
            creating = args.create_workspace_name is not None or args.create_workspace_slug is not None
            if workspace_id and creating:
                raise MigrationValidationError("Use either --workspace-id or workspace creation options, not both.")
            if creating and not (args.create_workspace_name and args.create_workspace_slug):
                raise MigrationValidationError("Both workspace creation name and slug are required.")
            if not workspace_id and not creating:
                raise MigrationValidationError("Execution requires --workspace-id or explicit workspace creation options.")
            if creating and args.workspace_member_role is None:
                raise MigrationValidationError(
                    "Workspace creation requires --workspace-member-role ADMIN or RECRUITER."
                )
            if plan.has_errors:
                raise MigrationValidationError(
                    f"Import refused: {report['validation']['invalid_records_total']} invalid records found. Review the report and source rows."
                )
            factory = create_session_factory()
            report = execute_migration(
                plan,
                factory,
                workspace_id=workspace_id,
                workspace_name=args.create_workspace_name,
                workspace_slug=args.create_workspace_slug,
                workspace_member_role=args.workspace_member_role,
                reviewer_user_id=reviewer_id,
            )
        report["report_path"] = str(args.report.resolve())
        write_report(report, args.report)
        print_summary(report)
        return 2 if plan.has_errors else 0
    except (OSError, ValueError, RuntimeError, SQLAlchemyError, pd.errors.ParserError) as error:
        failure_report = locals().get("report")
        if isinstance(failure_report, dict):
            failure_report["mode"] = "execute_failed" if args.execute else "dry_run_failed"
            failure_report["failure"] = f"{type(error).__name__}: {error}"
            failure_report["report_path"] = str(args.report.resolve())
            write_report(failure_report, args.report)
            print_summary(failure_report)
        else:
            print(f"CSV migration failed: {type(error).__name__}: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
