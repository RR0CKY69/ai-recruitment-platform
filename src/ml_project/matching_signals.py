"""Separate, transparent candidate evidence signals; not a combined qualification score."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping

import pandas as pd


def _normalize_term(value: object) -> str:
    """Normalize case and whitespace while preserving punctuation to avoid false matches."""
    if pd.isna(value):
        return ""
    return " ".join(str(value).casefold().split())


def _split_terms(value: object) -> list[str]:
    if pd.isna(value):
        return []
    return [term.strip() for term in str(value).split(";") if term.strip()]


def skill_coverage(required_skills: object, candidate_skills: object) -> dict[str, object]:
    """Compare semicolon-separated skill terms using exact normalized term matches."""
    required = _split_terms(required_skills)
    candidate_terms = {normalize_skill(term) for term in _split_terms(candidate_skills)}
    matched = [term for term in required if normalize_skill(term) in candidate_terms]
    missing = [term for term in required if normalize_skill(term) not in candidate_terms]
    coverage = len(matched) / len(required) * 100 if required else 0.0
    return {
        "matched_skills": matched,
        "missing_skills": missing,
        "skill_coverage_percent": coverage,
    }


def experience_compatibility(required_years: object, candidate_years: object) -> str:
    """Report whether the candidate meets the stated minimum, or unknown if unavailable."""
    try:
        required = float(required_years)
        candidate = float(candidate_years)
    except (TypeError, ValueError):
        return "Unknown"
    if not math.isfinite(required) or not math.isfinite(candidate):
        return "Unknown"
    return "Meets minimum" if candidate >= required else "Below minimum"


def location_compatibility(job_location: object, candidate_location: object) -> str:
    """Compare literal locations; remote compatibility requires an explicit remote job."""
    job = _normalize_term(job_location)
    candidate = _normalize_term(candidate_location)
    if not job or not candidate:
        return "Unknown"
    if job == candidate:
        return "Exact match"
    if re.search(r"\bremote\b", job):
        return "Remote compatible"
    return "Different location"


def assess_candidate(job: Mapping[str, object], candidate: Mapping[str, object]) -> dict[str, object]:
    """Return separate skills, experience, and location evidence for display."""
    skills = skill_coverage(job.get("required_skills"), candidate.get("skills"))
    required_experience = job.get("min_experience")
    candidate_experience = candidate.get("experience_years")
    try:
        required_display = f"{float(required_experience):g} years"
    except (TypeError, ValueError):
        required_display = "Unknown"
    try:
        candidate_display = f"{float(candidate_experience):g} years"
    except (TypeError, ValueError):
        candidate_display = "Unknown"

    return {
        **skills,
        "experience_required": required_display,
        "experience_candidate": candidate_display,
        "experience_compatibility": experience_compatibility(
            required_experience, candidate_experience
        ),
        "location_compatibility": location_compatibility(
            job.get("location"), candidate.get("location")
        ),
}


SKILL_ALIASES = {
    "js": "javascript",
    "javascript": "javascript",
    "react.js": "react",
    "reactjs": "react",
    "react": "react",
    "ml": "machine learning",
    "machine learning": "machine learning",
    "nlp": "natural language processing",
    "natural language processing": "natural language processing",
    "asp.net": "asp.net",
    "asp net": "asp.net",
    "aspnet": "asp.net",
    "python": "python",
    "py": "python",
}


def normalize_skill(value: object) -> str:
    if pd.isna(value):
        return ""
    term = " ".join(str(value).casefold().split())
    return SKILL_ALIASES.get(term, term)


def combined_score(
    tfidf_similarity: float,
    skill_coverage_percent: float,
    experience_compatibility: str,
    location_compatibility: str,
) -> float:
    experience_score = 1.0 if experience_compatibility == "Meets minimum" else 0.0
    location_scores = {"Exact match": 1.0, "Remote compatible": 0.7, "Different location": 0.0, "Unknown": 0.0}
    location_score = location_scores.get(location_compatibility, 0.0)
    skill_score = (skill_coverage_percent or 0.0) / 100.0
    tfidf = tfidf_similarity or 0.0
    value = 100.0 * (0.40 * tfidf + 0.35 * skill_score + 0.15 * experience_score + 0.10 * location_score)
    return max(0.0, min(100.0, value))
