"""Evaluate candidate rankings against human-reviewed relevance judgments."""

from __future__ import annotations

import argparse
import math
from collections.abc import Mapping, Sequence
from pathlib import Path

import pandas as pd

from ml_project.matching import match_candidates

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_REPORT = PROJECT_ROOT / "reports" / "baseline_evaluation.csv"
RELEVANCE_VALUES = {0, 1, 2}
EVALUATION_COLUMNS = {"job_id", "candidate_id", "relevance_label"}


def _checked_label(candidate_id: object, labels: Mapping[object, object]) -> int:
    """Return a validated relevance label or explain why the judgment is unusable."""
    if candidate_id not in labels:
        raise ValueError(f"Missing relevance label for candidate {candidate_id!r}.")
    value = labels[candidate_id]
    if pd.isna(value):
        raise ValueError(f"Missing relevance label for candidate {candidate_id!r}.")
    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"Invalid relevance label for candidate {candidate_id!r}.") from error
    if not numeric_value.is_integer() or int(numeric_value) not in RELEVANCE_VALUES:
        raise ValueError(f"Relevance label for candidate {candidate_id!r} must be 0, 1, or 2.")
    return int(numeric_value)


def precision_at_k(
    ranked_candidate_ids: Sequence[object], labels: Mapping[object, object], k: int = 5
) -> float:
    """Return the fraction of the first k ranked candidates labeled fully relevant (2)."""
    if k <= 0:
        raise ValueError("k must be positive.")
    top_ids = ranked_candidate_ids[:k]
    if not top_ids:
        return 0.0
    relevant = sum(_checked_label(candidate_id, labels) == 2 for candidate_id in top_ids)
    return relevant / k


def recall_at_k(
    ranked_candidate_ids: Sequence[object], labels: Mapping[object, object], k: int = 10
) -> float:
    """Return the fraction of all fully relevant candidates found in the first k."""
    if k <= 0:
        raise ValueError("k must be positive.")
    all_labels = {candidate_id: _checked_label(candidate_id, labels) for candidate_id in labels}
    total_relevant = sum(label == 2 for label in all_labels.values())
    if total_relevant == 0:
        return 0.0
    relevant_in_top_k = sum(
        _checked_label(candidate_id, labels) == 2 for candidate_id in ranked_candidate_ids[:k]
    )
    return relevant_in_top_k / total_relevant


def ndcg_at_k(
    ranked_candidate_ids: Sequence[object], labels: Mapping[object, object], k: int = 5
) -> float:
    """Return normalized discounted cumulative gain using graded labels 0, 1, and 2."""
    if k <= 0:
        raise ValueError("k must be positive.")

    def gain(label: int, rank: int) -> float:
        return (2**label - 1) / math.log2(rank + 2)

    actual = sum(
        gain(_checked_label(candidate_id, labels), rank)
        for rank, candidate_id in enumerate(ranked_candidate_ids[:k])
    )
    ideal_labels = sorted(
        (_checked_label(candidate_id, labels) for candidate_id in labels), reverse=True
    )[:k]
    ideal = sum(gain(label, rank) for rank, label in enumerate(ideal_labels))
    return actual / ideal if ideal else 0.0


