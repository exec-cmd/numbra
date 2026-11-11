from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction

from .expressions import Expr, parse_expression


class Difficulty(StrEnum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


class Operation(StrEnum):
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"
    POWER = "^"


class StageKind(StrEnum):
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"


class Topic(StrEnum):
    SQRT = "sqrt"
    TRIG = "trig"
    LOG = "log"
    POWER = "power"
    IDENTITIES = "identities"
    TRICKS = "tricks"


BASIC_OPERATIONS = (Operation.ADD, Operation.SUBTRACT, Operation.MULTIPLY, Operation.DIVIDE)


def parse_operation_selection(values: Iterable[str]) -> tuple[Operation | Topic, ...]:
    """Parse the shared CLI/config selection without treating identities as an operator."""
    selected: list[Operation | Topic] = []
    for value in values:
        try:
            item: Operation | Topic = (
                Topic(value)
                if value in {"sqrt", "trig", "log", "power", "tricks"}
                else Operation(value)
            )
        except ValueError as exc:
            raise ValueError(
                "unsupported operation; use +,-,*,/,^,sqrt,trig,log,power,tricks"
            ) from exc
        if item not in selected:
            selected.append(item)
    if not selected:
        raise ValueError("operation list must not be empty")
    return tuple(selected)


# Ordinary exercises are integers; funbox adds exact fractions, booleans, sets of roots and
# canonical inequalities such as "x>4".
type Answer = int | Decimal | Fraction | bool | frozenset[Fraction] | str


@dataclass(frozen=True, slots=True)
class Problem:
    expression: str
    answer: Answer
    operations: tuple[Operation, ...]
    tree: Expr | None = None
    family: str = "arithmetic"
    strategy: str = ""
    solution_steps: tuple[str, ...] = ()
    work_units: int | None = None
    topics: tuple[Topic, ...] = ()

    def as_tree(self) -> Expr:
        return self.tree if self.tree is not None else parse_expression(self.expression)

    def evaluate(self) -> Fraction:
        return self.as_tree().evaluate()


_INEQUALITY = re.compile(r"(?:x\s*)?(<=|>=|<|>)\s*([+-]?[0-9]+)")


def parse_inequality(text: str) -> tuple[str, int] | None:
    """Split "x>4", "x ≥ -2" or ">4" into an ASCII relation and an integer bound."""
    normalized = text.strip().replace("\u2264", "<=").replace("\u2265", ">=")
    match = _INEQUALITY.fullmatch(normalized)
    return None if match is None else (match.group(1), int(match.group(2)))


def format_answer(expected: Answer) -> str:
    """Render an expected answer as the CLI shows it and the database stores it."""
    if isinstance(expected, bool):
        return "true" if expected else "false"
    if isinstance(expected, str):
        parsed = parse_inequality(expected)
        return expected if parsed is None else f"x {parsed[0]} {parsed[1]}"
    if isinstance(expected, frozenset):
        return ", ".join(str(item) for item in sorted(expected))
    return str(expected)
