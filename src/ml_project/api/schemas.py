"""Request and response schemas for authentication endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


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
    """Workspace-visible candidate profile, excluding email and internal fields."""

    id: UUID
    workspace_id: UUID
    legacy_candidate_id: str | None
    full_name: str
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