def evaluate_job_ranking(
    ranked_candidate_ids: Sequence[object],
    job_evaluations: pd.DataFrame,
) -> dict[str, object]:
    """Calculate metrics only when the ranking has complete valid human judgments."""
    labels: dict[object, object] = dict(
        zip(job_evaluations["candidate_id"], job_evaluations["relevance_label"])
    )
    if job_evaluations["candidate_id"].duplicated().any():
        raise ValueError("Evaluation data contains duplicate candidate labels for a job.")

    missing_ids = [
        candidate_id
        for candidate_id in ranked_candidate_ids
        if candidate_id not in labels or pd.isna(labels.get(candidate_id))
    ]
    extra_ids = set(labels).difference(ranked_candidate_ids)
    invalid_ids = []
    for candidate_id, value in labels.items():
        if pd.isna(value):
            continue
        try:
            _checked_label(candidate_id, labels)
        except ValueError:
            invalid_ids.append(candidate_id)

    complete = not missing_ids and not extra_ids and not invalid_ids
    result: dict[str, object] = {
        "precision_at_5": float("nan"),
        "recall_at_10": float("nan"),
        "ndcg_at_5": float("nan"),
        "evaluation_status": "complete" if complete else "incomplete_labels",
        "num_ranked": len(ranked_candidate_ids),
        "num_labeled": sum(not pd.isna(value) for value in labels.values()),
        "num_missing_labels": len(missing_ids) + len(extra_ids) + len(invalid_ids),
    }
    if complete and ranked_candidate_ids:
        result["precision_at_5"] = precision_at_k(ranked_candidate_ids, labels, 5)
        result["recall_at_10"] = recall_at_k(ranked_candidate_ids, labels, 10)
        result["ndcg_at_5"] = ndcg_at_k(ranked_candidate_ids, labels, 5)
    elif complete:
        result["evaluation_status"] = "empty_ranking"
        result["precision_at_5"] = 0.0
        result["recall_at_10"] = 0.0
        result["ndcg_at_5"] = 0.0
    return result


def evaluate_baseline(
    jobs: pd.DataFrame,
    candidates: pd.DataFrame,
    evaluations: pd.DataFrame,
) -> pd.DataFrame:
    """Evaluate the existing TF-IDF ranking per job and append a macro-average row."""
    missing_columns = EVALUATION_COLUMNS.difference(evaluations.columns)
    if missing_columns:
        raise ValueError(f"Evaluation data is missing columns: {', '.join(sorted(missing_columns))}")
    if evaluations.duplicated(["job_id", "candidate_id"]).any():
        raise ValueError("Evaluation data contains duplicate job_id/candidate_id pairs.")

    rows: list[dict[str, object]] = []
    for _, job in jobs.iterrows():
        job_id = job["job_id"]
        ranking = match_candidates(job["description"], candidates)
        job_result = evaluate_job_ranking(
            ranking["candidate_id"].tolist(),
            evaluations.loc[evaluations["job_id"] == job_id],
        )
        rows.append(
            {
                "job_id": job_id,
                "job_title": job["job_title"],
                **job_result,
            }
        )

    result_frame = pd.DataFrame(rows)
    evaluated = result_frame.loc[result_frame["evaluation_status"] == "complete"]
    macro_metrics = (
        evaluated[["precision_at_5", "recall_at_10", "ndcg_at_5"]].mean()
        if not evaluated.empty
        else pd.Series(
            {"precision_at_5": float("nan"), "recall_at_10": float("nan"), "ndcg_at_5": float("nan")}
        )
    )
    macro_row: dict[str, object] = {
        "job_id": "MACRO_AVERAGE",
        "job_title": "Macro average",
        "precision_at_5": macro_metrics["precision_at_5"],
        "recall_at_10": macro_metrics["recall_at_10"],
        "ndcg_at_5": macro_metrics["ndcg_at_5"],
        "evaluation_status": "macro_average" if not evaluated.empty else "no_fully_labeled_jobs",
        "num_ranked": int(evaluated["num_ranked"].sum()) if not evaluated.empty else 0,
        "num_labeled": int(evaluated["num_labeled"].sum()) if not evaluated.empty else 0,
        "num_missing_labels": int(result_frame["num_missing_labels"].sum()),
    }
    return pd.concat([result_frame, pd.DataFrame([macro_row])], ignore_index=True)


def main() -> int:
    """Run the baseline evaluation and write per-job and macro-average CSV results."""
    parser = argparse.ArgumentParser(description="Evaluate TF-IDF rankings against human labels.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    jobs = pd.read_csv(args.data_dir / "jobs.csv")
    candidates = pd.read_csv(args.data_dir / "candidates.csv")
    evaluations = pd.read_csv(args.data_dir / "evaluation.csv")
    results = evaluate_baseline(jobs, candidates, evaluations)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results.to_csv(args.output, index=False)

    complete_count = int((results["evaluation_status"] == "complete").sum())
    print(f"Evaluation report saved to: {args.output}")
    print(f"Fully labeled jobs evaluated: {complete_count} of {len(jobs)}")
    if complete_count == 0:
        print("Metrics are unavailable until every candidate for a job has a reviewed label.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
