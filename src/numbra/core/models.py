from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class Difficulty(StrEnum):
    VERY_EASY = "very-easy"
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"
    VERY_HARD = "very-hard"


class Operation(StrEnum):
    ADD = "+"
    SUBTRACT = "-"
    MULTIPLY = "*"
    DIVIDE = "/"


class StageKind(StrEnum):
    FAST = "fast"
    NORMAL = "normal"
    SLOW = "slow"


@dataclass(frozen=True, slots=True)
class Problem:
    expression: str
    answer: int | Decimal
    operations: tuple[Operation, ...]

    def evaluate(self) -> int | Decimal:
        values = self.expression.split()
        result: int | Decimal = int(values[0])
        for index in range(1, len(values), 2):
            operation = Operation(values[index])
            operand = int(values[index + 1])
            if operation is Operation.ADD:
                result += operand
            elif operation is Operation.SUBTRACT:
                result -= operand
            elif operation is Operation.MULTIPLY:
                result *= operand
            else:
                result //= operand
        return result
