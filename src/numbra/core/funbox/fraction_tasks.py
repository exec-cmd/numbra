"""Flat chains of fractions and decimals, evaluated with the usual precedence of * and /."""

from __future__ import annotations

import random
from decimal import Decimal
from fractions import Fraction

from ..models import Difficulty, Problem

# Every term and the final answer keep a denominator of at most 12.
MAX_DENOMINATOR = 12
DENOMINATORS = {
    Difficulty.EASY: (2, 3, 4, 5, 6),
    Difficulty.NORMAL: (2, 3, 4, 5, 6, 8, 10, 12),
    Difficulty.HARD: (2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12),
}


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    leaves_count = 2 if units <= 2 else 3 if units <= 5 else 4
    for _ in range(200):
        leaves = [_leaf(rng, difficulty) for _ in range(leaves_count)]
        operators = [rng.choice("+-*/") for _ in range(leaves_count - 1)]
        total = _evaluate(leaves, operators)
        if total is None or abs(total) > 1000:
            continue
        return Problem(
            expression=f"{_render(leaves, operators)} = ?",
            answer=total,
            operations=(),
            family="funbox",
            strategy="fractions",
            work_units=units,
        )
    raise ValueError("fraction task generation exhausted its attempts")


def _leaf(rng: random.Random, difficulty: Difficulty) -> Fraction:
    denominator = rng.choice(DENOMINATORS[difficulty])
    return Fraction(rng.randint(1, 3 * denominator), denominator)


def _evaluate(leaves: list[Fraction], operators: list[str]) -> Fraction | None:
    """Usual precedence; None when a term or the total breaks the denominator cap."""
    total = Fraction(0)
    sign = 1
    term = leaves[0]
    for operator, leaf in zip(operators, leaves[1:], strict=True):
        if operator == "*":
            term *= leaf
        elif operator == "/":
            term /= leaf
        else:
            total += sign * term
            sign = 1 if operator == "+" else -1
            term = leaf
        if term.denominator > MAX_DENOMINATOR:
            return None
    total += sign * term
    return total if total.denominator <= MAX_DENOMINATOR else None


def _render(leaves: list[Fraction], operators: list[str]) -> str:
    text = _text(leaves[0])
    for operator, leaf in zip(operators, leaves[1:], strict=True):
        operand = _text(leaf)
        # "a / 1/6" would read as (a / 1) / 6, so a fraction divisor gets parentheses.
        if operator == "/" and "/" in operand:
            operand = f"({operand})"
        text += f" {operator} {operand}"
    return text


def _text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    decimal = format(Decimal(value.numerator) / Decimal(value.denominator), "f")
    # A decimal is shown only when it is exact and short; otherwise the fraction is clearer.
    if "." in decimal and len(decimal.split(".")[1]) <= 3 and Fraction(decimal) == value:
        return decimal
    return f"{value.numerator}/{value.denominator}"
