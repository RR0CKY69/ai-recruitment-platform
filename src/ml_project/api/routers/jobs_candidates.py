"""Read-only workspace-scoped job and candidate endpoints."""

from __future__ import annotations

import io
import os
import re
import zipfile
from typing import Annotated
from uuid import UUID

from docx import Document as DocxDocument
from docx.opc.exceptions import PackageNotFoundError as DocxPackageNotFoundError
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from pypdf import PdfReader
from pypdf.errors import PdfReadError
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, joinedload, selectinload

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_membership,
)
from ml_project.api.schemas import (
    AssignCandidateRequest,
    CandidateAssociatedJobResponse,
    CandidateDetailResponse,
    CandidateMatchingSummaryResponse,
    CandidateProfileResponse,
    CandidateRequest,
    CandidateResponse,
    CandidateSkillResponse,
    CandidateSourceResponse,
    JobCandidateAssignmentResponse,
    JobRequest,
    JobResponse,
    ResumeCandidateDraft,
    ResumeUploadResponse,
    UpdateJobCandidateStageRequest,
)
from ml_project.config import get_max_resume_size_bytes
from ml_project.audit import record_audit_event
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
)

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
            email=candidate.email,
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
        email=candidate.email,
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


def _job_candidate_association_response(association: JobCandidate) -> JobCandidateAssignmentResponse:
    candidate = association.candidate
    return JobCandidateAssignmentResponse(
        candidate_id=candidate.id,
        workspace_id=candidate.workspace_id,
        full_name=candidate.full_name,
        email=candidate.email,
        current_title=candidate.current_title,
        summary=candidate.summary,
        experience_years=candidate.experience_years,
        location=candidate.location,
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
        stage=association.stage,
    )


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The job-candidate operation could not be completed.",
    )


@router.get("/jobs/{job_id}/candidates", response_model=list[JobCandidateAssignmentResponse])
def list_job_candidates(
    job_id: UUID,
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[JobCandidateAssignmentResponse]:
    """Return candidates explicitly assigned to one job in an authorized workspace."""
    require_workspace_membership(session, user, workspace_id)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in workspace.",
        )
    associations = session.scalars(
        select(JobCandidate)
        .options(
            joinedload(JobCandidate.candidate).selectinload(Candidate.skills),
            joinedload(JobCandidate.candidate).selectinload(Candidate.sources),
        )
        .where(
            JobCandidate.workspace_id == workspace_id,
            JobCandidate.job_id == job_id,
        )
        .order_by(JobCandidate.created_at.desc(), JobCandidate.id)
    ).all()
    return [_job_candidate_association_response(association) for association in associations]


@router.post(
    "/jobs/{job_id}/candidates",
    response_model=JobCandidateAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
def assign_candidate_to_job(
    job_id: UUID,
    payload: AssignCandidateRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> JobCandidateAssignmentResponse:
    """Assign a workspace candidate to a workspace job."""
    require_workspace_membership(session, user, payload.workspace_id)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == payload.workspace_id)
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in workspace.",
        )
    candidate = session.scalar(
        select(Candidate).where(
            Candidate.id == payload.candidate_id,
            Candidate.workspace_id == payload.workspace_id,
        )
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found in workspace.",
        )
    association = session.scalar(
        select(JobCandidate).where(
            JobCandidate.workspace_id == payload.workspace_id,
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == payload.candidate_id,
        )
    )
    if association is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Candidate is already assigned to this job.",
        )
    association = JobCandidate(
        workspace_id=payload.workspace_id,
        job_id=job_id,
        candidate_id=payload.candidate_id,
        created_by_id=user.id,
    )
    session.add(association)
    try:
        session.flush()
        session.commit()
    except IntegrityError:
        session.rollback()
        association = session.scalar(
            select(JobCandidate).where(
                JobCandidate.workspace_id == payload.workspace_id,
                JobCandidate.job_id == job_id,
                JobCandidate.candidate_id == payload.candidate_id,
            )
        )
        if association is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Candidate is already assigned to this job.",
            ) from None
    return _job_candidate_association_response(association)


