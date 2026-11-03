"""Data operations for human review of job-candidate evaluation pairs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

LABELS = {0, 1, 2}
EVALUATION_COLUMNS = ["job_id", "candidate_id", "relevance_label", "label_review_status"]
REVIEW_COLUMNS = [
    "job_id",
    "job_title",
    "description",
    "required_skills",
    "min_experience",
    "job_location",
    "candidate_id",
    "name",
    "current_title",
    "summary",
    "skills",
    "experience_years",
    "candidate_location",
    "relevance_label",
    "label_review_status",
    "reviewer_notes",
    "matched_skills",
    "missing_skills",
]
NOTES_COLUMNS = ["job_id", "candidate_id", "reviewer_notes"]


def load_review_data(data_dir: Path) -> pd.DataFrame:
    """Join evaluation pairs to full job and candidate details."""
    jobs = pd.read_csv(data_dir / "jobs.csv")
    candidates = pd.read_csv(data_dir / "candidates.csv")
    evaluations = pd.read_csv(data_dir / "evaluation.csv")
    missing_columns = set(EVALUATION_COLUMNS[:2] + ["relevance_label"]).difference(
        evaluations.columns
    )
    if missing_columns:
        raise ValueError(f"Evaluation CSV is missing columns: {', '.join(sorted(missing_columns))}")

    if "label_review_status" not in evaluations.columns:
        evaluations["label_review_status"] = "needs_human_review"

    review = evaluations.merge(jobs, on="job_id", how="left", validate="many_to_one")
    review = review.merge(candidates, on="candidate_id", how="left", validate="many_to_one")
    if review[["job_title", "name"]].isna().any().any():
        raise ValueError("Some evaluation pairs refer to unknown job or candidate IDs.")

    review = review.rename(
        columns={"location_x": "job_location", "location_y": "candidate_location"}
    )
    if "job_location" not in review:
        review = review.rename(columns={"location": "job_location"})
    if "candidate_location" not in review:
        raise ValueError("Joined review data is missing candidate location information.")

    notes_path = data_dir / "evaluation_notes.csv"
    if notes_path.exists():
        notes = pd.read_csv(notes_path)
        if not set(NOTES_COLUMNS).issubset(notes.columns):
            raise ValueError("Evaluation notes CSV must contain job_id, candidate_id, and reviewer_notes.")
        if notes.duplicated(["job_id", "candidate_id"]).any():
            raise ValueError("Evaluation notes CSV contains duplicate job-candidate pairs.")
        review = review.merge(
            notes, on=["job_id", "candidate_id"], how="left", validate="one_to_one"
        )
    else:
        review["reviewer_notes"] = ""
    review["reviewer_notes"] = review["reviewer_notes"].astype("string").fillna("")

    skill_details = review.apply(_skill_comparison, axis=1, result_type="expand")
    review["matched_skills"] = skill_details[0]
    review["missing_skills"] = skill_details[1]
    return review[REVIEW_COLUMNS]


def _skill_comparison(row: pd.Series) -> tuple[str, str]:
    """Compare semicolon-separated skill terms for reviewer reference only."""
    required = _split_skills(row["required_skills"])
    candidate_skills = {skill.casefold() for skill in _split_skills(row["skills"])}
    matched = [skill for skill in required if skill.casefold() in candidate_skills]
    missing = [skill for skill in required if skill.casefold() not in candidate_skills]
    return "; ".join(matched), "; ".join(missing)


def _split_skills(value: object) -> list[str]:
    if pd.isna(value):
        return []
    return [skill.strip() for skill in str(value).split(";") if skill.strip()]


def review_progress(review_data: pd.DataFrame) -> dict[str, object]:
    """Summarize reviewed and pending pairs, overall and grouped by job."""
    total = len(review_data)
    reviewed_mask = review_data["label_review_status"].eq("reviewed") & review_data[
        "relevance_label"
    ].isin(LABELS)
    reviewed = int(reviewed_mask.sum())
    by_job = (
        review_data.assign(_is_reviewed=reviewed_mask)
        .groupby(["job_id", "job_title"], as_index=False)
        .agg(total_combinations=("candidate_id", "size"), reviewed_combinations=("_is_reviewed", "sum"))
    )
    by_job["pending_combinations"] = (
        by_job["total_combinations"] - by_job["reviewed_combinations"]
    )
    by_job["completion_percent"] = (
        by_job["reviewed_combinations"] / by_job["total_combinations"] * 100
    )
    return {
        "total": total,
        "reviewed": reviewed,
        "pending": total - reviewed,
        "completion_percent": reviewed / total * 100 if total else 0.0,
        "by_job": by_job,
    }


def save_human_label(
    data_dir: Path,
    job_id: str,
    candidate_id: str,
    relevance_label: int,
    reviewer_notes: str = "",
) -> None:
    """Persist one human label and its separate note without changing other pairs."""
    if isinstance(relevance_label, bool) or relevance_label not in LABELS:
        raise ValueError("Relevance label must be 0 (Not relevant), 1 (Partially relevant), or 2 (Relevant).")

    evaluation_path = data_dir / "evaluation.csv"
    evaluations = pd.read_csv(evaluation_path)
    missing_columns = set(EVALUATION_COLUMNS).difference(evaluations.columns)
    if missing_columns:
        raise ValueError(f"Evaluation CSV is missing columns: {', '.join(sorted(missing_columns))}")
    pair_mask = evaluations["job_id"].eq(job_id) & evaluations["candidate_id"].eq(candidate_id)
    if pair_mask.sum() != 1:
        raise ValueError("The selected job-candidate combination must exist exactly once.")

    notes_path = data_dir / "evaluation_notes.csv"
    notes = (
        pd.read_csv(notes_path)
        if notes_path.exists()
        else pd.DataFrame(columns=NOTES_COLUMNS)
    )
    if not set(NOTES_COLUMNS).issubset(notes.columns):
        raise ValueError("Evaluation notes CSV must contain job_id, candidate_id, and reviewer_notes.")

    evaluations.loc[pair_mask, "relevance_label"] = relevance_label
    evaluations.loc[pair_mask, "label_review_status"] = "reviewed"
    evaluations.to_csv(evaluation_path, index=False)

    note_mask = notes["job_id"].eq(job_id) & notes["candidate_id"].eq(candidate_id)
    if note_mask.any():
        notes.loc[note_mask, "reviewer_notes"] = reviewer_notes
    else:
        notes = pd.concat(
            [
                notes,
                pd.DataFrame(
                    [{"job_id": job_id, "candidate_id": candidate_id, "reviewer_notes": reviewer_notes}]
                ),
            ],
            ignore_index=True,
        )
    notes.to_csv(notes_path, index=False)
