import math

import pandas as pd
import pytest

from ml_project.evaluation import (
    evaluate_baseline,
    evaluate_job_ranking,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
)


def test_precision_at_5_counts_only_label_two():
    ranking = ["a", "b", "c", "d", "e", "f"]
    labels = {"a": 2, "b": 1, "c": 0, "d": 2, "e": 1, "f": 2}

    assert precision_at_k(ranking, labels, 5) == pytest.approx(2 / 5)


def test_recall_at_10_finds_fraction_of_all_label_two_candidates():
    ranking = [str(index) for index in range(12)]
    labels = {str(index): 2 if index in {0, 3, 10} else 0 for index in range(12)}

    assert recall_at_k(ranking, labels, 10) == pytest.approx(2 / 3)


def test_ndcg_at_5_uses_graded_relevance():
    labels = {"best": 2, "partial": 1, "not_relevant": 0}
    ideal_dcg = 3 + 1 / math.log2(3)
    observed_dcg = 1 + 3 / math.log2(3)

    assert ndcg_at_k(["partial", "best", "not_relevant"], labels, 5) == pytest.approx(
        observed_dcg / ideal_dcg
    )


def test_empty_ranking_has_zero_metrics_when_labels_are_complete():
    result = evaluate_job_ranking([], pd.DataFrame({"candidate_id": [], "relevance_label": []}))

    assert result["evaluation_status"] == "empty_ranking"
    assert result["precision_at_5"] == 0.0
    assert result["recall_at_10"] == 0.0
    assert result["ndcg_at_5"] == 0.0


def test_missing_evaluation_labels_mark_job_incomplete():
    result = evaluate_job_ranking(
        ["a", "b"],
        pd.DataFrame({"candidate_id": ["a", "b"], "relevance_label": [2, None]}),
    )

    assert result["evaluation_status"] == "incomplete_labels"
    assert math.isnan(result["precision_at_5"])
    assert result["num_missing_labels"] == 1


def test_metric_functions_reject_unknown_labels():
    with pytest.raises(ValueError, match="must be 0, 1, or 2"):
        precision_at_k(["a"], {"a": 3})


def test_macro_average_uses_only_fully_labeled_jobs(monkeypatch):
    from ml_project import evaluation

    def fixed_ranking(description, candidates):
        return pd.DataFrame({"candidate_id": ["a", "b"]})

    monkeypatch.setattr(evaluation, "match_candidates", fixed_ranking)
    jobs = pd.DataFrame(
        {"job_id": ["J1", "J2"], "job_title": ["One", "Two"], "description": ["x", "y"]}
    )
    candidates = pd.DataFrame()
    judgments = pd.DataFrame(
        {
            "job_id": ["J1", "J1", "J2", "J2"],
            "candidate_id": ["a", "b", "a", "b"],
            "relevance_label": [2, 0, 2, None],
        }
    )

    result = evaluate_baseline(jobs, candidates, judgments)

    macro = result.iloc[-1]
    assert result.loc[0, "evaluation_status"] == "complete"
    assert result.loc[1, "evaluation_status"] == "incomplete_labels"
    assert macro["evaluation_status"] == "macro_average"
    assert macro["precision_at_5"] == pytest.approx(1 / 5)
    assert macro["recall_at_10"] == pytest.approx(1.0)
    assert macro["ndcg_at_5"] == pytest.approx(1.0)
