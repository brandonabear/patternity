"""Basic metrics on minimal rows."""

import pytest

from patternity.analysis import count_basic
from tests.helpers import chart_rows


@pytest.mark.parametrize("head", ["2", "4"], ids=["hold", "roll"])
def test_jump_during_an_ongoing_hold_or_roll_is_a_hand(head: str) -> None:
    rows = chart_rows([f"{head}000", "0011", "3000", "0000", ","])
    assert count_basic(rows).hands == 1


def test_jump_after_the_tail_is_not_a_hand() -> None:
    rows = chart_rows(["4000", "3000", "0011", "0000", ","])
    assert count_basic(rows).hands == 0
