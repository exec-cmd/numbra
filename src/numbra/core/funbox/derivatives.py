"""Derivative at a point for polynomials of degree 2 or 3 with integer coefficients."""

from __future__ import annotations

import random

from ..models import Difficulty, Problem
from .text import polynomial_text

# (largest leading coefficient, largest other coefficient, largest point)
RANGES = {
    Difficulty.EASY: (4, 6, 3),
    Difficulty.NORMAL: (3, 9, 4),
    Difficulty.HARD: (5, 12, 5),
}


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    lead_max, other_max, point_max = RANGES[difficulty]
    degree = 2 if difficulty is Difficulty.EASY else 3
    lead = rng.choice([value for value in range(-lead_max, lead_max + 1) if value])
    # Ascending coefficients: constant, the middle terms, then the leading one.
    coefficients = [
        rng.randint(-9, 9),
        *(rng.randint(-other_max, other_max) for _ in range(degree - 1)),
        lead,
    ]
    point = rng.randint(-point_max, point_max)
    answer = sum(
        power * coefficient * point ** (power - 1)
        for power, coefficient in enumerate(coefficients)
        if power > 0
    )
    return Problem(
        expression=f"f(x) = {polynomial_text(coefficients)}; f'({point}) = ?",
        answer=answer,
        operations=(),
        family="funbox",
        strategy="derivatives",
        work_units=units,
    )
