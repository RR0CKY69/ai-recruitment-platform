"""Request and response schemas for authentication endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


class RegisterRequest(BaseModel):
    """User registration details; password is a plaintext string from the client."""

    model_config = ConfigDict(extra="forbid")

    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=8, max_length=1024)
    workspace_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("full_name")
    @classmethod
    def non_blank_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("workspace_name")
    @classmethod
    def non_blank_workspace_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped


class LoginRequest(BaseModel):
    """Login credentials; SecretStr avoids plaintext in model representations."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=1024)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class CurrentUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool


class WorkspaceMembershipResponse(BaseModel):
    """Workspace details limited to the authenticated user's membership."""

    workspace_id: UUID
    name: str
    slug: str
    role: Literal["ADMIN", "RECRUITER"]



class WorkspaceDetailResponse(BaseModel):
    """Workspace details and the authenticated user's role."""

    workspace_id: UUID
    name: str
    slug: str
    role: Literal["ADMIN", "RECRUITER"]


class WorkspaceMemberResponse(BaseModel):
    """Public details for one workspace member."""

    membership_id: UUID
    user_id: UUID
    full_name: str
    email: str
    role: Literal["ADMIN", "RECRUITER"]
    created_at: datetime


class AddWorkspaceMemberRequest(BaseModel):
    """Add an existing registered user to a workspace."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)
    role: Literal["ADMIN", "RECRUITER"] = "RECRUITER"

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized


class UpdateWorkspaceMemberRoleRequest(BaseModel):
    """Change an existing member's workspace role."""

    model_config = ConfigDict(extra="forbid")

    role: Literal["ADMIN", "RECRUITER"]


