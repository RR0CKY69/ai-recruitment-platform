"""SQLAlchemy ORM models."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


def uuid4():
    return uuid.uuid4()


class User(TimestampMixin, Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    memberships: Mapped[list["WorkspaceMember"]] = relationship(back_populates="user")
    refresh_sessions: Mapped[list["RefreshSession"]] = relationship(back_populates="user")


class Workspace(TimestampMixin, Base):
    __tablename__ = "workspaces"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    members: Mapped[list["WorkspaceMember"]] = relationship(back_populates="workspace")
    jobs: Mapped[list["Job"]] = relationship(back_populates="workspace")
    candidates: Mapped[list["Candidate"]] = relationship(back_populates="workspace")
    job_candidates: Mapped[list["JobCandidate"]] = relationship(back_populates="workspace")


class WorkspaceMember(TimestampMixin, Base):
    __tablename__ = "workspace_members"
    __table_args__ = (
        CheckConstraint("role IN ('ADMIN', 'RECRUITER')", name="ck_workspace_members_role_valid"),
        UniqueConstraint("workspace_id", "user_id", name="uq_workspace_members_workspace_user"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    workspace: Mapped[Workspace] = relationship(back_populates="members")
    user: Mapped[User] = relationship(back_populates="memberships")


class Job(TimestampMixin, Base):
    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT', 'OPEN', 'ON_HOLD', 'CLOSED')",
            name="ck_jobs_status_valid",
        ),
        UniqueConstraint("workspace_id", "id", name="uq_jobs_workspace_id_id"),
        Index("ix_jobs_workspace_id", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legacy_job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    title: Mapped[str] = mapped_column(String(250), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    employment_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    location: Mapped[str | None] = mapped_column(String(250), nullable=True)
    minimum_experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="OPEN")
    workspace: Mapped[Workspace] = relationship(back_populates="jobs")
    requirements: Mapped[list["JobRequirement"]] = relationship(back_populates="job")
    job_candidates: Mapped[list["JobCandidate"]] = relationship(
        back_populates="job",
        foreign_keys="JobCandidate.job_id",
    )


class JobRequirement(TimestampMixin, Base):
    __tablename__ = "job_requirements"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    requirement_type: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    normalized_value: Mapped[str | None] = mapped_column(String(300), nullable=True)
    job: Mapped[Job] = relationship(back_populates="requirements")


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "email", name="uq_candidates_workspace_email"),
        UniqueConstraint("workspace_id", "id", name="uq_candidates_workspace_id_id"),
        Index(
            "uq_candidates_workspace_email_ci",
            "workspace_id",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
            sqlite_where=text("email IS NOT NULL"),
        ),
        Index("ix_candidates_workspace_id", "workspace_id"),
        Index("ix_candidates_workspace_name", "workspace_id", "full_name"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    legacy_candidate_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    current_title: Mapped[str | None] = mapped_column(String(250), nullable=True)
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    experience_years: Mapped[int | None] = mapped_column(Integer, nullable=True)
    location: Mapped[str | None] = mapped_column(String(250), nullable=True)
    workspace: Mapped[Workspace] = relationship(back_populates="candidates")
    skills: Mapped[list["CandidateSkill"]] = relationship(back_populates="candidate")
    sources: Mapped[list["CandidateSource"]] = relationship(back_populates="candidate")
    job_candidates: Mapped[list["JobCandidate"]] = relationship(
        back_populates="candidate",
        foreign_keys="JobCandidate.candidate_id",
    )


class CandidateSkill(TimestampMixin, Base):
    __tablename__ = "candidate_skills"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False)
    years_experience: Mapped[int | None] = mapped_column(Integer, nullable=True)
    candidate: Mapped[Candidate] = relationship(back_populates="skills")


class CandidateSource(TimestampMixin, Base):
    __tablename__ = "candidate_sources"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), nullable=False)
    provider: Mapped[str] = mapped_column(String(150), nullable=False)
    source_record_id: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_basis: Mapped[str | None] = mapped_column(String(300), nullable=True)
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    candidate: Mapped[Candidate] = relationship(back_populates="sources")


class SearchQuery(TimestampMixin, Base):
    __tablename__ = "search_queries"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    query_type: Mapped[str] = mapped_column(String(20), nullable=False, default="BOOLEAN")


class SourcingTask(TimestampMixin, Base):
    __tablename__ = "sourcing_tasks"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    source_provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="PENDING")
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class JobCandidate(TimestampMixin, Base):
    __tablename__ = "job_candidates"
    __table_args__ = (
        CheckConstraint(
            "stage IN ('SOURCED', 'REVIEWING', 'SHORTLISTED', 'REJECTED', 'HIRED')",
            name="ck_job_candidates_stage_valid",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "candidate_id"],
            ["candidates.workspace_id", "candidates.id"],
            name="fk_job_candidates_workspace_candidate",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workspace_id", "job_id"],
            ["jobs.workspace_id", "jobs.id"],
            name="fk_job_candidates_workspace_job",
            ondelete="CASCADE",
        ),
        UniqueConstraint("job_id", "candidate_id", name="uq_job_candidates_job_candidate"),
        Index("ix_job_candidates_workspace_id", "workspace_id"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    job_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    candidate_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="SOURCED")
    workspace: Mapped[Workspace] = relationship(back_populates="job_candidates", foreign_keys=[workspace_id])
    job: Mapped[Job] = relationship(
        back_populates="job_candidates",
        foreign_keys=[job_id],
    )
    candidate: Mapped[Candidate] = relationship(
        back_populates="job_candidates",
        foreign_keys=[candidate_id],
    )
    match_results: Mapped[list["MatchResult"]] = relationship(back_populates="job_candidate")
    shortlist_entries: Mapped[list["Shortlist"]] = relationship(back_populates="job_candidate")
    evaluation_labels: Mapped[list["EvaluationLabel"]] = relationship(back_populates="job_candidate")


class MatchResult(TimestampMixin, Base):
    __tablename__ = "match_results"
    __table_args__ = (UniqueConstraint("job_candidate_id", "model_name", "model_version", name="uq_match_results_model_version"),)
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    tfidf_similarity: Mapped[float | None] = mapped_column(nullable=True)
    skill_coverage: Mapped[float | None] = mapped_column(nullable=True)
    experience_compatibility: Mapped[str | None] = mapped_column(String(40), nullable=True)
    location_compatibility: Mapped[str | None] = mapped_column(String(40), nullable=True)
    semantic_similarity: Mapped[float | None] = mapped_column(nullable=True)
    hybrid_score: Mapped[float | None] = mapped_column(nullable=True)
    explanation: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    job_candidate: Mapped[JobCandidate] = relationship(back_populates="match_results")


class Shortlist(TimestampMixin, Base):
    __tablename__ = "shortlists"
    __table_args__ = (
        CheckConstraint("status IN ('ACTIVE', 'REMOVED', 'HIRED')", name="ck_shortlists_status_valid"),
        UniqueConstraint("job_candidate_id", name="uq_shortlists_job_candidate"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False)
    added_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="ACTIVE")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_candidate: Mapped[JobCandidate] = relationship(back_populates="shortlist_entries")


class EvaluationLabel(TimestampMixin, Base):
    __tablename__ = "evaluation_labels"
    __table_args__ = (
        CheckConstraint("relevance_label IN (0, 1, 2)", name="ck_evaluation_labels_label_valid"),
        UniqueConstraint(
            "job_candidate_id",
            "reviewer_id",
            name="uq_evaluation_labels_pair_reviewer",
        ),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_candidate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("job_candidates.id", ondelete="CASCADE"), nullable=False)
    reviewer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    relevance_label: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, default="needs_human_review")
    job_candidate: Mapped[JobCandidate] = relationship(back_populates="evaluation_labels")
    notes: Mapped[list["EvaluationNote"]] = relationship(back_populates="evaluation_label")


class EvaluationNote(TimestampMixin, Base):
    __tablename__ = "evaluation_notes"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    evaluation_label_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("evaluation_labels.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation_label: Mapped[EvaluationLabel] = relationship(back_populates="notes")


class AuditLog(TimestampMixin, Base):
    __tablename__ = "audit_logs"
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class RefreshSession(TimestampMixin, Base):
    __tablename__ = "refresh_sessions"
    __table_args__ = (
        Index("ix_refresh_sessions_user_id", "user_id"),
        Index("ix_refresh_sessions_family_id", "family_id"),
        Index("ix_refresh_sessions_expires_at", "expires_at"),
        Index("ix_refresh_sessions_token_hash", "token_hash"),
    )
    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    family_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    user: Mapped[User] = relationship(back_populates="refresh_sessions")