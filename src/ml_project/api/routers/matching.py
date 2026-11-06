"""Workspace-authorized candidate matching endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from ml_project.api.dependencies import (
    get_api_session,
    get_current_user,
    require_workspace_membership,
)
from ml_project.api.schemas import (
    MatchingResultResponse,
    MatchingRunRequest,
    MatchScoreBucketResponse,
    MatchScoreDistributionResponse,
    MatchScoreMetricDistributionResponse,
)
from ml_project.audit import record_audit_event
from ml_project.matching import match_candidates
from ml_project.matching_signals import assess_candidate, combined_score
from ml_project.models import (
    Candidate,
    Job,
    JobCandidate,
    JobRequirement,
    MatchResult,
    User,
)

router = APIRouter(prefix="/matching", tags=["matching"])

MODEL_NAME = "tfidf-cosine"
MODEL_VERSION = "1.0"
SCORE_BUCKETS = ((0, 20), (20, 40), (40, 60), (60, 80), (80, 100))
SCORE_BUCKET_LABELS = ("0–20", ">20–40", ">40–60", ">60–80", ">80–100")


def _score_bucket_expression(score):
    conditions = [
        (and_(score >= lower, score <= upper), index)
        if index == 0
        else (and_(score > lower, score <= upper), index)
        for index, (lower, upper) in enumerate(SCORE_BUCKETS)
    ]
    return case(*conditions, else_=None)


def _distribution_columns(score, name: str):
    bucket = _score_bucket_expression(score)
    total = func.count(case((bucket.is_not(None), 1))).label(f"{name}_total")
    counts = [
        func.coalesce(func.sum(case((bucket == index, 1), else_=0)), 0).label(f"{name}_{index}")
        for index in range(len(SCORE_BUCKETS))
    ]
    return [total, *counts]


def _score_distribution(row, name: str, score_scale: str) -> MatchScoreMetricDistributionResponse:
    return MatchScoreMetricDistributionResponse(
        score_scale=score_scale,
        total_scored_matches=row._mapping[f"{name}_total"],
        buckets=[
            MatchScoreBucketResponse(
                range=label,
                count=row._mapping[f"{name}_{index}"],
            )
            for index, label in enumerate(SCORE_BUCKET_LABELS)
        ],
    )


def _required_skills(session: Session, job_id: uuid.UUID) -> str:
    rows = session.scalars(
        select(JobRequirement).where(
            JobRequirement.job_id == job_id,
            JobRequirement.requirement_type == "REQUIRED_SKILL",
        )
    ).all()
    return ";".join(r.description for r in rows if r.description)


def _job_dict(job: Job, required_skills: str) -> dict:
    return {
        "required_skills": required_skills,
        "min_experience": job.minimum_experience_years,
        "location": job.location,
    }


def _candidate_dict(candidate: Candidate, skills: str) -> dict:
    return {
        "skills": skills,
        "experience_years": candidate.experience_years,
        "location": candidate.location,
    }


@router.post("/run", response_model=list[MatchingResultResponse], status_code=status.HTTP_200_OK)
def run_matching(
    payload: MatchingRunRequest,
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
) -> list[MatchingResultResponse]:
    require_workspace_membership(session, user, payload.workspace_id)

    job = session.scalar(
        select(Job).where(Job.id == payload.job_id, Job.workspace_id == payload.workspace_id)
    )
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found in workspace.")

    associations = session.scalars(
        select(JobCandidate)
        .options(selectinload(JobCandidate.candidate).selectinload(Candidate.skills))
        .where(
            JobCandidate.workspace_id == payload.workspace_id,
            JobCandidate.job_id == job.id,
        )
    ).all()

    required_skills = _required_skills(session, job.id)

    if not associations:
        try:
            record_audit_event(
                session,
                workspace_id=payload.workspace_id,
                actor_id=user.id,
                action="matching.run",
                entity_type="job",
                entity_id=job.id,
                details={"candidate_count": 0},
            )
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Matching could not be completed.")
        return []

    # Build DataFrame for TF-IDF from explicitly assigned candidates only.
    rows = []
    for assoc in associations:
        c = assoc.candidate
        skills = ";".join(s.name for s in c.skills if s.name)
        rows.append({
            "candidate_id": str(c.id),
            "name": c.full_name,
            "current_title": c.current_title or "",
            "summary": c.summary or "",
            "skills": skills,
        })
    df = pd.DataFrame(rows, columns=["candidate_id", "name", "current_title", "summary", "skills"])
    ranked = match_candidates(job.description or "", df)

    # Build score lookup by candidate_id
    score_map = {str(r["candidate_id"]): float(r["similarity_score"]) for _, r in ranked.iterrows()}

    results: list[MatchingResultResponse] = []
    for assoc in associations:
        c = assoc.candidate
        skills = ";".join(s.name for s in c.skills if s.name)
        signals = assess_candidate(_job_dict(job, required_skills), _candidate_dict(c, skills))
        combined = combined_score(
            score_map.get(str(c.id), 0.0),
            float(signals["skill_coverage_percent"]),
            str(signals["experience_compatibility"]),
            str(signals["location_compatibility"]),
        )

        # Upsert MatchResult against the existing association only. Never create JobCandidate associations.
        existing = session.scalar(
            select(MatchResult).where(
                MatchResult.job_candidate_id == assoc.id,
                MatchResult.model_name == MODEL_NAME,
                MatchResult.model_version == MODEL_VERSION,
            )
        )
        if existing is None:
            mr = MatchResult(
                job_candidate_id=assoc.id,
                model_name=MODEL_NAME,
                model_version=MODEL_VERSION,
                tfidf_similarity=score_map.get(str(c.id), 0.0),
                skill_coverage=float(signals["skill_coverage_percent"]) / 100.0,
                experience_compatibility=str(signals["experience_compatibility"]),
                location_compatibility=str(signals["location_compatibility"]),
                semantic_similarity=None,
                hybrid_score=combined,
                explanation={
                    "matched_skills": signals["matched_skills"],
                    "missing_skills": signals["missing_skills"],
                    "experience_required": signals["experience_required"],
                    "experience_candidate": signals["experience_candidate"],
                    "experience_unknown": signals["experience_compatibility"] == "Unknown",
                    "location_unknown": signals["location_compatibility"] == "Unknown",
                    "combined_score": combined,
                },
            )
            session.add(mr)
        else:
            existing.tfidf_similarity = score_map.get(str(c.id), 0.0)
            existing.skill_coverage = float(signals["skill_coverage_percent"]) / 100.0
            existing.experience_compatibility = str(signals["experience_compatibility"])
            existing.location_compatibility = str(signals["location_compatibility"])
            existing.hybrid_score = combined
            existing.explanation = {
                "matched_skills": signals["matched_skills"],
                "missing_skills": signals["missing_skills"],
                "experience_required": signals["experience_required"],
                "experience_candidate": signals["experience_candidate"],
                "experience_unknown": signals["experience_compatibility"] == "Unknown",
                "location_unknown": signals["location_compatibility"] == "Unknown",
                "combined_score": combined,
            }
            mr = existing
        session.flush()

        results.append(MatchingResultResponse(
            job_id=job.id,
            candidate_id=c.id,
            candidate_name=c.full_name,
            current_title=c.current_title,
            tfidf_similarity=mr.tfidf_similarity,
            skill_coverage=mr.skill_coverage,
            experience_compatibility=mr.experience_compatibility,
            location_compatibility=mr.location_compatibility,
            semantic_similarity=None,
            hybrid_score=mr.hybrid_score,
            explanation=mr.explanation,
        ))

    try:
        record_audit_event(
            session,
            workspace_id=payload.workspace_id,
            actor_id=user.id,
            action="matching.run",
            entity_type="job",
            entity_id=job.id,
            details={"candidate_count": len(associations)},
        )
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Matching could not be completed.")

    # Return ranked by tfidf desc
    results.sort(key=lambda r: (r.tfidf_similarity or 0.0), reverse=True)
    return results


@router.get("", response_model=list[MatchingResultResponse])
def get_matching(
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[uuid.UUID, Query()],
    job_id: Annotated[uuid.UUID | None, Query()] = None,
) -> list[MatchingResultResponse]:
    require_workspace_membership(session, user, workspace_id)

    stmt = (
        select(MatchResult, JobCandidate, Job, Candidate)
        .join(JobCandidate, MatchResult.job_candidate_id == JobCandidate.id)
        .join(Job, JobCandidate.job_id == Job.id)
        .join(Candidate, JobCandidate.candidate_id == Candidate.id)
        .where(JobCandidate.workspace_id == workspace_id)
    )
    if job_id is not None:
        stmt = stmt.where(JobCandidate.job_id == job_id)

    rows = session.execute(stmt).all()
    out = []
    for mr, assoc, job, candidate in rows:
        out.append(MatchingResultResponse(
            job_id=job.id,
            candidate_id=candidate.id,
            candidate_name=candidate.full_name,
            current_title=candidate.current_title,
            tfidf_similarity=mr.tfidf_similarity,
            skill_coverage=mr.skill_coverage,
            experience_compatibility=mr.experience_compatibility,
            location_compatibility=mr.location_compatibility,
            semantic_similarity=mr.semantic_similarity,
            hybrid_score=mr.hybrid_score,
            explanation=mr.explanation or {},
        ))
    out.sort(key=lambda r: (r.tfidf_similarity or 0.0), reverse=True)
    return out


@router.get("/score-distribution", response_model=MatchScoreDistributionResponse)
def get_match_score_distribution(
    session: Annotated[Session, Depends(get_api_session)],
    user: Annotated[User, Depends(get_current_user)],
    workspace_id: Annotated[uuid.UUID, Query()],
) -> MatchScoreDistributionResponse:
    """Aggregate persisted matching scores for one authorized workspace."""
    require_workspace_membership(session, user, workspace_id)
    tfidf_percent = MatchResult.tfidf_similarity * 100.0
    row = session.execute(
        select(
            *_distribution_columns(MatchResult.hybrid_score, "combined"),
            *_distribution_columns(tfidf_percent, "tfidf"),
        )
        .select_from(MatchResult)
        .join(JobCandidate, MatchResult.job_candidate_id == JobCandidate.id)
        .where(JobCandidate.workspace_id == workspace_id)
    ).one()
    return MatchScoreDistributionResponse(
        experimental_combined_score=_score_distribution(
            row,
            "combined",
            "0–100 experimental combined score",
        ),
        tfidf_similarity=_score_distribution(
            row,
            "tfidf",
            "0–100 scale (cosine similarity × 100)",
        ),
    )