from __future__ import annotations

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


BASIC_OPERATIONS = (Operation.ADD, Operation.SUBTRACT, Operation.MULTIPLY, Operation.DIVIDE)


def parse_operation_selection(values: Iterable[str]) -> tuple[Operation | Topic, ...]:
    """Parse the shared CLI/config selection without treating identities as an operator."""
    selected: list[Operation | Topic] = []
    for value in values:
        try:
            item: Operation | Topic = (
                Topic(value) if value in {"sqrt", "trig", "log", "power"} else Operation(value)
            )
        except ValueError as exc:
            raise ValueError("unsupported operation; use +,-,*,/,^,sqrt,trig,log,power") from exc
        if item not in selected:
            selected.append(item)
    if not selected:
        raise ValueError("operation list must not be empty")
    return tuple(selected)


@dataclass(frozen=True, slots=True)
class Problem:
    expression: str
    answer: int | Decimal | Fraction
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
