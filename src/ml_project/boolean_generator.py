"""Generate a basic Boolean query from a delimited required-skills field."""

from __future__ import annotations


def generate_boolean_query(required_skills: str) -> str:
    """Combine listed skills with AND; quote multiword skills for search engines."""
    skills = [skill.strip() for skill in (required_skills or "").split(";") if skill.strip()]
    terms = [f'"{skill}"' if " " in skill else skill for skill in skills]
    return " AND ".join(terms)