@router.delete("/jobs/{job_id}/candidates/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_candidate_from_job(
    job_id: UUID,
    candidate_id: UUID,
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> Response:
    """Remove a job-candidate association without deleting historical recruitment data."""
    require_workspace_membership(session, user, workspace_id)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in workspace.",
        )
    candidate = session.scalar(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.workspace_id == workspace_id)
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found in workspace.",
        )
    association = session.scalar(
        select(JobCandidate).where(
            JobCandidate.workspace_id == workspace_id,
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
    )
    if association is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found in workspace.",
        )
    dependent_count = (
        session.scalar(
            select(func.count()).select_from(MatchResult).where(
                MatchResult.job_candidate_id == association.id
            )
        )
        + session.scalar(
            select(func.count()).select_from(Shortlist).where(
                Shortlist.job_candidate_id == association.id
            )
        )
        + session.scalar(
            select(func.count()).select_from(EvaluationLabel).where(
                EvaluationLabel.job_candidate_id == association.id
            )
        )
    )
    if dependent_count > 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot remove assignment with existing historical recruitment data.",
        )
    session.delete(association)
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/jobs/{job_id}/candidates/{candidate_id}",
    response_model=JobCandidateAssignmentResponse,
)
def update_job_candidate_stage(
    job_id: UUID,
    candidate_id: UUID,
    payload: UpdateJobCandidateStageRequest,
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> JobCandidateAssignmentResponse:
    """Update a job-candidate stage and synchronize its shortlist entry."""
    require_workspace_membership(session, user, workspace_id)

    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == workspace_id)
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in workspace.",
        )

    candidate = session.scalar(
        select(Candidate).where(
            Candidate.id == candidate_id,
            Candidate.workspace_id == workspace_id,
        )
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found in workspace.",
        )

    association = session.scalar(
        select(JobCandidate).where(
            JobCandidate.workspace_id == workspace_id,
            JobCandidate.job_id == job_id,
            JobCandidate.candidate_id == candidate_id,
        )
    )
    if association is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assignment not found in workspace.",
        )

    shortlist = session.scalar(
        select(Shortlist).where(
            Shortlist.job_candidate_id == association.id
        )
    )

    if payload.stage == "SHORTLISTED":
        if shortlist is None:
            shortlist = Shortlist(
                job_candidate_id=association.id,
                added_by_id=user.id,
                status="ACTIVE",
            )
            session.add(shortlist)
            session.flush()
            record_audit_event(
                session,
                workspace_id=workspace_id,
                actor_id=user.id,
                action="shortlist.added",
                entity_type="shortlist",
                entity_id=shortlist.id,
                details={"job_id": str(job_id), "candidate_id": str(candidate_id)},
            )
        elif shortlist.status in {"REMOVED", "HIRED"}:
            shortlist.status = "ACTIVE"
            shortlist.added_by_id = user.id
            record_audit_event(
                session,
                workspace_id=workspace_id,
                actor_id=user.id,
                action="shortlist.added",
                entity_type="shortlist",
                entity_id=shortlist.id,
                details={"job_id": str(job_id), "candidate_id": str(candidate_id)},
            )

    elif payload.stage == "HIRED":
        shortlist_created = shortlist is None

        if shortlist_created:
            shortlist = Shortlist(
                job_candidate_id=association.id,
                added_by_id=user.id,
                status="HIRED",
            )
            session.add(shortlist)
            session.flush()

        if shortlist_created or shortlist.status != "HIRED":
            shortlist.status = "HIRED"
            record_audit_event(
                session,
                workspace_id=workspace_id,
                actor_id=user.id,
                action="shortlist.hired",
                entity_type="shortlist",
                entity_id=shortlist.id,
                details={"job_id": str(job_id), "candidate_id": str(candidate_id)},
            )

    elif shortlist is not None and shortlist.status in {"ACTIVE", "HIRED"}:
        shortlist.status = "REMOVED"
        record_audit_event(
            session,
            workspace_id=workspace_id,
            actor_id=user.id,
            action="shortlist.removed",
            entity_type="shortlist",
            entity_id=shortlist.id,
            details={"job_id": str(job_id), "candidate_id": str(candidate_id)},
        )

    association.stage = payload.stage

    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None

    return _job_candidate_association_response(association)



def _job_response(job: Job, session: Session) -> JobResponse:
    """Build the public JobResponse for one workspace-scoped job."""
    candidate_count = session.scalar(
        select(func.count(JobCandidate.id)).where(
            JobCandidate.workspace_id == job.workspace_id,
            JobCandidate.job_id == job.id,
        )
    )
    return JobResponse(
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
        candidate_count=candidate_count or 0,
    )


