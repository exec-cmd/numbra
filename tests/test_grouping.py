from __future__ import annotations

import random

from numbra.core.expressions import parse_expression
from numbra.core.grouping import group_terms


def _strip_groups(text: str) -> str:
    return text.replace("(", "").replace(")", "")


def test_five_term_chain_is_grouped_without_changing_value() -> None:
    text = "12 + 7 - 5 + 9 - 3 + 8"
    grouped = group_terms(text, random.Random(4))
    assert "(" in grouped
    assert parse_expression(grouped).evaluate() == parse_expression(text).evaluate()


def test_grouping_respects_run_rules_and_short_chains() -> None:
    grouped = group_terms("1 + 2 - 3 + 4 - 5 + 6", random.Random(2))
    assert " - (" not in grouped
    assert grouped.count("(") <= 2
    nested = group_terms("(1 + 2) + 3 + 4 + 5", random.Random(0))
    assert nested.startswith("(1 + 2)")
    assert "((1 + 2)" not in nested
    assert group_terms("1 + 2 - 3", random.Random(0)) == "1 + 2 - 3"


def test_missing_number_groups_only_left_side() -> None:
    grouped = group_terms("12 + ? - 5 + 9 - 3 = 18", random.Random(4))
    lhs, answer = grouped.split(" = ")
    assert "(" in lhs
    assert "(" not in answer
    assert answer == "18"
    assert _strip_groups(lhs) == "12 + ? - 5 + 9 - 3"
