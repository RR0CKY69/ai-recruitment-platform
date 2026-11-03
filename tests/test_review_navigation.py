import pytest

from ml_project.review_navigation import adjacent_pair, selected_pair

CHOICES = ["J001 / C001", "J001 / C002", "J002 / C001"]


def test_previous_and_next_move_one_pair():
    assert adjacent_pair(CHOICES, "J001 / C002", -1) == "J001 / C001"
    assert adjacent_pair(CHOICES, "J001 / C002", 1) == "J002 / C001"


def test_first_and_last_boundaries_stay_on_current_pair():
    assert adjacent_pair(CHOICES, CHOICES[0], -1) == CHOICES[0]
    assert adjacent_pair(CHOICES, CHOICES[-1], 1) == CHOICES[-1]


def test_empty_choices_and_filter_changes_are_safe():
    assert adjacent_pair([], None, 1) is None
    assert selected_pair([], "J001 / C001") is None
    assert selected_pair(["J003 / C001"], "J001 / C001") == "J003 / C001"


def test_unknown_navigation_direction_is_rejected():
    with pytest.raises(ValueError, match="direction must be"):
        adjacent_pair(CHOICES, CHOICES[0], 0)
