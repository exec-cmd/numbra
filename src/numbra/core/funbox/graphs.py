"""Graph tasks: place a point on a figure, or read a line or vertex from one. TUI only."""

from __future__ import annotations

import random
from fractions import Fraction
from typing import Literal

from ..models import Difficulty, GraphSpec, Problem
from .text import polynomial_text

# Every point a task shows (the placed point, sampled line points, vertex) lies in -10..10.
GRID = 10


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    if rng.random() < 0.5:
        return _place(rng, difficulty, units)
    return _read(rng, difficulty, units)


def _place(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    figure: Literal["line", "parabola"] = (
        "line" if difficulty is Difficulty.EASY or rng.random() < 0.5 else "parabola"
    )
    for _ in range(500):
        coefficients = _line(rng) if figure == "line" else _parabola(rng)[0]
        x = rng.randint(-4, 4)
        y = _value(coefficients, x)
        if abs(y) <= GRID:
            return Problem(
                expression=f"place the point of y = {polynomial_text(coefficients)} at x = {x}",
                answer=(Fraction(x), Fraction(y)),
                operations=(),
                family="funbox",
                strategy="graphs",
                work_units=units,
                graph=GraphSpec("place", figure, coefficients, x),
            )
    raise ValueError("graph task generation exhausted its attempts")


def _read(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    if difficulty is Difficulty.EASY or rng.random() < 0.5:
        for _ in range(500):
            coefficients = _line(rng)
            if _within(coefficients, range(-4, 5)):
                slope, intercept = coefficients[1], coefficients[0]
                return Problem(
                    expression="read the line through the grid; answer k, b",
                    answer=(Fraction(slope), Fraction(intercept)),
                    operations=(),
                    family="funbox",
                    strategy="graphs",
                    work_units=units,
                    graph=GraphSpec("read", "line", coefficients),
                )
    coefficients, (h, k) = _parabola(rng)
    return Problem(
        expression="read the vertex of the parabola; answer h, k",
        answer=(Fraction(h), Fraction(k)),
        operations=(),
        family="funbox",
        strategy="graphs",
        work_units=units,
        graph=GraphSpec("read", "parabola", coefficients),
    )


def _line(rng: random.Random) -> tuple[int, ...]:
    slope = rng.choice((-3, -2, -1, 1, 2, 3))
    return (rng.randint(-6, 6), slope)


def _parabola(rng: random.Random) -> tuple[tuple[int, ...], tuple[int, int]]:
    """Ascending coefficients of a(x - h)^2 + k, with the vertex (h, k) in -6..6."""
    a = rng.choice((-2, -1, 1, 2))
    h = rng.randint(-3, 3)
    k = rng.randint(-6, 6)
    return (a * h * h + k, -2 * a * h, a), (h, k)


def _value(coefficients: tuple[int, ...], x: int) -> int:
    return sum(coefficient * x**power for power, coefficient in enumerate(coefficients))


def _within(coefficients: tuple[int, ...], xs: range) -> bool:
    return all(abs(_value(coefficients, x)) <= GRID for x in xs)
