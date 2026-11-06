"""Linear equations, linear inequalities and quadratics with integer roots."""

from __future__ import annotations

import random
from fractions import Fraction

from ..models import Difficulty, Problem
from .text import polynomial_text

ROOT_SPAN = {Difficulty.EASY: 5, Difficulty.NORMAL: 9, Difficulty.HARD: 12}
FLIPPED = {">": "<", "<": ">", ">=": "<=", "<=": ">="}


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    kinds = (
        ("linear", "inequality")
        if difficulty is Difficulty.EASY
        else (
            "linear",
            "inequality",
            "quadratic",
        )
    )
    kind = rng.choice(kinds)
    span = ROOT_SPAN[difficulty]
    if kind == "linear":
        return _linear(rng, span, units)
    if kind == "inequality":
        return _inequality(rng, span, units)
    return _quadratic(rng, span, units)


def inequality_answer(slope: int, relation: str, root: int) -> str:
    """Canonical answer for slope*x + c REL bound, where bound = slope*root + c."""
    # Dividing by a negative slope reverses the relation.
    return f"x{FLIPPED[relation] if slope < 0 else relation}{root}"


def _linear(rng: random.Random, span: int, units: int) -> Problem:
    root = rng.randint(-span, span)
    slope = rng.choice([value for value in range(-9, 10) if value])
    constant = rng.randint(-9, 9)
    left = polynomial_text([constant, slope])
    if units >= 3 and rng.random() < 0.5:
        other = rng.choice([value for value in range(-9, 10) if value not in (0, slope)])
        right = polynomial_text([constant + (slope - other) * root, other])
    else:
        right = str(slope * root + constant)
    return Problem(
        expression=f"{left} = {right}; x = ?",
        answer=root,
        operations=(),
        family="funbox",
        strategy="equations",
        work_units=units,
    )


def _inequality(rng: random.Random, span: int, units: int) -> Problem:
    root = rng.randint(-span, span)
    slope = rng.choice([value for value in range(-5, 6) if value])
    constant = rng.randint(-9, 9)
    relation = rng.choice((">", "<", ">=", "<="))
    bound = slope * root + constant
    return Problem(
        expression=f"{polynomial_text([constant, slope])} {relation} {bound}; solve for x",
        answer=inequality_answer(slope, relation, root),
        operations=(),
        family="funbox",
        strategy="equations",
        work_units=units,
    )


def _quadratic(rng: random.Random, span: int, units: int) -> Problem:
    # Two roots drawn in order; equal values give a double root, typed once.
    first, second = sorted(rng.randint(-span, span) for _ in range(2))
    return Problem(
        expression=f"{polynomial_text([first * second, -(first + second), 1])} = 0; roots = ?",
        answer=frozenset({Fraction(first), Fraction(second)}),
        operations=(),
        family="funbox",
        strategy="equations",
        work_units=units,
    )
