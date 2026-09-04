from __future__ import annotations

import ast
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
    POWER = "^"


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
        parsed = ast.parse(self.expression.replace("^", "**"), mode="eval")
        return _evaluate_ast(parsed.body)


def _evaluate_ast(node: ast.expr) -> int:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return node.value
    if not isinstance(node, ast.BinOp):
        raise ValueError("expression contains an unsupported value")
    left = _evaluate_ast(node.left)
    right = _evaluate_ast(node.right)
    if isinstance(node.op, ast.Add):
        return left + right
    if isinstance(node.op, ast.Sub):
        return left - right
    if isinstance(node.op, ast.Mult):
        return left * right
    if isinstance(node.op, ast.Div):
        if right == 0 or left % right:
            raise ValueError("division must be exact and non-zero")
        return left // right
    if isinstance(node.op, ast.Pow):
        if right < 0 or right > 3:
            raise ValueError("powers must use an exponent from 0 to 3")
        return left**right
    raise ValueError("expression contains an unsupported operation")
