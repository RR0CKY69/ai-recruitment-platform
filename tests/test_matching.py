import pandas as pd

from ml_project.dataset_validation import validate_datasets
from ml_project.matching import match_candidates


def test_matching_returns_descending_ranked_scores_between_zero_and_one():
    candidates = pd.DataFrame(
        [
            {
                "candidate_id": "C1",
                "name": "Strong Match",
                "current_title": "Python Developer",
                "summary": "Builds Python APIs and database services.",
                "skills": "Python; REST APIs; PostgreSQL",
            },
            {
                "candidate_id": "C2",
                "name": "Partial Match",
                "current_title": "Data Analyst",
                "summary": "Works with reports and business data.",
                "skills": "SQL; Excel",
            },
            {
                "candidate_id": "C3",
                "name": "Weak Match",
                "current_title": "Accountant",
                "summary": "Prepares financial statements.",
                "skills": "audit; accounting",
            },
        ]
    )

    results = match_candidates("Python developer building REST APIs", candidates)

    assert results["candidate_id"].tolist() == ["C1", "C2", "C3"]
    assert results["similarity_score"].is_monotonic_decreasing
    assert results["similarity_score"].between(0, 1).all()


def test_empty_candidate_list_returns_empty_results():
    results = match_candidates("Python developer", pd.DataFrame())

    assert results.empty
    assert results.columns.tolist() == ["candidate_id", "name", "similarity_score"]


def test_missing_profile_text_is_safe():
    candidates = pd.DataFrame(
        [
            {"candidate_id": "C1", "name": "No Profile", "summary": None, "skills": None},
            {
                "candidate_id": "C2",
                "name": "Has Profile",
                "summary": "Python developer",
                "skills": "Python",
            },
        ]
    )

    results = match_candidates("Python developer", candidates)

    assert len(results) == 2
    assert results["similarity_score"].notna().all()
    assert results.iloc[0]["candidate_id"] == "C2"


def test_empty_text_returns_zero_scores():
    candidates = pd.DataFrame([{"candidate_id": "C1", "name": "Candidate"}])

    results = match_candidates("", candidates)

    assert results["similarity_score"].tolist() == [0.0]


def test_bundled_datasets_pass_validation():
    jobs, candidates = validate_datasets()

    assert len(jobs) == 5
    assert len(candidates) == 12