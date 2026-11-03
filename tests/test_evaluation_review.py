from pathlib import Path

import pandas as pd
import pytest

from ml_project.evaluation_review import load_review_data, review_progress, save_human_label

PROJECT_DATA = Path(__file__).resolve().parents[1] / "data"


def _copy_review_files(destination: Path) -> None:
    for filename in ("jobs.csv", "candidates.csv", "evaluation.csv"):
        pd.read_csv(PROJECT_DATA / filename).to_csv(destination / filename, index=False)


def test_join_includes_all_pairs_and_full_job_candidate_details():
    review = load_review_data(PROJECT_DATA)

    assert len(review) == 60
    assert {"description", "required_skills", "min_experience", "job_location"}.issubset(
        review.columns
    )
    assert {"name", "current_title", "summary", "skills", "experience_years", "candidate_location"}.issubset(
        review.columns
    )
    row = review.loc[(review["job_id"] == "J002") & (review["candidate_id"] == "C003")].iloc[0]
    assert row["job_title"] == "Python Developer"
    assert row["name"] == "Sara Ahmed"
    assert "Python services" in row["description"]
    assert "REST APIs" in row["required_skills"]


def test_save_label_updates_only_target_pair_and_preserves_existing_labels(tmp_path):
    _copy_review_files(tmp_path)
    evaluations_path = tmp_path / "evaluation.csv"
    evaluations = pd.read_csv(evaluations_path)
    evaluations["relevance_label"] = pd.NA
    evaluations["label_review_status"] = "needs_human_review"
    evaluations.loc[(evaluations["job_id"] == "J001") & (evaluations["candidate_id"] == "C001"),
                    ["relevance_label", "label_review_status"]] = [2, "reviewed"]
    evaluations.to_csv(evaluations_path, index=False)
    pd.DataFrame(
        [
            {"job_id": "J001", "candidate_id": "C001", "reviewer_notes": "Keep this existing note."}
        ]
    ).to_csv(tmp_path / "evaluation_notes.csv", index=False)

    save_human_label(tmp_path, "J002", "C003", 2, "Clear match from experience and skills.")

    updated = pd.read_csv(evaluations_path)
    original_pair = updated.loc[(updated["job_id"] == "J001") & (updated["candidate_id"] == "C001")].iloc[0]
    saved_pair = updated.loc[(updated["job_id"] == "J002") & (updated["candidate_id"] == "C003")].iloc[0]
    pending_pair = updated.loc[(updated["job_id"] == "J002") & (updated["candidate_id"] == "C001")].iloc[0]
    assert original_pair["relevance_label"] == 2
    assert original_pair["label_review_status"] == "reviewed"
    assert saved_pair["relevance_label"] == 2
    assert saved_pair["label_review_status"] == "reviewed"
    assert pd.isna(pending_pair["relevance_label"])
    assert pending_pair["label_review_status"] == "needs_human_review"

    notes = pd.read_csv(tmp_path / "evaluation_notes.csv")
    preserved_note = notes.loc[
        (notes["job_id"] == "J001") & (notes["candidate_id"] == "C001"), "reviewer_notes"
    ].iloc[0]
    saved_note = notes.loc[
        (notes["job_id"] == "J002") & (notes["candidate_id"] == "C003"), "reviewer_notes"
    ].iloc[0]
    assert saved_note == "Clear match from experience and skills."
    assert preserved_note == "Keep this existing note."
    reopened = load_review_data(tmp_path)
    saved_review = reopened.loc[
        (reopened["job_id"] == "J002") & (reopened["candidate_id"] == "C003")
    ].iloc[0]
    assert saved_review["reviewer_notes"] == "Clear match from experience and skills."


def test_invalid_labels_are_rejected_without_changing_csv(tmp_path):
    _copy_review_files(tmp_path)
    before = (tmp_path / "evaluation.csv").read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="Relevance label must be 0"):
        save_human_label(tmp_path, "J001", "C001", 3)

    assert (tmp_path / "evaluation.csv").read_text(encoding="utf-8") == before


def test_pending_records_stay_incomplete_and_progress_counts_only_reviewed():
    review = load_review_data(PROJECT_DATA)
    review["relevance_label"] = pd.NA
    review["label_review_status"] = "needs_human_review"
    first_index = review.index[0]
    review.loc[first_index, "relevance_label"] = 1
    review.loc[first_index, "label_review_status"] = "reviewed"

    progress = review_progress(review)

    assert progress["total"] == 60
    assert progress["reviewed"] == 1
    assert progress["pending"] == 59
    assert progress["completion_percent"] == pytest.approx(100 / 60)
    first_job = progress["by_job"].loc[progress["by_job"]["job_id"] == "J001"].iloc[0]
    assert first_job["reviewed_combinations"] == 1
    assert first_job["pending_combinations"] == 11
