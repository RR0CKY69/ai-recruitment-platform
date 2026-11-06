"""Workspace-authorized candidate shortlisting endpoints."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_membership,
)
from ml_project.api.schemas import ShortlistCreateRequest, ShortlistResponse
from ml_project.audit import record_audit_event
from ml_project.models import Candidate, Job, JobCandidate, Shortlist, User

router = APIRouter(prefix="/shortlists", tags=["shortlists"])


def _details_statement():
    return (
        select(Shortlist, JobCandidate, Job, Candidate, User)
        .join(JobCandidate, Shortlist.job_candidate_id == JobCandidate.id)
        .join(Job, JobCandidate.job_id == Job.id)
        .join(Candidate, JobCandidate.candidate_id == Candidate.id)
        .outerjoin(User, Shortlist.added_by_id == User.id)
    )


def _to_response(row: tuple[Shortlist, JobCandidate, Job, Candidate, User | None]) -> ShortlistResponse:
    shortlist, association, job, candidate, recruiter = row
    return ShortlistResponse(
        shortlist_id=shortlist.id,
        workspace_id=association.workspace_id,
        job_id=job.id,
        job_title=job.title,
        candidate_id=candidate.id,
        candidate_name=candidate.full_name,
        current_title=candidate.current_title,
        experience_years=candidate.experience_years,
        candidate_location=candidate.location,
        shortlisted_at=shortlist.created_at,
        recruiter_id=recruiter.id if recruiter else None,
        recruiter_name=recruiter.full_name if recruiter else None,
        status="ACTIVE",
    )


def _get_shortlist_details(
    session: Session, shortlist_id: UUID, workspace_id: UUID
) -> tuple[Shortlist, JobCandidate, Job, Candidate, User | None] | None:
    return session.execute(
        _details_statement().where(
            Shortlist.id == shortlist_id,
            Shortlist.status == "ACTIVE",
            JobCandidate.workspace_id == workspace_id,
        )
    ).one_or_none()


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The shortlist operation could not be completed.",
    )


@router.post("", response_model=ShortlistResponse, status_code=status.HTTP_201_CREATED)
def add_to_shortlist(
    payload: ShortlistCreateRequest,
    response: Response,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> ShortlistResponse:
    """Create or reactivate a workspace-scoped shortlist entry idempotently."""
    require_workspace_membership(session, user, payload.workspace_id)

    job = session.scalar(
        select(Job).where(
            Job.id == payload.job_id,
            Job.workspace_id == payload.workspace_id,
        )
    )
    candidate = session.scalar(
        select(Candidate).where(
            Candidate.id == payload.candidate_id,
            Candidate.workspace_id == payload.workspace_id,
        )
    )
    if job is None or candidate is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested job or candidate was not found in this workspace.",
        )

    association = session.scalar(
        select(JobCandidate).where(
            JobCandidate.workspace_id == payload.workspace_id,
            JobCandidate.job_id == job.id,
            JobCandidate.candidate_id == candidate.id,
        )
    )
    if association is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Candidate is not assigned to this job.",
        )

    shortlist = session.scalar(
        select(Shortlist).where(Shortlist.job_candidate_id == association.id)
    )
    if shortlist is not None and shortlist.status == "ACTIVE":
        if association.stage != "SHORTLISTED":
            try:
                association.stage = "SHORTLISTED"
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise _database_error() from None

        row = _get_shortlist_details(session, shortlist.id, payload.workspace_id)
        if row is None:
            raise _database_error()
        response.status_code = status.HTTP_200_OK
        return _to_response(row)
    if shortlist is not None and shortlist.status == "HIRED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hired candidate cannot be added to the active shortlist.",
        )

    try:
        if shortlist is None:
            shortlist = Shortlist(job_candidate_id=association.id, added_by_id=user.id)
            session.add(shortlist)
        else:
            shortlist.status = "ACTIVE"
            shortlist.added_by_id = user.id

        association.stage = "SHORTLISTED"
        session.flush()
        record_audit_event(
            session,
            workspace_id=payload.workspace_id,
            actor_id=user.id,
            action="shortlist.added",
            entity_type="shortlist",
            entity_id=shortlist.id,
            details={"job_id": str(job.id), "candidate_id": str(candidate.id)},
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        association = session.scalar(
            select(JobCandidate).where(
                JobCandidate.workspace_id == payload.workspace_id,
                JobCandidate.job_id == job.id,
                JobCandidate.candidate_id == candidate.id,
            )
        )
        if association is None:
            raise _database_error()

        existing = session.scalar(
            select(Shortlist).where(
                Shortlist.job_candidate_id == association.id,
                Shortlist.status == "ACTIVE",
            )
        )
        if existing is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The shortlist entry conflicts with an existing record.",
            ) from None

        response.status_code = status.HTTP_200_OK
        shortlist = existing

        if association.stage != "SHORTLISTED":
            try:
                association.stage = "SHORTLISTED"
                session.commit()
            except SQLAlchemyError:
                session.rollback()
                raise _database_error() from None
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None

    row = _get_shortlist_details(session, shortlist.id, payload.workspace_id)
    if row is None:
        raise _database_error()
    return _to_response(row)


@router.get("", response_model=list[ShortlistResponse])
def list_shortlists(
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[UUID, Query()],
    job_id: Annotated[UUID | None, Query()] = None,
) -> list[ShortlistResponse]:
    """List active shortlist entries in a member workspace, optionally by job."""
    require_workspace_membership(session, user, workspace_id)
    statement = _details_statement().where(
        Shortlist.status == "ACTIVE",
        JobCandidate.workspace_id == workspace_id,
    )
    if job_id is not None:
        statement = statement.where(JobCandidate.job_id == job_id)
    rows = session.execute(statement.order_by(Shortlist.created_at.desc())).all()
    return [_to_response(row) for row in rows]


@router.delete("/{shortlist_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_from_shortlist(
    shortlist_id: UUID,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[UUID, Query()],
) -> Response:
    """Mark a shortlist entry removed without deleting its audit record."""
    require_workspace_membership(session, user, workspace_id)
    row = session.execute(
        _details_statement().where(
            Shortlist.id == shortlist_id,
            JobCandidate.workspace_id == workspace_id,
        )
    ).one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The shortlist entry was not found in this workspace.",
        )
    shortlist = row[0]
    if shortlist.status == "HIRED":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A hired candidate cannot be removed from the shortlist.",
        )
    if shortlist.status != "REMOVED":
        shortlist.status = "REMOVED"
        try:
            session.flush()
            record_audit_event(
                session,
                workspace_id=workspace_id,
                actor_id=user.id,
                action="shortlist.removed",
                entity_type="shortlist",
                entity_id=shortlist.id,
                details={"job_id": str(row[2].id), "candidate_id": str(row[3].id)},
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise _database_error() from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
