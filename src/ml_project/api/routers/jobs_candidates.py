"""Read-only workspace-scoped job and candidate endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_membership,
)
from ml_project.api.schemas import (
    CandidateResponse,
    CandidateAssociatedJobResponse,
    CandidateDetailResponse,
    CandidateMatchingSummaryResponse,
    CandidateSkillResponse,
    CandidateSourceResponse,
    JobResponse,
)
from ml_project.models import Candidate, Job, JobCandidate, User

router = APIRouter(tags=["workspace records"])


@router.get("/jobs", response_model=list[JobResponse])
def list_jobs(
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[JobResponse]:
    """List jobs in a workspace after verifying the current user's membership."""
    require_workspace_membership(session, user, workspace_id)
    jobs = session.scalars(
        select(Job)
        .options(selectinload(Job.requirements))
        .where(Job.workspace_id == workspace_id)
        .order_by(Job.title, Job.id)
    ).all()
    candidate_counts = dict(
        session.execute(
            select(JobCandidate.job_id, func.count(JobCandidate.id))
            .where(JobCandidate.workspace_id == workspace_id)
            .group_by(JobCandidate.job_id)
        ).all()
    )
    return [
        JobResponse(
            id=job.id,
            workspace_id=job.workspace_id,
            legacy_job_id=job.legacy_job_id,
            title=job.title,
            description=job.description,
            required_skills=sorted(
                requirement.description
                for requirement in job.requirements
                if requirement.requirement_type == "REQUIRED_SKILL"
            ),
            minimum_experience_years=job.minimum_experience_years,
            location=job.location,
            employment_type=job.employment_type,
            status=job.status,
            candidate_count=candidate_counts.get(job.id, 0),
        )
        for job in jobs
    ]


@router.get("/candidates", response_model=list[CandidateResponse])
def list_candidates(
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[CandidateResponse]:
    """List workspace candidates and their skills/sources without N+1 queries."""
    require_workspace_membership(session, user, workspace_id)
    candidates = session.scalars(
        select(Candidate)
        .options(selectinload(Candidate.skills), selectinload(Candidate.sources))
        .where(Candidate.workspace_id == workspace_id)
        .order_by(Candidate.full_name, Candidate.id)
    ).all()
    return [
        CandidateResponse(
            id=candidate.id,
            workspace_id=candidate.workspace_id,
            legacy_candidate_id=candidate.legacy_candidate_id,
            full_name=candidate.full_name,
            current_title=candidate.current_title,
            summary=candidate.summary,
            skills=[
                CandidateSkillResponse(
                    name=skill.name,
                    normalized_name=skill.normalized_name,
                    years_experience=skill.years_experience,
                )
                for skill in sorted(candidate.skills, key=lambda item: item.normalized_name)
            ],
            sources=[
                CandidateSourceResponse(
                    provider=source.provider,
                    source_record_id=source.source_record_id,
                    source_url=source.source_url,
                    authorized_basis=source.authorized_basis,
                )
                for source in sorted(candidate.sources, key=lambda item: item.provider)
            ],
            experience_years=candidate.experience_years,
            location=candidate.location,
        )
        for candidate in candidates
    ]


@router.get("/candidates/{candidate_id}", response_model=CandidateDetailResponse)
def get_candidate(
    candidate_id: UUID,
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> CandidateDetailResponse:
    """Return one candidate profile and associations limited to an authorized workspace."""
    require_workspace_membership(session, user, workspace_id)
    candidate = session.scalar(
        select(Candidate)
        .options(selectinload(Candidate.skills), selectinload(Candidate.sources))
        .where(Candidate.id == candidate_id, Candidate.workspace_id == workspace_id)
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found in workspace.",
        )

    associations = session.scalars(
        select(JobCandidate)
        .options(joinedload(JobCandidate.job), selectinload(JobCandidate.match_results))
        .where(
            JobCandidate.workspace_id == workspace_id,
            JobCandidate.candidate_id == candidate.id,
        )
        .order_by(JobCandidate.created_at.desc(), JobCandidate.id)
    ).all()
    profile = CandidateResponse(
        id=candidate.id,
        workspace_id=candidate.workspace_id,
        legacy_candidate_id=candidate.legacy_candidate_id,
        full_name=candidate.full_name,
        current_title=candidate.current_title,
        summary=candidate.summary,
        skills=[
            CandidateSkillResponse(
                name=skill.name,
                normalized_name=skill.normalized_name,
                years_experience=skill.years_experience,
            )
            for skill in sorted(candidate.skills, key=lambda item: item.normalized_name)
        ],
        sources=[
            CandidateSourceResponse(
                provider=source.provider,
                source_record_id=source.source_record_id,
                source_url=source.source_url,
                authorized_basis=source.authorized_basis,
            )
            for source in sorted(candidate.sources, key=lambda item: item.provider)
        ],
        experience_years=candidate.experience_years,
        location=candidate.location,
    )
    return CandidateDetailResponse(
        **profile.model_dump(),
        associated_jobs=[
            CandidateAssociatedJobResponse(
                job_id=association.job.id,
                title=association.job.title,
                status=association.job.status,
                stage=association.stage,
                matching_results=[
                    CandidateMatchingSummaryResponse(
                        model_name=result.model_name,
                        model_version=result.model_version,
                        tfidf_similarity=result.tfidf_similarity,
                        skill_coverage=result.skill_coverage,
                        experience_compatibility=result.experience_compatibility,
                        location_compatibility=result.location_compatibility,
                        hybrid_score=result.hybrid_score,
                        updated_at=result.updated_at,
                    )
                    for result in association.match_results
                ],
            )
            for association in associations
        ],
    )
