import pytest

from ml_project.matching_signals import (
    assess_candidate,
    combined_score,
    experience_compatibility,
    location_compatibility,
    normalize_skill,
    skill_coverage,
)


def test_normalize_skill_alias():
    assert normalize_skill("JS") == "javascript"
    assert normalize_skill("  React.js ") == "react"
    assert normalize_skill("ASP NET") == "asp.net"


def test_skill_coverage_aliases():
    result = skill_coverage("JavaScript; Python; React", "JS; py; react.js")
    assert result["skill_coverage_percent"] == 100.0


def test_experience_exact_minimum():
    assert experience_compatibility(2, 2) == "Meets minimum"


def test_experience_below():
    assert experience_compatibility(2, 1) == "Below minimum"


def test_experience_above():
    assert experience_compatibility(2, 3) == "Meets minimum"


def test_experience_missing_candidate():
    assert experience_compatibility(2, None) == "Unknown"


def test_experience_missing_job():
    assert experience_compatibility(None, 3) == "Unknown"


def test_combined_score_max():
    assert combined_score(1.0, 100.0, "Meets minimum", "Exact match") == 100.0


def test_combined_score_zero():
    assert combined_score(0.0, 0.0, "Below minimum", "Different location") == 0.0


def test_combined_score_remote():
    score = combined_score(1.0, 100.0, "Meets minimum", "Remote compatible")
    assert abs(score - 97.0) < 1e-9


def test_fully_matched_required_skills_have_full_coverage():
    result = skill_coverage(
        "Structural Analysis; ETABS; SAP2000; AutoCAD; Building Codes",
        "structural analysis; ETABS; SAP2000; AutoCAD; building codes",
    )

    assert result["skill_coverage_percent"] == 100.0
    assert result["matched_skills"] == [
        "Structural Analysis",
        "ETABS",
        "SAP2000",
        "AutoCAD",
        "Building Codes",
    ]
    assert result["missing_skills"] == []


def test_skill_matching_is_case_insensitive_but_not_substring_based():
    result = skill_coverage("React; C++; SQL", "react native; C++; SQLAlchemy")

    assert result["matched_skills"] == ["C++"]
    assert result["missing_skills"] == ["React", "SQL"]
    assert result["skill_coverage_percent"] == pytest.approx(100 / 3)


def test_experience_compatibility_reports_requirement_without_claiming_qualification():
    assert experience_compatibility(5, 6) == "Meets minimum"
    assert experience_compatibility(5, 4) == "Below minimum"
    assert experience_compatibility(None, 4) == "Unknown"


def test_location_compatibility_is_conservative():
    assert location_compatibility("Lahore, Pakistan", "lahore, pakistan") == "Exact match"
    assert location_compatibility("Remote, Pakistan", "Karachi, Pakistan") == "Remote compatible"
    assert location_compatibility("Lahore, Pakistan", "Karachi, Pakistan") == "Different location"
    assert location_compatibility("", "Karachi, Pakistan") == "Unknown"


def test_assessment_returns_separate_evidence_fields():
    result = assess_candidate(
        {"required_skills": "Python; SQL", "min_experience": 3, "location": "Remote"},
        {"skills": "Python", "experience_years": 4, "location": "Lahore"},
    )

    assert result["skill_coverage_percent"] == 50.0
    assert result["experience_compatibility"] == "Meets minimum"
    assert result["location_compatibility"] == "Remote compatible"
    assert "combined_score" not in result
