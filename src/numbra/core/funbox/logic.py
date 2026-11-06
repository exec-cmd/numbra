"""Boolean expressions over comparisons of small integer expressions."""

from __future__ import annotations

import operator
import random
from collections.abc import Callable
from dataclasses import dataclass

from ..models import Difficulty, Problem

SIDE_LIMIT = {Difficulty.EASY: 9, Difficulty.NORMAL: 20, Difficulty.HARD: 30}
COMPARISONS: dict[str, Callable[[int, int], bool]] = {
    "=": operator.eq,
    "!=": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}
ARITHMETIC = {"+": operator.add, "-": operator.sub, "*": operator.mul}


@dataclass(frozen=True, slots=True)
class _Node:
    """kind is "atom" (a parenthesised comparison), "not" or "bin"."""

    kind: str
    text: str
    value: bool


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    count = 1 if units == 1 else 2 if units == 2 else 3 if units <= 5 else 4
    limit = SIDE_LIMIT[difficulty]
    nodes = []
    for _ in range(count):
        node = _comparison(rng, limit, arithmetic=units >= 2)
        if units >= 3 and rng.random() < 0.4:
            node = _negate(node)
        nodes.append(node)
    root = nodes[0]
    for node in nodes[1:]:
        root = _combine(rng.choice(("and", "or")), root, node)
    return Problem(
        expression=f"{root.text}; true or false?",
        answer=root.value,
        operations=(),
        family="funbox",
        strategy="logic",
        work_units=units,
    )


def _side(rng: random.Random, limit: int, arithmetic: bool) -> tuple[str, int]:
    if arithmetic and rng.random() < 0.5:
        symbol = rng.choice(tuple(ARITHMETIC))
        left, right = rng.randint(1, limit), rng.randint(1, limit)
        return f"{left} {symbol} {right}", ARITHMETIC[symbol](left, right)
    number = rng.randint(1, limit)
    return str(number), number


def _comparison(rng: random.Random, limit: int, arithmetic: bool) -> _Node:
    left_text, left = _side(rng, limit, arithmetic)
    if rng.random() < 0.5:
        right_text, right = _side(rng, limit, arithmetic)
    else:
        # Near the left value, so the answer is not decided by the size of the numbers.
        right = max(0, left + rng.randint(-3, 3))
        right_text = str(right)
    symbol = rng.choice(tuple(COMPARISONS))
    return _Node("atom", f"({left_text} {symbol} {right_text})", COMPARISONS[symbol](left, right))


def _negate(node: _Node) -> _Node:
    text = f"not ({node.text})" if node.kind == "bin" else f"not {node.text}"
    return _Node("not", text, not node.value)


def _combine(word: str, left: _Node, right: _Node) -> _Node:
    value = left.value and right.value if word == "and" else left.value or right.value
    return _Node("bin", f"{_operand(left)} {word} {_operand(right)}", value)


def _operand(node: _Node) -> str:
    # not binds tighter than and/or, so only a nested and/or needs parentheses.
    return f"({node.text})" if node.kind == "bin" else node.text
