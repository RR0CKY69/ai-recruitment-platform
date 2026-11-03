"""Explainable TF-IDF baseline for ranking candidate profiles against a job."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

RESULT_COLUMNS = ["candidate_id", "name", "similarity_score"]
PROFILE_TEXT_COLUMNS = ("current_title", "summary", "skills")


def _text(value: object) -> str:
    """Convert missing or non-text CSV values into safe strings."""
    if pd.isna(value):
        return ""
    return str(value).strip()


def match_candidates(job_description: str, candidates: pd.DataFrame) -> pd.DataFrame:
    """Rank candidate profiles by TF-IDF cosine similarity to a job description.

    Only textual similarity is implemented. Skill coverage, experience, location,
    and semantic similarity are intentionally left for future ranking signals.
    """
    if candidates.empty:
        return pd.DataFrame(columns=RESULT_COLUMNS)

    ranked = pd.DataFrame(index=candidates.index)
    ranked["candidate_id"] = candidates.get("candidate_id", pd.Series(pd.NA, index=candidates.index))
    ranked["name"] = candidates.get("name", pd.Series(pd.NA, index=candidates.index))

    profile_texts = [
        " ".join(_text(candidates.iloc[row].get(column, "")) for column in PROFILE_TEXT_COLUMNS)
        for row in range(len(candidates))
    ]
    job_text = _text(job_description)

    vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
    analyzer = vectorizer.build_analyzer()
    if not job_text or not any(profile_texts) or not any(
        analyzer(text) for text in [job_text, *profile_texts]
    ):
        ranked["similarity_score"] = 0.0
    else:
        vectors = vectorizer.fit_transform([job_text, *profile_texts])
        ranked["similarity_score"] = cosine_similarity(vectors[0:1], vectors[1:]).ravel()

    return (
        ranked[RESULT_COLUMNS]
        .sort_values("similarity_score", ascending=False, kind="stable")
        .reset_index(drop=True)
    )


def main() -> int:
    """Rank bundled fictional candidates for a selected job ID."""
    parser = argparse.ArgumentParser(description="Rank sample candidates with TF-IDF similarity.")
    parser.add_argument("--job-id", required=True, help="job ID from data/jobs.csv")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "data",
        help="directory containing jobs.csv and candidates.csv",
    )
    args = parser.parse_args()
    jobs = pd.read_csv(args.data_dir / "jobs.csv")
    candidates = pd.read_csv(args.data_dir / "candidates.csv")
    selected = jobs.loc[jobs["job_id"] == args.job_id]
    if selected.empty:
        parser.error(f"unknown job ID: {args.job_id}")
    job = selected.iloc[0]
    print(f"Candidates ranked for: {job['job_title']} ({job['job_id']})")
    print(match_candidates(job["description"], candidates).to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())