"""Validate the bundled job and candidate CSV datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
JOB_COLUMNS = {"job_id", "job_title", "description", "required_skills", "min_experience", "location"}
CANDIDATE_COLUMNS = {
    "candidate_id", "name", "current_title", "summary", "skills", "experience_years", "location"
}


def validate_datasets(data_dir: Path = DATA_DIR) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load both datasets and raise ValueError with actionable validation failures."""
    jobs = pd.read_csv(data_dir / "jobs.csv")
    candidates = pd.read_csv(data_dir / "candidates.csv")
    errors: list[str] = []

    for label, frame, required, id_column in (
        ("jobs", jobs, JOB_COLUMNS, "job_id"),
        ("candidates", candidates, CANDIDATE_COLUMNS, "candidate_id"),
    ):
        missing_columns = required.difference(frame.columns)
        if missing_columns:
            errors.append(f"{label}: missing columns {', '.join(sorted(missing_columns))}")
            continue
        if frame[id_column].duplicated().any():
            errors.append(f"{label}: {id_column} values must be unique")
        if frame[list(required)].isna().any().any():
            errors.append(f"{label}: required columns contain missing values")

    if errors:
        raise ValueError("Dataset validation failed: " + "; ".join(errors))
    return jobs, candidates


def main() -> int:
    """Print dataset counts and a clear validation status."""
    try:
        jobs, candidates = validate_datasets()
    except (OSError, ValueError, pd.errors.ParserError) as error:
        print(f"Dataset validation failed: {error}")
        return 1
    print(f"Dataset validation successful: {len(jobs)} jobs and {len(candidates)} candidates.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())