class UpdateWorkspaceRequest(BaseModel):
    """Update workspace settings."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)

    @field_validator("name")
    @classmethod
    def non_blank_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Workspace name cannot be blank.")
        return stripped

class JobResponse(BaseModel):
    """Workspace-visible job fields, excluding internal creator and audit data."""

    id: UUID
    workspace_id: UUID
    legacy_job_id: str | None
    title: str
    description: str
    required_skills: list[str]
    minimum_experience_years: int | None
    location: str | None
    employment_type: str | None
    status: str
    candidate_count: int


class JobRequest(BaseModel):
    """Fields for creating or updating one workspace job."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    title: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1)
    required_skills: list[str] = Field(default_factory=list)
    employment_type: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=250)
    minimum_experience_years: int | None = Field(default=None, ge=0)
    status: Literal["DRAFT", "OPEN", "ON_HOLD", "CLOSED"] = "OPEN"

    @field_validator("title", "description")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("employment_type", "location", mode="before")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value

    @field_validator("required_skills")
    @classmethod
    def normalize_and_dedup_skills(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for skill in value:
            cleaned = skill.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(cleaned)
        return normalized


class CandidateSkillResponse(BaseModel):
    """Candidate skill details suitable for workspace members."""

    name: str
    normalized_name: str
    years_experience: int | None


class CandidateSourceResponse(BaseModel):
    """Allowlisted source details; internal source metadata is omitted."""

    provider: str
    source_record_id: str | None
    source_url: str | None
    authorized_basis: str | None


class CandidateResponse(BaseModel):
    """Workspace-visible candidate profile, excluding internal fields."""

    id: UUID
    workspace_id: UUID
    legacy_candidate_id: str | None
    full_name: str
    email: str | None
    current_title: str | None
    summary: str
    skills: list[CandidateSkillResponse]
    sources: list[CandidateSourceResponse]
    experience_years: int | None
    location: str | None


class CandidateMatchingSummaryResponse(BaseModel):
    """Stored matching values available for one existing candidate/job association."""

    model_name: str
    model_version: str
    tfidf_similarity: float | None
    skill_coverage: float | None
    experience_compatibility: str | None
    location_compatibility: str | None
    hybrid_score: float | None
    updated_at: datetime


class CandidateAssociatedJobResponse(BaseModel):
    """Workspace job association and any stored matching snapshots."""

    job_id: UUID
    title: str
    status: str
    stage: str
    matching_results: list[CandidateMatchingSummaryResponse]


class CandidateDetailResponse(CandidateResponse):
    """Candidate profile plus workspace-scoped job associations."""

    associated_jobs: list[CandidateAssociatedJobResponse]


class CandidateSourceInput(BaseModel):
    """Source details provided when creating or updating one candidate profile."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1, max_length=150)
    source_record_id: str | None = Field(default=None, max_length=300)
    source_url: str | None = Field(default=None, max_length=2048)
    authorized_basis: str | None = Field(default=None, max_length=300)

    @field_validator("provider", "authorized_basis")
    @classmethod
    def non_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("source_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if not re.fullmatch(r"https?://[^\s]+", stripped):
            raise ValueError("Enter a valid source URL.")
        return stripped


class CandidateRequest(BaseModel):
    """Fields for creating or updating one workspace candidate profile."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    full_name: str = Field(min_length=1, max_length=200)
    email: str = Field(min_length=1, max_length=320)
    current_title: str | None = Field(default=None, max_length=250)
    summary: str = Field(min_length=1)
    experience_years: int | None = Field(default=None, ge=0)
    location: str | None = Field(default=None, max_length=250)
    skills: list[str] = Field(default_factory=list)
    sources: list[CandidateSourceInput] = Field(default_factory=list)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
            raise ValueError("Enter a valid email address.")
        return normalized

    @field_validator("full_name")
    @classmethod
    def non_blank_full_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("summary")
    @classmethod
    def non_blank_summary(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Field cannot be blank.")
        return stripped

    @field_validator("current_title", "location", mode="before")
    @classmethod
    def empty_to_none(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        return value.strip() if isinstance(value, str) else value

    @field_validator("skills")
    @classmethod
    def normalize_and_dedup_skills(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for skill in value:
            cleaned = skill.strip()
            if not cleaned:
                continue
            key = cleaned.casefold()
            if key not in seen:
                seen.add(key)
                normalized.append(cleaned)
        return normalized


class CandidateProfileResponse(BaseModel):
    """Candidate profile returned by create and update endpoints; includes email."""

    id: UUID
    workspace_id: UUID
    legacy_candidate_id: str | None
    full_name: str
    email: str | None
    current_title: str | None
    summary: str
    skills: list[CandidateSkillResponse]
    sources: list[CandidateSourceResponse]
    experience_years: int | None
    location: str | None


class ResumeCandidateDraft(BaseModel):
    """Parsed resume draft for user review before saving a candidate profile."""

    model_config = ConfigDict(extra="forbid")

    full_name: str | None = None
    email: str | None = None
    current_title: str | None = None
    summary: str | None = None
    experience_years: int | None = None
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    sources: list[CandidateSourceInput] = Field(default_factory=list)


class ResumeUploadResponse(BaseModel):
    """Response for resume upload; parsed_candidate may be null when nothing useful is extracted."""

    parsed_candidate: ResumeCandidateDraft | None


class AssignCandidateRequest(BaseModel):
    """IDs needed to assign one workspace candidate to one workspace job."""

    model_config = ConfigDict(extra="forbid")

    workspace_id: UUID
    candidate_id: UUID


class JobCandidateAssignmentResponse(BaseModel):
    """Assigned candidate card returned by job-candidate assignment endpoints."""

    candidate_id: UUID
    workspace_id: UUID
    full_name: str
    email: str | None
    current_title: str | None
    summary: str
    experience_years: int | None
    location: str | None
    skills: list[CandidateSkillResponse]
    sources: list[CandidateSourceResponse]
    stage: str


class UpdateJobCandidateStageRequest(BaseModel):
    """Stage update for one existing job-candidate assignment in a workspace."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal["SOURCED", "REVIEWING", "SHORTLISTED", "REJECTED", "HIRED"]


class ShortlistCreateRequest(BaseModel):
    """IDs needed to shortlist one job-candidate pair in a workspace."""

    workspace_id: UUID
    job_id: UUID
    candidate_id: UUID


class ShortlistResponse(BaseModel):
    """Public shortlist and profile fields; excludes internal ORM data."""

    shortlist_id: UUID
    workspace_id: UUID
    job_id: UUID
    job_title: str
    candidate_id: UUID
    candidate_name: str
    current_title: str | None
    experience_years: int | None
    candidate_location: str | None
    shortlisted_at: datetime
    recruiter_id: UUID | None
    recruiter_name: str | None
    status: Literal["ACTIVE"]


class EvaluationNoteResponse(BaseModel):
    """A reviewer-authored note attached to one evaluation label."""

    note_id: UUID
    author_id: UUID
    author_name: str | None
    note: str


class EvaluationResponse(BaseModel):
    """Workspace evaluation entry; a missing label represents an unreviewed pair."""

    evaluation_id: UUID | None
    workspace_id: UUID
    job_id: UUID
    legacy_job_id: str | None
    job_title: str
    candidate_id: UUID
    legacy_candidate_id: str | None
    candidate_name: str
    current_title: str | None
    relevance_label: int | None
    review_status: Literal["reviewed", "needs_human_review"]
    reviewer_id: UUID | None
    reviewer_name: str | None
    notes: list[EvaluationNoteResponse]
    updated_at: datetime | None


class MatchingRunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: UUID
    job_id: UUID


class MatchingResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: UUID
    candidate_id: UUID
    candidate_name: str
    current_title: str | None = None
    tfidf_similarity: float | None = None
    skill_coverage: float | None = None
    experience_compatibility: str | None = None
    location_compatibility: str | None = None
    semantic_similarity: float | None = None
    hybrid_score: float | None = None
    explanation: dict[str, Any] = Field(default_factory=dict)


class MatchScoreBucketResponse(BaseModel):
    range: str
    count: int


class MatchScoreMetricDistributionResponse(BaseModel):
    score_scale: str
    total_scored_matches: int
    buckets: list[MatchScoreBucketResponse]


class MatchScoreDistributionResponse(BaseModel):
    experimental_combined_score: MatchScoreMetricDistributionResponse
    tfidf_similarity: MatchScoreMetricDistributionResponse


class EvaluationUpsertRequest(BaseModel):
    """Update the authenticated reviewer's label and optionally one of their notes."""

    workspace_id: UUID
    job_id: UUID
    candidate_id: UUID
    expected_updated_at: datetime | None
    relevance_label: int | None = Field(default=None, ge=0, le=2, strict=True)
    review_status: Literal["reviewed", "needs_human_review"]
    note: str | None = Field(default=None, min_length=1, max_length=10000)
    note_id: UUID | None = None

    @field_validator("note")
    @classmethod
    def note_must_contain_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("A note cannot be blank.")
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def status_requires_compatible_label(self):
        if self.review_status == "reviewed" and self.relevance_label is None:
            raise ValueError("A reviewed evaluation requires a relevance label.")
        if self.review_status == "needs_human_review" and self.relevance_label is not None:
            raise ValueError("An evaluation needing review cannot have a relevance label.")
        if self.review_status == "needs_human_review" and (self.note is not None or self.note_id):
            raise ValueError("Reviewer notes require a reviewed evaluation.")
        if self.note_id is not None and self.note is None:
            raise ValueError("A note is required when updating an existing note.")
        return self
