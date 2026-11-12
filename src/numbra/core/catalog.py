"""Seeded arithmetic construction and finite topic catalogs for mental arithmetic."""

from __future__ import annotations

import random
from collections.abc import Iterable
from fractions import Fraction
from functools import lru_cache
from math import isqrt

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


def _chain_terms(tree: Expr) -> tuple[Expr, ...]:
    if tree.kind in {"+", "-"}:
        return (*_chain_terms(tree.args[0]), *_chain_terms(tree.args[1]))
    return (tree,)


def _equal_term_chain(tree: Expr) -> bool:
    """Rejects 'log_3 9 + log_2 4 + 2': three or more additive terms that all have one value."""
    if tree.kind not in {"+", "-"}:
        return False
    terms = _chain_terms(tree)
    return len(terms) >= 3 and len({term.evaluate() for term in terms}) == 1


def accepted(tree: Expr, max_result: int) -> bool:
    try:
        return valid_bounds(tree, max_result) and meaningful(tree) and not _equal_term_chain(tree)
    except (ValueError, ZeroDivisionError, OverflowError):
        return False


def build_arithmetic(
    rng: random.Random,
    terms: int,
    minimum: int,
    maximum: int,
    max_result: int,
    operations: tuple[Operation, ...],
    operation_weights: dict[Operation, float],
    dividend_limit: int,
    quotient_minimum: int,
) -> Expr | None:
    """Build one bounded arithmetic tree, with division constructed from its quotient."""
    minimum = max(1, minimum)
    if terms < 2 or maximum < minimum or not operations:
        return None

    used_division = False
    operation_uses: dict[Operation, int] = {op: 0 for op in operations}

    def leaf(upper: int = maximum) -> Expr | None:
        upper = min(maximum, upper)
        return N(rng.randint(minimum, upper)) if upper >= minimum else None

    def multiply(left: Expr) -> Expr | None:
        value = left.evaluate()
        if value.denominator != 1:
            return None
        upper = max_result if value == 0 else max_result // abs(value.numerator)
        right = leaf(upper)
        return B("*", left, right) if right is not None else None

    def choose(
        *, top: bool = False, allow_division: bool = True, allow_power: bool = False
    ) -> Operation | None:
        choices = tuple(
            op
            for op in operations
            if (op is not Operation.DIVIDE or allow_division)
            and (op is not Operation.POWER or allow_power)
        )
        if not choices:
            return None
        additive = tuple(op for op in choices if op in (Operation.ADD, Operation.SUBTRACT))
        if top and additive:
            choices = additive
        selected = rng.choices(
            choices,
            weights=[
                operation_weights.get(op, 1.0)
                / (1 + operation_uses[op])
                * (2 if top and op in (Operation.ADD, Operation.SUBTRACT) else 1)
                for op in choices
            ],
        )[0]
        operation_uses[selected] += 1
        return selected

    def divide(left: Expr) -> Expr | None:
        nonlocal used_division
        divisor_minimum = max(2, minimum)
        if quotient_minimum > maximum:
            return None
        if left.kind == "number":
            divisor_maximum = min(
                maximum, dividend_limit // quotient_minimum, max_result // quotient_minimum
            )
            if divisor_maximum < divisor_minimum:
                return None
            divisor = rng.choice(range(divisor_minimum, divisor_maximum + 1))
            quotient = rng.randint(
                quotient_minimum,
                min(maximum, dividend_limit // divisor, max_result // divisor),
            )
            left = N(divisor * quotient)
        else:
            value = left.evaluate()
            if value.denominator != 1 or value <= 0 or value > min(dividend_limit, max_result):
                return None
            dividend = value.numerator
            valid_divisors: set[int] = set()
            # Reject an oversized dividend before the factor scan.
            for factor in range(1, isqrt(dividend) + 1):
                if dividend % factor:
                    continue
                for divisor in (factor, dividend // factor):
                    quotient = dividend // divisor
                    if (
                        divisor_minimum <= divisor <= maximum
                        and quotient_minimum <= quotient <= maximum
                    ):
                        valid_divisors.add(divisor)
            if not valid_divisors:
                return None
            divisor = rng.choice(tuple(valid_divisors))
        used_division = True
        return B("/", left, N(divisor))

    def flat(count: int) -> Expr | None:
        if count == 2:
            op = choose(allow_division=not used_division, allow_power=terms == 2)
            if op is None:
                return None
            if op is Operation.POWER:
                return B("^", N(rng.randint(2, 20)), N(rng.choice((2, 3))))
            if op is Operation.DIVIDE:
                left = leaf()
                return divide(left) if left is not None else None
            if op is Operation.MULTIPLY:
                left = leaf(isqrt(max_result))
                return multiply(left) if left is not None else None
            left, right = leaf(), leaf()
            return B(op.value, left, right) if left is not None and right is not None else None
        tree = leaf()
        if tree is None:
            return None
        for _ in range(count - 1):
            op = choose(allow_division=not used_division)
            if op is None:
                return None
            if op is Operation.DIVIDE:
                divided = divide(tree)
                if divided is None:
                    return None
                tree = divided
            elif op is Operation.MULTIPLY:
                multiplied = multiply(tree)
                if multiplied is None:
                    return None
                tree = multiplied
            else:
                right = leaf()
                if right is None:
                    return None
                tree = B(op.value, tree, right)
        return tree

    def grouped() -> Expr | None:
        sizes = [3] * (terms // 3)
        if remainder := terms % 3:
            sizes.append(remainder)
        rng.shuffle(sizes)
        pieces = []
        for size in sizes:
            if (
                size == 3
                and Operation.MULTIPLY in operations
                and any(op in operations for op in (Operation.ADD, Operation.SUBTRACT))
                and rng.random() < 0.5
            ):
                inner_op = rng.choice(
                    tuple(op for op in (Operation.ADD, Operation.SUBTRACT) if op in operations)
                )
                operation_uses[inner_op] += 1
                operation_uses[Operation.MULTIPLY] += 1
                left, right = leaf(), leaf()
                if left is None or right is None:
                    return None
                pair = B(inner_op.value, left, right)
                multiplied = multiply(pair)
                if multiplied is None:
                    return None
                pieces.append(multiplied)
            else:
                piece = flat(size)
                if piece is None:
                    return None
                pieces.append(piece)
        tree = pieces[0]
        for piece in pieces[1:]:
            outer_op = choose(top=True, allow_division=False)
            if outer_op is None:
                return None
            tree = B(outer_op.value, tree, piece)
        return tree

    if terms >= 4:
        tree = grouped()
    elif terms == 3 and rng.random() < 0.25 and Operation.MULTIPLY in operations:
        additive = tuple(op for op in (Operation.ADD, Operation.SUBTRACT) if op in operations)
        if additive:
            inner_op = rng.choice(additive)
            left, right, factor = leaf(), leaf(), leaf()
            tree = (
                B("*", B(inner_op.value, left, right), factor)
                if left is not None and right is not None and factor is not None
                else None
            )
        else:
            tree = flat(terms)
    else:
        tree = flat(terms)

    if tree is None:
        return None
    rendered = tree.render()
    depth = pairs = 0
    for character in rendered:
        if character == "(":
            depth += 1
            pairs += 1
            if depth > 1:
                return None
        elif character == ")":
            depth -= 1
    if pairs > 2 or expression_operations(tree).count("/") > 1:
        return None
    if not accepted(tree, max_result) or tree.evaluate().denominator != 1:
        return None
    return tree


def _power(base: int, exponent: int, enabled: bool) -> Expr:
    if enabled:
        return B("^", N(base), N(exponent))
    result = N(base)
    for _ in range(exponent - 1):
        result = B("*", result, N(base))
    return result


def integral_forms(tree: Expr, name: str) -> Iterable[tuple[Expr, str]]:
    """A fractional atom such as sin(30) = 1/2 also yields whole multiples: 2*sin(30), 4*sin(30)."""
    denominator = tree.evaluate().denominator
    if denominator == 1:
        yield tree, name
        return
    for k in range(denominator, 3 * denominator + 1, denominator):
        yield B("*", N(k), tree), name


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
        (form, form_name)
        for tree, name in topic_atoms(topic, power_enabled)
        if accepted(tree, max_result)
        for form, form_name in integral_forms(tree, name)
        if accepted(form, max_result)
    )
    result: dict[tuple[object, ...], Problem] = {}
    values = sample(operands(minimum, min(maximum, max_result)), 6)

    def add(tree: Expr, name: str, topics: tuple[Topic, ...] = (topic,)) -> None:
        # Answers are integers outside funbox; fractional intermediates stay inside expressions.
        if accepted(tree, max_result) and tree.evaluate().denominator == 1:
            key = canonical_key(tree)
            if key not in result:
                result[key] = problem(tree, topic.value, name, topics)

    if not atoms:
        return ()

    # Two tabular functions of the same or a different enabled topic.
    partners = [(t, topic) for t, _ in atoms[:: max(1, len(atoms) // 6)][:6]]
    for other in other_topics:
        partners.extend(
            (t, other)
            for t, _ in tuple(
                (t, n) for t, n in topic_atoms(other, power_enabled) if accepted(t, max_result)
            )[:4]
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
