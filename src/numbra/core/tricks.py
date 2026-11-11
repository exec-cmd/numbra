"""Mental-math tricks: one strategy per problem, explicit work units, bounded catalogs.

Units are assigned per trick instead of by the general heuristic, because a trick
makes large-looking numbers cheap (37 * 99 is easy once seen as 3700 - 37).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from .catalog import accepted, problem
from .expressions import Expr, canonical_key
from .models import Problem, Topic

N = Expr.number
B = Expr.binary


@dataclass(frozen=True, slots=True)
class TrickInfo:
    id: str
    rule: str
    example: str


TRICKS = (
    TrickInfo("times-5", "Multiply by 10, then halve.", "48 * 5 = 480 / 2 = 240"),
    TrickInfo("times-25", "Multiply by 100, then divide by 4.", "36 * 25 = 3600 / 4 = 900"),
    TrickInfo("times-50", "Multiply by 100, then halve.", "64 * 50 = 6400 / 2 = 3200"),
    TrickInfo(
        "times-11", "Keep the outer digits, insert the sums of neighbours.", "43 * 11 = 4|7|3 = 473"
    ),
    TrickInfo(
        "near-round-multiply", "Use 10 - 1, 100 - 1 or 100 + 1.", "37 * 99 = 3700 - 37 = 3663"
    ),
    TrickInfo(
        "near-round-add", "Round one number, then correct.", "298 + 457 = 300 + 457 - 2 = 755"
    ),
    TrickInfo("complement", "Take each digit from 9 and the last one from 10.", "1000 - 376 = 624"),
    TrickInfo(
        "round-and-adjust",
        "Multiply by the round neighbour, then correct.",
        "49 * 21 = 50 * 21 - 21 = 1029",
    ),
    TrickInfo(
        "square-ending-5", "For a5 squared write a * (a + 1), then 25.", "65 * 65 = 42|25 = 4225"
    ),
    TrickInfo("double-halve", "Halve one factor and double the other.", "16 * 35 = 8 * 70 = 560"),
    TrickInfo(
        "divide-by-5-or-25",
        "Divide by 5 as * 2 / 10, by 25 as * 4 / 100.",
        "735 / 5 = 1470 / 10 = 147",
    ),
    TrickInfo(
        "same-decade",
        "Same tens, units sum to 10: t * (t + 1), then the units product.",
        "43 * 47 = 20|21 = 2021",
    ),
    TrickInfo(
        "near-100",
        "Subtract one deficit from the other number, then write the deficits' product.",
        "97 * 94 = 91|18 = 9118",
    ),
    TrickInfo(
        "square-near-50", "25 plus the offset, then the offset squared.", "48 * 48 = 23|04 = 2304"
    ),
    TrickInfo(
        "square-near-round",
        "Move both factors to the round neighbour and back, then add the step squared.",
        "38 * 38 = 40 * 36 + 4 = 1444",
    ),
    TrickInfo(
        "difference-of-squares",
        "Around a round middle: the middle squared minus the offset squared.",
        "48 * 52 = 2500 - 4 = 2496",
    ),
    TrickInfo("times-15", "Multiply by 10, then add half of that.", "47 * 15 = 470 + 235 = 705"),
    TrickInfo("times-125", "Multiply by 1000, then divide by 8.", "48 * 125 = 48000 / 8 = 6000"),
    TrickInfo(
        "divide-by-4-or-8", "Halve twice for 4, three times for 8.", "372 / 4 = 186 / 2 = 93"
    ),
    TrickInfo(
        "tens-sum-10",
        "Same units, tens sum to 10: tens product plus the unit, then the unit squared.",
        "37 * 77 = 28|49 = 2849",
    ),
    TrickInfo(
        "times-teens",
        "Multiply by 10, then add the number times the units digit.",
        "34 * 12 = 340 + 68 = 408",
    ),
    TrickInfo(
        "divide-by-11",
        "Undo times 11: the outer digits of the dividend, less any carry, give the quotient.",
        "572 / 11 = 5|2 = 52",
    ),
    TrickInfo("times-75", "Multiply by 3, then by 25.", "37 * 75 = 111 * 25 = 2775"),
    TrickInfo(
        "divide-by-50-or-125",
        "Divide by 50 as * 2 / 100, by 125 as * 8 / 1000.",
        "3250 / 125 = 26000 / 1000 = 26",
    ),
)


def _plain(low: int, high: int, step: int = 1) -> range | tuple[int, ...]:
    """Numbers without a trailing zero, where most tricks degenerate."""
    return tuple(n for n in range(low, high, step) if n % 10)


def _candidates() -> Iterator[tuple[Expr, str, int]]:
    # Pattern-specific tricks come first: the first trick to claim a problem keeps it,
    # and 88 * 89 is a near-100 problem even though round-and-adjust also builds it.
    for n in range(15, 100, 10):
        yield B("*", N(n), N(n)), "square-ending-5", 2 if n <= 45 else 3
    for tens in range(1, 10):
        for unit in range(1, 5):
            a, b = 10 * tens + unit, 10 * tens + 10 - unit
            units = 2 if tens == 1 else 3 if tens <= 4 else 4
            yield B("*", N(a), N(b)), "same-decade", units
    for a in range(88, 100):
        for b in range(a, 100):
            yield B("*", N(a), N(b)), "near-100", 4 if a >= 95 else 5
    for n in range(41, 60):
        if n not in (45, 50, 55):
            yield B("*", N(n), N(n)), "square-near-50", 3 if abs(n - 50) <= 3 else 4
    # Squares near 50 and 100 are claimed above; the rest go through the nearest ten.
    for n in _plain(13, 100):
        if n % 5:
            step = min(n % 10, 10 - n % 10)
            yield B("*", N(n), N(n)), "square-near-round", (2 if n < 20 else 3) + (step > 2)
    # Before round-and-adjust, which would otherwise take 49 * 51.
    for middle in range(20, 110, 10):
        for offset in range(1, 5):
            units = 2 if middle <= 30 else 3 if middle <= 60 else 4
            yield B("*", N(middle - offset), N(middle + offset)), "difference-of-squares", units
    for n in _plain(12, 2000):
        units = (1 if n % 2 == 0 else 2) if n < 100 else 3 if n < 1000 else 4
        yield B("*", N(n), N(5)), "times-5", units
    for n in _plain(12, 400):
        yield B("*", N(n), N(25)), "times-25", (2 if n % 4 == 0 else 3) if n < 100 else 4
    for n in _plain(12, 200):
        yield B("*", N(n), N(50)), "times-50", (1 if n % 2 == 0 else 2) if n < 100 else 3
    # After times-25, which keeps 25 * 125.
    for n in _plain(12, 81):
        yield B("*", N(n), N(125)), "times-125", 3 if n % 8 == 0 else 4
    # Odd factors only: double-halve owns an even number times 15.
    for n in _plain(11, 667, 2):
        yield B("*", N(n), N(15)), "times-15", 2 if n < 100 else 3
    for n in _plain(12, 910):
        units = (1 if n // 10 + n % 10 < 10 else 2) if n < 100 else 4
        yield B("*", N(n), N(11)), "times-11", units
    for n in _plain(12, 100):
        for factor, units in ((9, 2), (101, 2), (99, 3)):
            yield B("*", N(n), N(factor)), "near-round-multiply", units
    sizes = (
        (2, range(20, 100, 10), _plain(13, 100, 7)),
        (3, range(100, 1000, 100), _plain(117, 1000, 61)),
        (4, range(1000, 5000, 1000), _plain(1234, 10000, 577)),
    )
    for units, rounds, others in sizes:
        for r in rounds:
            for a in (r - 2, r - 1, r + 1, r + 2):
                for b in others:
                    yield B("+", N(a), N(b)), "near-round-add", units
                    if b > a:
                        yield B("-", N(b), N(a)), "near-round-add", units + 1
    for whole, parts, units in (
        (100, _plain(11, 100), 1),
        (1000, _plain(103, 1000, 7), 2),
        (10000, _plain(1003, 10000, 71), 4),
    ):
        for n in parts:
            yield B("-", N(whole), N(n)), "complement", units
    for rounds, units in ((range(20, 100, 10), 3), (range(200, 1000, 100), 5)):
        for r in rounds:
            for a in (r - 1, r + 1):
                for m in _plain(12, 100):
                    yield B("*", N(a), N(m)), "round-and-adjust", units
    # 25 and 50 are excluded: those products belong to times-25 and times-50.
    for e in (*range(12, 100, 2), *range(102, 1000, 2)):
        if e % 10:
            for f in (15, 35, 45, 55, 65, 75, 85, 95):
                yield B("*", N(e), N(f)), "double-halve", 2 if e < 100 else 3
    for divisor, small, large in ((5, 2, 3), (25, 3, 4)):
        for quotient in range(3, 2000):
            dividend = divisor * quotient
            if dividend % 100:
                units = small if dividend < 1000 else large
                yield B("/", N(dividend), N(divisor)), "divide-by-5-or-25", units
    for divisor, small, large in ((4, 2, 3), (8, 3, 4)):
        for quotient in range(13, 1250):
            dividend = divisor * quotient
            if dividend % 100:
                units = small if dividend < 1000 else large
                yield B("/", N(dividend), N(divisor)), "divide-by-4-or-8", units
    for a in range(1, 10):
        c = 10 - a
        if a < c:
            for unit in range(1, 10):
                yield (
                    B("*", N(10 * a + unit), N(10 * c + unit)),
                    "tens-sum-10",
                    3 if a == 1 else 4,
                )
    for k in (12, 13, 14, 16, 17, 18):
        for x in _plain(12, 100):
            yield B("*", N(x), N(k)), "times-teens", 2 if x < 25 else 3
    for q in _plain(12, 100):
        yield B("/", N(11 * q), N(11)), "divide-by-11", 2 if sum(divmod(q, 10)) < 10 else 3
    for x in _plain(13, 100, 2):
        yield B("*", N(x), N(75)), "times-75", 4
    for q in range(3, 200, 2):
        dividend = 50 * q
        yield B("/", N(dividend), N(50)), "divide-by-50-or-125", 2 if dividend < 1000 else 3
    for q in range(3, 81):
        if q % 8:
            dividend = 125 * q
            yield (
                B("/", N(dividend), N(125)),
                "divide-by-50-or-125",
                3 if dividend < 1000 else 4,
            )


@lru_cache(maxsize=8)
def trick_catalog(max_result: int) -> tuple[Problem, ...]:
    """Every trick problem within max_result; the first trick to claim a problem keeps it."""
    result: dict[tuple[object, ...], Problem] = {}
    for tree, strategy, units in _candidates():
        key = canonical_key(tree)
        if key not in result and accepted(tree, max_result):
            result[key] = problem(tree, "tricks", strategy, (Topic.TRICKS,), units)
    return tuple(result.values())
