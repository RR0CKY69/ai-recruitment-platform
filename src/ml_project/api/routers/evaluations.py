"""Workspace-authorized evaluation label and reviewer-note endpoints."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_membership,
)
from ml_project.api.schemas import (
    EvaluationNoteResponse,
    EvaluationResponse,
    EvaluationUpsertRequest,
)
from ml_project.audit import record_audit_event
from ml_project.models import (
    Candidate,
    EvaluationLabel,
    EvaluationNote,
    Job,
    JobCandidate,
    User,
)

router = APIRouter(prefix="/evaluations", tags=["evaluations"])


def _same_timestamp(left, right) -> bool:
    """Compare stored timestamps consistently across PostgreSQL and SQLite."""
    if left is None or right is None:
        return left is right
    if left.tzinfo is None:
        left = left.replace(tzinfo=timezone.utc)
    if right.tzinfo is None:
        right = right.replace(tzinfo=timezone.utc)
    return left == right


def _database_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="The evaluation operation could not be completed.",
    )


def _workspace_evaluation_rows(session: Session, workspace_id: UUID):
    """Load pairs, labels, reviewer identities, notes, and authors in one query."""
    reviewer = aliased(User, name="reviewer")
    note_author = aliased(User, name="note_author")
    return session.execute(
        select(
            JobCandidate,
            Job,
            Candidate,
            EvaluationLabel,
            reviewer,
            EvaluationNote,
            note_author,
        )
        .join(Job, JobCandidate.job_id == Job.id)
        .join(Candidate, JobCandidate.candidate_id == Candidate.id)
        .outerjoin(EvaluationLabel, EvaluationLabel.job_candidate_id == JobCandidate.id)
        .outerjoin(reviewer, reviewer.id == EvaluationLabel.reviewer_id)
        .outerjoin(EvaluationNote, EvaluationNote.evaluation_label_id == EvaluationLabel.id)
        .outerjoin(note_author, note_author.id == EvaluationNote.author_id)
        .where(JobCandidate.workspace_id == workspace_id)
        .order_by(Job.title, Candidate.full_name, EvaluationLabel.created_at, EvaluationNote.created_at)
    ).all()


def _evaluation_response(
    association: JobCandidate,
    job: Job,
    candidate: Candidate,
    label: EvaluationLabel | None,
    reviewer: User | None,
    notes: list[EvaluationNoteResponse],
) -> EvaluationResponse:
    return EvaluationResponse(
        evaluation_id=label.id if label else None,
        workspace_id=association.workspace_id,
        job_id=job.id,
        legacy_job_id=job.legacy_job_id,
        job_title=job.title,
        candidate_id=candidate.id,
        legacy_candidate_id=candidate.legacy_candidate_id,
        candidate_name=candidate.full_name,
        current_title=candidate.current_title,
        relevance_label=label.relevance_label if label else None,
        review_status=("reviewed" if label else "needs_human_review"),
        reviewer_id=reviewer.id if reviewer else None,
        reviewer_name=reviewer.full_name if reviewer else None,
        notes=notes,
        updated_at=label.updated_at if label else None,
    )


@router.get("", response_model=list[EvaluationResponse])
def list_evaluations(
    workspace_id: Annotated[UUID, Query()],
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[EvaluationResponse]:
    """Return labels and pending pairs that belong to an authorized workspace."""
    require_workspace_membership(session, user, workspace_id)
    grouped: dict[tuple[UUID, UUID | None], dict[str, object]] = {}
    for association, job, candidate, label, reviewer, note, author in _workspace_evaluation_rows(
        session, workspace_id
    ):
        key = (association.id, label.id if label else None)
        if key not in grouped:
            grouped[key] = {
                "association": association,
                "job": job,
                "candidate": candidate,
                "label": label,
                "reviewer": reviewer,
                "notes": [],
            }
        if note is not None:
            grouped[key]["notes"].append(  # type: ignore[union-attr]
                EvaluationNoteResponse(
                    note_id=note.id,
                    author_id=note.author_id,
                    author_name=author.full_name if author else None,
                    note=note.note,
                )
            )

    return [
        _evaluation_response(
            entry["association"],
            entry["job"],
            entry["candidate"],
            entry["label"],
            entry["reviewer"],
            entry["notes"],
        )
        for entry in grouped.values()
    ]


@router.put("", response_model=EvaluationResponse)
def upsert_evaluation(
    payload: EvaluationUpsertRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> EvaluationResponse:
    """Create or update the current user's label and notes for an existing pair."""
    require_workspace_membership(session, user, payload.workspace_id)
    association = session.scalar(
        select(JobCandidate).where(
            JobCandidate.workspace_id == payload.workspace_id,
            JobCandidate.job_id == payload.job_id,
            JobCandidate.candidate_id == payload.candidate_id,
        )
    )
    if association is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The job-candidate pair was not found in this workspace.",
        )

    label = session.scalar(
        select(EvaluationLabel).where(
            EvaluationLabel.job_candidate_id == association.id,
            EvaluationLabel.reviewer_id == user.id,
        )
    )
    if payload.review_status == "needs_human_review":
        if label is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An existing reviewed label cannot be cleared by this endpoint.",
            )
        return _evaluation_response(
            association,
            association.job,
            association.candidate,
            None,
            None,
            [],
        )

    if label is None and payload.expected_updated_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The evaluation changed after it was loaded. Refresh and try again.",
        )
    if label is not None and not _same_timestamp(
        label.updated_at, payload.expected_updated_at
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The evaluation changed after it was loaded. Refresh and try again.",
        )

    is_existing_label = label is not None
    if label is None:
        label = EvaluationLabel(
            job_candidate_id=association.id,
            reviewer_id=user.id,
            relevance_label=payload.relevance_label,
            review_status="REVIEWED",
        )
        session.add(label)
    else:
        previous_updated_at = label.updated_at
        previous_aware = previous_updated_at
        if previous_aware.tzinfo is None:
            previous_aware = previous_aware.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        if now <= previous_aware:
            now = previous_aware + timedelta(microseconds=1)

    try:
        if is_existing_label:
            result = session.execute(
                update(EvaluationLabel)
                .where(
                    EvaluationLabel.id == label.id,
                    EvaluationLabel.reviewer_id == user.id,
                    EvaluationLabel.updated_at == previous_updated_at,
                )
                .values(
                    relevance_label=payload.relevance_label,
                    review_status="REVIEWED",
                    updated_at=now,
                )
                .execution_options(synchronize_session=False)
            )
            if result.rowcount != 1:
                session.rollback()
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="The evaluation changed after it was loaded. Refresh and try again.",
                )
            session.refresh(label)
            record_audit_event(
                session,
                workspace_id=payload.workspace_id,
                actor_id=user.id,
                action="evaluation.label_updated",
                entity_type="evaluation_label",
                entity_id=label.id,
                details={
                    "job_id": str(payload.job_id),
                    "candidate_id": str(payload.candidate_id),
                    "relevance_label": payload.relevance_label,
                },
            )
        else:
            session.flush()
            record_audit_event(
                session,
                workspace_id=payload.workspace_id,
                actor_id=user.id,
                action="evaluation.label_created",
                entity_type="evaluation_label",
                entity_id=label.id,
                details={
                    "job_id": str(payload.job_id),
                    "candidate_id": str(payload.candidate_id),
                    "relevance_label": payload.relevance_label,
                },
            )
        if payload.note is not None and payload.note_id is not None:
            note = session.scalar(
                select(EvaluationNote).where(
                    EvaluationNote.id == payload.note_id,
                    EvaluationNote.evaluation_label_id == label.id,
                    EvaluationNote.author_id == user.id,
                )
            )
            if note is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="The reviewer note was not found.",
                )
            note.note = payload.note
            session.flush()
            record_audit_event(
                session,
                workspace_id=payload.workspace_id,
                actor_id=user.id,
                action="evaluation.note_updated",
                entity_type="evaluation_note",
                entity_id=note.id,
                details={"evaluation_label_id": str(label.id)},
            )
        elif payload.note is not None:
            note = EvaluationNote(
                evaluation_label_id=label.id,
                author_id=user.id,
                note=payload.note,
            )
            session.add(note)
            session.flush()
            record_audit_event(
                session,
                workspace_id=payload.workspace_id,
                actor_id=user.id,
                action="evaluation.note_created",
                entity_type="evaluation_note",
                entity_id=note.id,
                details={"evaluation_label_id": str(label.id)},
            )
        session.commit()
    except HTTPException:
        session.rollback()
        raise
    except IntegrityError:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The evaluation conflicts with an existing review record.",
        ) from None
    except SQLAlchemyError:
        session.rollback()
        raise _database_error() from None

    note_rows = session.execute(
        select(EvaluationNote, User)
        .outerjoin(User, User.id == EvaluationNote.author_id)
        .where(EvaluationNote.evaluation_label_id == label.id)
        .order_by(EvaluationNote.created_at, EvaluationNote.id)
    ).all()
    note_responses = [
        EvaluationNoteResponse(
            note_id=note.id,
            author_id=note.author_id,
            author_name=author.full_name if author else None,
            note=note.note,
        )
        for note, author in note_rows
    ]
    return _evaluation_response(
        association,
        association.job,
        association.candidate,
        label,
        user,
        note_responses,
    )