@router.post("/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(
    payload: JobRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> JobResponse:
    """Create a workspace-scoped job with its required-skill requirements."""
    require_workspace_membership(session, user, payload.workspace_id)
    job = Job(
        workspace_id=payload.workspace_id,
        created_by_id=user.id,
        title=payload.title,
        description=payload.description,
        employment_type=payload.employment_type,
        location=payload.location,
        minimum_experience_years=payload.minimum_experience_years,
        status=payload.status,
    )
    session.add(job)
    session.flush()
    for skill in payload.required_skills:
        session.add(
            JobRequirement(
                job_id=job.id,
                requirement_type="REQUIRED_SKILL",
                description=skill,
                normalized_value=skill.casefold(),
            )
        )
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None
    return _job_response(job, session)


@router.put("/jobs/{job_id}", response_model=JobResponse)
def update_job(
    job_id: UUID,
    payload: JobRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> JobResponse:
    """Update a workspace-scoped job without touching assignments or history."""
    require_workspace_membership(session, user, payload.workspace_id)
    job = session.scalar(
        select(Job).where(Job.id == job_id, Job.workspace_id == payload.workspace_id)
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found in workspace.",
        )
    job.title = payload.title
    job.description = payload.description
    job.employment_type = payload.employment_type
    job.location = payload.location
    job.minimum_experience_years = payload.minimum_experience_years
    job.status = payload.status
    session.execute(delete(JobRequirement).where(JobRequirement.job_id == job_id))
    for skill in payload.required_skills:
        session.add(
            JobRequirement(
                job_id=job_id,
                requirement_type="REQUIRED_SKILL",
                description=skill,
                normalized_value=skill.casefold(),
            )
        )
    try:
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None
    return _job_response(job, session)


def _candidate_profile_response(candidate: Candidate) -> CandidateProfileResponse:
    """Build the public CandidateProfileResponse for one candidate."""
    return CandidateProfileResponse(
        id=candidate.id,
        workspace_id=candidate.workspace_id,
        legacy_candidate_id=candidate.legacy_candidate_id,
        full_name=candidate.full_name,
        email=candidate.email,
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


@router.post("/candidates", response_model=CandidateProfileResponse, status_code=status.HTTP_201_CREATED)
def create_candidate(
    payload: CandidateRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> CandidateProfileResponse:
    """Create a workspace-scoped candidate profile without assigning it to any job."""
    require_workspace_membership(session, user, payload.workspace_id)
    existing_email = session.scalar(
        select(Candidate.id).where(
            Candidate.workspace_id == payload.workspace_id,
            Candidate.email == payload.email,
        )
    )
    if existing_email is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists in the workspace.",
        )
    candidate = Candidate(
        workspace_id=payload.workspace_id,
        created_by_id=user.id,
        full_name=payload.full_name,
        email=payload.email,
        current_title=payload.current_title,
        summary=payload.summary,
        experience_years=payload.experience_years,
        location=payload.location,
    )
    session.add(candidate)
    session.flush()
    for skill in payload.skills:
        session.add(
            CandidateSkill(
                candidate_id=candidate.id,
                name=skill,
                normalized_name=skill.casefold(),
            )
        )
    for source in payload.sources:
        session.add(
            CandidateSource(
                candidate_id=candidate.id,
                provider=source.provider,
                source_record_id=source.source_record_id,
                source_url=source.source_url,
                authorized_basis=source.authorized_basis,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists in the workspace.",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None
    session.refresh(candidate)
    return _candidate_profile_response(candidate)


@router.put("/candidates/{candidate_id}", response_model=CandidateProfileResponse)
def update_candidate(
    candidate_id: UUID,
    payload: CandidateRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> CandidateProfileResponse:
    """Update a reusable workspace candidate profile without creating job assignments."""
    require_workspace_membership(session, user, payload.workspace_id)
    candidate = session.scalar(
        select(Candidate).where(Candidate.id == candidate_id, Candidate.workspace_id == payload.workspace_id)
    )
    if candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found in workspace.",
        )
    if payload.email != candidate.email:
        conflicting_email = session.scalar(
            select(Candidate.id).where(
                Candidate.workspace_id == payload.workspace_id,
                Candidate.email == payload.email,
                Candidate.id != candidate_id,
            )
        )
        if conflicting_email is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A candidate with this email already exists in the workspace.",
            )
    candidate.full_name = payload.full_name
    candidate.email = payload.email
    candidate.current_title = payload.current_title
    candidate.summary = payload.summary
    candidate.experience_years = payload.experience_years
    candidate.location = payload.location
    session.execute(delete(CandidateSkill).where(CandidateSkill.candidate_id == candidate_id))
    for skill in payload.skills:
        session.add(
            CandidateSkill(
                candidate_id=candidate_id,
                name=skill,
                normalized_name=skill.casefold(),
            )
        )
    session.execute(delete(CandidateSource).where(CandidateSource.candidate_id == candidate_id))
    for source in payload.sources:
        session.add(
            CandidateSource(
                candidate_id=candidate_id,
                provider=source.provider,
                source_record_id=source.source_record_id,
                source_url=source.source_url,
                authorized_basis=source.authorized_basis,
            )
        )
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A candidate with this email already exists in the workspace.",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None
    session.refresh(candidate)
    return _candidate_profile_response(candidate)


# Resume upload security constants
_ALLOWED_EXTENSIONS = {".pdf", ".docx"}
_ALLOWED_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_FILE_SIGNATURES = {
    ".pdf": b"%PDF-",
    ".docx": b"PK\x03\x04",
}
_MAX_DOCX_ENTRIES = 2000
_MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
_MAX_EXTRACTED_TEXT_CHARS = 200000

_COMMON_SKILLS = {
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "ruby",
    "php", "swift", "kotlin", "scala", "r", "matlab", "sql", "html", "css", "react",
    "angular", "vue", "django", "flask", "fastapi", "spring", "node.js", "express",
    "aws", "azure", "gcp", "docker", "kubernetes", "terraform", "jenkins", "git",
    "linux", "unix", "windows", "postgresql", "mysql", "mongodb", "redis", "elasticsearch",
    "machine learning", "deep learning", "ai", "nlp", "computer vision", "tensorflow",
    "pytorch", "scikit-learn", "pandas", "numpy", "tableau", "powerbi", "excel",
    "project management", "agile", "scrum", "devops", "ci/cd", "api", "rest", "graphql",
    "communication", "leadership", "teamwork", "problem solving", "analysis",
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")
_YEARS_RE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:\+?\s*)?years?", re.IGNORECASE)
_LOCATION_KEYWORDS = {
    "remote", "hybrid", "onsite", "on-site", "new york", "london", "san francisco",
    "seattle", "austin", "berlin", "toronto", "sydney", "singapore", "tokyo",
}


def _validate_resume_file(
    upload_file: UploadFile,
) -> bytes:
    """Validate the uploaded resume file extension, MIME type, and signature."""
    filename = upload_file.filename or ""
    _, ext = os.path.splitext(filename)
    ext = ext.lower()

    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF and DOCX files are supported.",
        )

    content_type = upload_file.content_type or ""
    expected_mime = _ALLOWED_MIME_TYPES[ext]
    if content_type not in ("", expected_mime):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File type does not match the expected document format.",
        )

    content = upload_file.file.read()
    upload_file.file.seek(0)

    max_size = get_max_resume_size_bytes()
    if len(content) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The uploaded file is empty.",
        )
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Resume file exceeds the 10 MiB size limit.",
        )

    signature = _FILE_SIGNATURES[ext]
    if not content.startswith(signature):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File signature does not match the expected document format.",
        )

    return content


