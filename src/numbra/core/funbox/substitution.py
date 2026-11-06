"""Letter expressions with given values, and physics formulas that need one substitution."""

from __future__ import annotations

import random
from math import prod

from ..models import Difficulty, Problem

VALUE_RANGE = {
    Difficulty.EASY: (1, 9),
    Difficulty.NORMAL: (1, 12),
    Difficulty.HARD: (2, 15),
}
LETTERS = {Difficulty.EASY: "ab", Difficulty.NORMAL: "abc", Difficulty.HARD: "abc"}

# (formula, target, factors): the target is the product of the factors, except "v = s / t".
PRODUCT_FORMULAS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("F = m * a", "F", ("m", "a")),
    ("P = U * I", "P", ("U", "I")),
    ("s = v * t", "s", ("v", "t")),
    ("p = m * v", "p", ("m", "v")),
)
ENERGY_FORMULA: tuple[str, str, tuple[str, ...]] = ("E = m * g * h", "E", ("m", "g", "h"))
CONSTANTS = {"g": 10}


def make(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    if rng.random() < 0.5:
        return _letter_expression(rng, difficulty, units)
    return _physics(rng, difficulty, units)


def _letter_expression(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    terms_count = 2 if units <= 2 else 3 if units <= 5 else 4
    max_power = 1 if units == 1 else 2 if units <= 5 else 3
    letters = LETTERS[difficulty]
    terms: list[tuple[int, int, str, list[tuple[str, int]]]] = []
    for _ in range(terms_count):
        names = sorted(rng.sample(letters, 2 if units >= 3 and rng.random() < 0.5 else 1))
        powers = [(name, rng.randint(1, max_power)) for name in names]
        coefficient = rng.randint(1, 9)
        sign = rng.choice((1, -1))
        monomial = "".join(name if power == 1 else f"{name}^{power}" for name, power in powers)
        text = monomial if coefficient == 1 else f"{coefficient}{monomial}"
        terms.append((sign, coefficient, text, powers))
    expression = ""
    for index, (sign, _, text, _) in enumerate(terms):
        if index == 0:
            expression += ("-" if sign < 0 else "") + text
        else:
            expression += f" {'+' if sign > 0 else '-'} {text}"
    used = sorted({name for *_, powers in terms for name, _ in powers})
    values = {name: rng.randint(*VALUE_RANGE[difficulty]) for name in used}
    total = sum(
        sign * coefficient * prod(values[name] ** power for name, power in powers)
        for sign, coefficient, _, powers in terms
    )
    givens = ", ".join(f"{name} = {values[name]}" for name in used)
    return Problem(
        expression=f"{expression}; {givens}; value = ?",
        answer=total,
        operations=(),
        family="funbox",
        strategy="substitution",
        work_units=units,
    )


def _physics(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    low, high = VALUE_RANGE[difficulty]
    if units >= 3 and rng.random() < 0.5:
        formula, target, factors = ENERGY_FORMULA
    elif rng.random() < 0.25:
        return _quotient(rng, difficulty, units)
    else:
        formula, target, factors = rng.choice(PRODUCT_FORMULAS)
    values = {name: CONSTANTS.get(name) or rng.randint(low, high) for name in factors}
    answer = prod(values.values())
    givens = ", ".join(f"{name} = {values[name]}" for name in factors)
    return Problem(
        expression=f"{formula}; {givens}; {target} = ?",
        answer=answer,
        operations=(),
        family="funbox",
        strategy="substitution",
        work_units=units,
    )


def _quotient(rng: random.Random, difficulty: Difficulty, units: int) -> Problem:
    """v = s / t with s = v * t, so the quotient is always a whole number."""
    low, high = VALUE_RANGE[difficulty]
    divisor = rng.randint(max(2, low), high)
    quotient = rng.randint(max(2, low), 2 * high)
    dividend = quotient * divisor
    return Problem(
        expression=f"v = s / t; s = {dividend}, t = {divisor}; v = ?",
        answer=quotient,
        operations=(),
        family="funbox",
        strategy="substitution",
        work_units=units,
    )
