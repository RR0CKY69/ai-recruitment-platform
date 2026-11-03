"""Small deterministic helpers for working with job records."""

from __future__ import annotations

import pandas as pd


def load_jobs(path: str) -> pd.DataFrame:
    """Load a job CSV and validate its required columns and unique identifiers."""
    jobs = pd.read_csv(path)
    required = {"job_id", "job_title", "description", "required_skills", "min_experience", "location"}
    missing = required.difference(jobs.columns)
    if missing:
        raise ValueError(f"Jobs CSV is missing required columns: {', '.join(sorted(missing))}")
    if jobs["job_id"].duplicated().any():
        raise ValueError("Jobs CSV contains duplicate job_id values.")
    return jobs