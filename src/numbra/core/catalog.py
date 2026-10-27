"""Finite, constructive catalogs of mental-arithmetic strategies.

Domains are bounded strategic samples, not scans of the configured integer range.
A catalog is the available exercise population for a generator version.
"""

from __future__ import annotations

from collections.abc import Iterable
from fractions import Fraction
from functools import lru_cache

from .expressions import (
    Expr,
    canonical_key,
    expression_operations,
    meaningful,
    valid_bounds,
    work_units,
)
from .models import Operation, Problem, Topic

N = Expr.number
B = Expr.binary
F = Expr.function


def operands(minimum: int, maximum: int) -> tuple[int, ...]:
    """Cover small ranges exactly, large ones with at most 64 strategic values."""
    minimum = max(1, minimum)
    if maximum < minimum:
        return ()
    if maximum - minimum < 48:
        return tuple(range(minimum, maximum + 1))
    values = {minimum + (maximum - minimum) * i // 23 for i in range(24)}
    for anchor in (10, 20, 25, 50, 100, 200, 250, 500, 1000):
        for delta in (-2, -1, 0, 1, 2):
            if minimum <= anchor + delta <= maximum:
                values.add(anchor + delta)
    return tuple(sorted(values))[:64]


def sample[T](items: tuple[T, ...], count: int) -> tuple[T, ...]:
    if len(items) <= count:
        return items
    return tuple(items[i * (len(items) - 1) // (count - 1)] for i in range(count))


def problem(
    tree: Expr,
    family: str = "arithmetic",
    strategy: str = "decomposition",
    topics: tuple[Topic, ...] = (),
    units: int | None = None,
) -> Problem:
    value = tree.evaluate()
    answer: int | Fraction = value.numerator if value.denominator == 1 else value
    return Problem(
        tree.render(),
        answer,
        tuple(Operation(op) for op in expression_operations(tree)),
        tree=tree,
        family=family,
        strategy=strategy,
        solution_steps=(),
        work_units=max(1, work_units(tree) if units is None else units),
        topics=topics,
    )


def accepted(tree: Expr, max_result: int) -> bool:
    try:
        return valid_bounds(tree, max_result) and meaningful(tree)
    except (ValueError, ZeroDivisionError, OverflowError):
        return False


def multiplication_is_structured(a: int, b: int) -> bool:
    return min(a, b) <= 12 or (abs(a - b) <= 18 and (a + b) % 10 == 0) or a % 10 == b % 10 == 0


@lru_cache(maxsize=64)
def arithmetic_catalog(
    minimum: int,
    maximum: int,
    min_terms: int,
    max_terms: int,
    max_result: int,
    operations: tuple[Operation, ...],
) -> tuple[Problem, ...]:
    values = sample(operands(minimum, min(maximum, max_result)), 32)
    atoms: dict[Operation, list[Expr]] = {op: [] for op in operations}
    for op in operations:
        if op is Operation.DIVIDE:
            for divisor in values:
                if divisor < 2:
                    continue
                for quotient in operands(2, min(50, maximum // divisor)):
                    dividend = divisor * quotient
                    if minimum <= dividend <= maximum:
                        atoms[op].append(B("/", N(dividend), N(divisor)))
        else:
            for a in values:
                for b in values:
                    if op is Operation.MULTIPLY and not multiplication_is_structured(a, b):
                        continue
                    tree = B(op.value, N(a), N(b))
                    if accepted(tree, max_result):
                        atoms[op].append(tree)
    bases = {op: sample(tuple(items), 12) for op, items in atoms.items()}
    result: dict[tuple[object, ...], Problem] = {}

    def add(tree: Expr, strategy: str) -> None:
        if accepted(tree, max_result):
            key = canonical_key(tree)
            if key not in result:
                result[key] = problem(tree, strategy=strategy)

    if min_terms <= 2 <= max_terms:
        for atom_trees in atoms.values():
            for tree in atom_trees:
                add(tree, "direct")
    # Each combination adds a useful step; both expression branches can be compound.
    for op, trees in bases.items():
        for tree in trees:
            for outer in operations:
                if min_terms <= 3 <= max_terms:
                    for number in sample(values, 6):
                        if outer is Operation.DIVIDE:
                            value = tree.evaluate()
                            if number < 2 or value % number or value == number:
                                continue
                        add(B(outer.value, tree, N(number)), "successive-steps")
                        if outer is not Operation.DIVIDE:
                            add(B(outer.value, N(number), tree), "right-branch")
                if min_terms <= 4 <= max_terms:
                    for right in sample(bases[outer], 4):
                        combined = B(op.value, tree, right)
                        if op is Operation.DIVIDE:
                            divisor_value = right.evaluate()
                            if (
                                divisor_value < max(2, minimum)
                                or divisor_value > maximum
                                or tree.evaluate() % divisor_value
                            ):
                                continue
                        add(combined, "two-branches")
                    # Homogeneous subtraction/division retain left-to-right practice.
                    for a, b in zip(sample(values, 6), reversed(sample(values, 6)), strict=True):
                        partial = B(outer.value, tree, N(a))
                        combined = B(op.value, partial, N(b))
                        if outer is Operation.DIVIDE and (a < 2 or tree.evaluate() % a):
                            continue
                        if op is Operation.DIVIDE and (b < 2 or partial.evaluate() % b):
                            continue
                        add(combined, "successive-steps")
    # Construct division chains backwards: sampled forward chains can miss valid
    # narrow factor combinations, especially with divisors >= 10.
    if Operation.DIVIDE in operations:
        divisors = tuple(range(max(2, minimum), min(maximum, max(2, minimum) + 12) + 1))
        for first in divisors:
            for second in divisors:
                for quotient in range(2, 13):
                    dividend = first * second * quotient
                    if min_terms <= 3 <= max_terms and minimum <= dividend <= maximum:
                        add(B("/", B("/", N(dividend), N(first)), N(second)), "successive-division")
                    if min_terms <= 4 <= max_terms:
                        for third in divisors[:4]:
                            dividend4 = dividend * third
                            if minimum <= dividend4 <= maximum:
                                add(
                                    B(
                                        "/",
                                        B("/", B("/", N(dividend4), N(first)), N(second)),
                                        N(third),
                                    ),
                                    "successive-division",
                                )
    return tuple(result.values())


def _power(base: int, exponent: int, enabled: bool) -> Expr:
    if enabled:
        return B("^", N(base), N(exponent))
    result = N(base)
    for _ in range(exponent - 1):
        result = B("*", result, N(base))
    return result


def topic_atoms(topic: Topic, power_enabled: bool) -> Iterable[tuple[Expr, str]]:
    if topic is Topic.SQRT:
        for root in range(2, 21):
            yield F("sqrt", N(root * root)), "perfect-square"
    elif topic is Topic.TRIG:
        for function in ("sin", "cos", "tan"):
            for angle in sorted(set(range(0, 360, 30)) | {45, 135, 225, 315}):
                tree = F(function, N(angle))
                try:
                    tree.evaluate()
                except ValueError:
                    continue
                yield tree, "rational-angle"
    elif topic is Topic.LOG:
        for base in (2, 3, 5, 10):
            for exponent in range(-3, 5):
                arg = N(base**exponent) if exponent >= 0 else B("/", N(1), N(base**-exponent))
                yield F("log", N(base), arg), "inverse-power"
    elif topic is Topic.POWER:
        for base in range(2, 21):
            for exponent in (2, 3):
                yield B("^", N(base), N(exponent)), "small-power"
    else:
        for anchor in (10, 20, 50, 100):
            for delta in range(1, 10):
                yield B("*", N(anchor - delta), N(anchor + delta)), "difference-of-squares"
                for sign in (-1, 1):
                    value = anchor + sign * delta
                    yield (
                        _power(value, 2, power_enabled),
                        "square-of-sum" if sign > 0 else "square-of-difference",
                    )
                    yield (
                        _power(value, 3, power_enabled),
                        "cube-of-sum" if sign > 0 else "cube-of-difference",
                    )
                for exponent in (2, 3):
                    for operator_sign in ("+", "-"):
                        if exponent == 2 and operator_sign == "+":
                            continue
                        yield (
                            B(
                                operator_sign,
                                _power(anchor, exponent, power_enabled),
                                _power(delta, exponent, power_enabled),
                            ),
                            (
                                "difference-of-squares"
                                if exponent == 2 and operator_sign == "-"
                                else "sum-of-cubes"
                                if operator_sign == "+" and exponent == 3
                                else "difference-of-cubes"
                                if exponent == 3
                                else "sum-of-squares"
                            ),
                        )


@lru_cache(maxsize=128)
def topic_catalog(
    topic: Topic,
    minimum: int,
    maximum: int,
    max_result: int,
    operations: tuple[Operation, ...],
    power_enabled: bool,
    other_topics: tuple[Topic, ...] = (),
) -> tuple[Problem, ...]:
    atoms = tuple(
        (tree, name)
        for tree, name in topic_atoms(topic, power_enabled)
        if accepted(tree, max_result)
    )
    result: dict[tuple[object, ...], Problem] = {}
    values = sample(operands(minimum, min(maximum, max_result)), 4)

    def add(tree: Expr, name: str, topics: tuple[Topic, ...] = (topic,)) -> None:
        if accepted(tree, max_result):
            key = canonical_key(tree)
            if key not in result:
                result[key] = problem(tree, topic.value, name, topics)

    if not atoms:
        return ()

    # Two tabular functions of the same or a different enabled topic.
    partners = [(t, topic) for t, _ in atoms[:: max(1, len(atoms) // 4)][:4]]
    for other in other_topics:
        partners.extend(
            (t, other)
            for t, _ in tuple(
                (t, n) for t, n in topic_atoms(other, power_enabled) if accepted(t, max_result)
            )[:2]
        )

    for tree, name in atoms:
        add(tree, name)
        for op in operations:
            for a in values:
                expanded = B(op.value, tree, N(a))
                if op is not Operation.DIVIDE or (a >= 2 and tree.evaluate() % a == 0):
                    add(expanded, name)
                    # At most three arithmetic steps, without function nesting.
                    for second in operations:
                        b = values[(values.index(a) + 3) % len(values)]
                        expanded2 = B(second.value, expanded, N(b))
                        if second is not Operation.DIVIDE or (
                            b >= 2 and expanded.evaluate() % b == 0
                        ):
                            add(expanded2, name)
                if op is not Operation.DIVIDE:
                    add(B(op.value, N(a), tree), name)
        for right, partner_topic in partners:
            for op in operations:
                joined = B(op.value, tree, right)
                used_topics = tuple(sorted({topic, partner_topic}, key=lambda t: t.value))
                add(joined, name, used_topics)
                if Operation.ADD in operations:
                    for number in values[:3]:
                        add(B("+", joined, N(number)), name, used_topics)
    return tuple(result.values())
