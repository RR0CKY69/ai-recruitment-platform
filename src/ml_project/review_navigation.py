"""Pure helpers for maintaining a valid review-pair selection across filters."""

from __future__ import annotations


def selected_pair(choices: list[str], current: str | None) -> str | None:
    """Keep the current pair when available; otherwise select the first filtered pair."""
    if not choices:
        return None
    return current if current in choices else choices[0]


def adjacent_pair(choices: list[str], current: str | None, direction: int) -> str | None:
    """Move one place in the filtered ordering, staying put at either boundary."""
    if direction not in {-1, 1}:
        raise ValueError("direction must be -1 (previous) or 1 (next).")
    if not choices:
        return None
    valid_current = selected_pair(choices, current)
    position = choices.index(valid_current)
    next_position = min(max(position + direction, 0), len(choices) - 1)
    return choices[next_position]
