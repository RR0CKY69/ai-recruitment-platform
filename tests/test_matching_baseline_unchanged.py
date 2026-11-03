import pandas as pd
import pytest

from ml_project.matching import match_candidates


def test_j001_tfidf_ranking_and_scores_remain_unchanged():
    jobs = pd.read_csv("data/jobs.csv")
    candidates = pd.read_csv("data/candidates.csv")
    job = jobs.loc[jobs["job_id"] == "J001"].iloc[0]

    result = match_candidates(job["description"], candidates)

    assert result["candidate_id"].tolist() == [
        "C001",
        "C010",
        "C009",
        "C002",
        "C006",
        "C003",
        "C012",
        "C011",
        "C008",
        "C004",
        "C007",
        "C005",
    ]
    assert result["similarity_score"].tolist() == pytest.approx(
        [
            0.3618223910628428,
            0.1348794859315859,
            0.12094211049368102,
            0.10706811229651983,
            0.09184435875266019,
            0.08921916935656472,
            0.08722332182777874,
            0.049012552893220554,
            0.026100819948401167,
            0.024549922854637415,
            0.023143732271149433,
            0.02182794765130272,
        ],
        abs=1e-12,
    )