def _extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF file in memory."""
    try:
        reader = PdfReader(io.BytesIO(content))
    except (PdfReadError, Exception):  # noqa: BLE001 - convert any PDF read error to safe 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read the PDF file. It may be corrupted or encrypted.",
        )

    if reader.is_encrypted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Encrypted PDF files are not supported.",
        )

    parts: list[str] = []
    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:  # noqa: BLE001 - per-page extraction failures are non-fatal
            text = ""
        if text:
            parts.append(text)
        if sum(len(p) for p in parts) > _MAX_EXTRACTED_TEXT_CHARS:
            break
    return "\n".join(parts)


def _validate_and_extract_docx(content: bytes) -> str:
    """Validate DOCX zip safety and extract text in memory."""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            names = zf.namelist()
            if len(names) > _MAX_DOCX_ENTRIES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DOCX file contains too many entries.",
                )
            total_uncompressed = 0
            for info in zf.infolist():
                total_uncompressed += info.file_size
                if total_uncompressed > _MAX_DOCX_UNCOMPRESSED_BYTES:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="DOCX file decompression exceeds safe limits.",
                    )
            if "word/document.xml" not in names:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="DOCX file is missing required document content.",
                )
    except zipfile.BadZipFile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read the DOCX file. It may be corrupted.",
        )
    except HTTPException:
        raise

    try:
        document = DocxDocument(io.BytesIO(content))
    except (DocxPackageNotFoundError, Exception):  # noqa: BLE001 - convert any DOCX read error to safe 400
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to read the DOCX file. It may be corrupted.",
        )

    parts: list[str] = []
    for paragraph in document.paragraphs:
        if paragraph.text:
            parts.append(paragraph.text)
        if sum(len(p) for p in parts) > _MAX_EXTRACTED_TEXT_CHARS:
            break
    return "\n".join(parts)


def _parse_resume_text(text: str) -> ResumeCandidateDraft:
    """Parse extracted resume text into a candidate draft using heuristics."""
    if not text or not text.strip():
        return ResumeCandidateDraft()

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ResumeCandidateDraft()

    # Email
    email_match = _EMAIL_RE.search(text)
    email = email_match.group(0).strip().casefold() if email_match else None

    # Name: first 1-3 lines that look like a person's name
    name = None
    for line in lines[:5]:
        if _EMAIL_RE.search(line):
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(w.isalpha() or w.replace("-", "").isalpha() for w in words):
            candidate_name = line
            if not any(skip in candidate_name.lower() for skip in ("resume", "cv", "curriculum", "profile")):
                name = candidate_name
                break

    # Experience years
    experience_years = None
    years_match = _YEARS_RE.search(text)
    if years_match:
        try:
            experience_years = int(float(years_match.group(1)))
        except (ValueError, TypeError):
            experience_years = None

    # Location
    location = None
    text_lower = text.lower()
    for keyword in sorted(_LOCATION_KEYWORDS, key=len, reverse=True):
        if keyword in text_lower:
            location = keyword.title() if keyword != "remote" else "Remote"
            break

    # Skills from common skills list
    found_skills: list[str] = []
    for skill in sorted(_COMMON_SKILLS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE):
            found_skills.append(skill.title() if skill not in ("ai", "api", "ci/cd", "sql") else skill.upper())
    # Deduplicate while preserving order
    seen_skills: set[str] = set()
    deduped_skills: list[str] = []
    for skill in found_skills:
        key = skill.casefold()
        if key not in seen_skills:
            seen_skills.add(key)
            deduped_skills.append(skill)

    # Summary: first substantial paragraph that isn't the name/header
    summary = None
    for line in lines:
        if len(line) > 40 and line != name and not _EMAIL_RE.search(line):
            summary = line
            break

    # Source entry
    sources = [
        {
            "provider": "resume_upload",
            "source_record_id": None,
            "source_url": None,
            "authorized_basis": "Resume uploaded by user for review",
        }
    ]

    return ResumeCandidateDraft(
        full_name=name,
        email=email,
        current_title=None,
        summary=summary,
        experience_years=experience_years,
        location=location,
        skills=deduped_skills[:20],
        sources=sources,
    )


@router.post(
    "/candidates/resume",
    response_model=ResumeUploadResponse,
)
def upload_resume(
    workspace_id: Annotated[UUID, Form()],
    file: Annotated[UploadFile, File()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ResumeUploadResponse:
    """Upload and parse a resume PDF or DOCX, returning a draft for review.

    No candidate is created or assigned automatically. The parsed draft must be
    explicitly saved through the candidate CRUD endpoints by the user.
    """
    require_workspace_membership(session, user, workspace_id)

    content = _validate_resume_file(file)
    _, ext = os.path.splitext(file.filename or "")
    ext = ext.lower()

    if ext == ".pdf":
        text = _extract_pdf_text(content)
    else:
        text = _validate_and_extract_docx(content)

    draft = _parse_resume_text(text)

    # Return null when no useful profile information could be extracted
    if not any(
        [
            draft.full_name,
            draft.email,
            draft.summary,
            draft.experience_years is not None,
            draft.location,
            draft.skills,
        ]
    ):
        return ResumeUploadResponse(parsed_candidate=None)

    return ResumeUploadResponse(parsed_candidate=draft)
