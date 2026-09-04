from __future__ import annotations

import ast
import random
from dataclasses import dataclass

from .models import Operation, Problem


class GenerationError(ValueError):
    """Raised when a profile cannot produce the requested examples."""


@dataclass(frozen=True, slots=True)
class DifficultyProfile:
    min_value: int
    max_value: int
    min_terms: int = 2
    max_terms: int = 2
    max_result: int = 10_000
    term_weights: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class _Node:
    text: str
    value: int
    precedence: int
    operations: tuple[Operation, ...]


_PRECEDENCE = {
    Operation.ADD: 1,
    Operation.SUBTRACT: 1,
    Operation.MULTIPLY: 2,
    Operation.DIVIDE: 2,
    Operation.POWER: 3,
}
_MAX_ATTEMPTS = 512


class ProblemGenerator:
    def __init__(
        self, profile: DifficultyProfile, operations: tuple[Operation, ...], seed: int
    ) -> None:
        if not operations:
            raise ValueError("at least one operation is required")
        if profile.min_value < 0 or profile.max_value < profile.min_value:
            raise ValueError("invalid difficulty range")
        if profile.max_value < 1 or profile.max_result < 1:
            raise ValueError("difficulty range must contain positive values")
        if profile.min_terms < 2 or profile.max_terms < profile.min_terms:
            raise ValueError("invalid term range")
        if any(terms < 2 or weight <= 0 for terms, weight in profile.term_weights):
            raise ValueError("invalid term weights")
        self.profile = profile
        self.operations = tuple(dict.fromkeys(Operation(operation) for operation in operations))
        self._random = random.Random(seed)
        self._seen: set[tuple[object, ...]] = set()

    def generate(self, complexity_range: tuple[int, int] | None = None) -> Problem:
        """Generate one new problem, optionally constrained by the legacy score range."""
        for _ in range(_MAX_ATTEMPTS):
            terms = self._choose_terms()
            operations = tuple(self._random.choice(self.operations) for _ in range(terms - 1))
            try:
                problem = self._build(terms, operations)
            except GenerationError:
                continue
            if complexity_range is not None and not (
                complexity_range[0] <= complexity_score(problem) <= complexity_range[1]
            ):
                continue
            key = canonical_problem_key(problem)
            if key in self._seen:
                continue
            self._seen.add(key)
            return problem
        raise GenerationError("difficulty profile cannot produce a new problem")

    def generate_many(self, count: int) -> tuple[Problem, ...]:
        """Generate a deterministic, unique and operation-balanced batch."""
        if count < 0:
            raise ValueError("count must not be negative")
        if count == 0:
            return ()

        for _ in range(_MAX_ATTEMPTS):
            terms_list = [self._choose_terms() for _ in range(count)]
            operation_slots = self._balanced_operation_slots(sum(terms - 1 for terms in terms_list))
            slot_index = 0
            local_seen = set(self._seen)
            problems: list[Problem] = []
            for terms in terms_list:
                operations = tuple(operation_slots[slot_index : slot_index + terms - 1])
                slot_index += terms - 1
                problem = self._build_unique(terms, operations, local_seen)
                if problem is None:
                    break
                problems.append(problem)
            if len(problems) == count:
                self._seen.update(local_seen)
                return tuple(problems)
        raise GenerationError("difficulty profile cannot produce the requested batch")

    def _build_unique(
        self,
        terms: int,
        operations: tuple[Operation, ...],
        seen: set[tuple[object, ...]],
    ) -> Problem | None:
        for _ in range(_MAX_ATTEMPTS):
            try:
                problem = self._build(terms, operations)
            except GenerationError:
                continue
            key = canonical_problem_key(problem)
            if key not in seen:
                seen.add(key)
                return problem
        return None

    def _build(self, terms: int, operations: tuple[Operation, ...]) -> Problem:
        maximum = min(self.profile.max_value, self.profile.max_result)
        minimum = max(1, self.profile.min_value)
        if maximum < minimum:
            raise GenerationError("difficulty profile has no valid initial operand")
        initial = self._random.randint(minimum, maximum)
        node = _Node(str(initial), initial, 4, ())
        for operation in operations:
            node = self._combine(node, operation)
        return Problem(node.text, node.value, node.operations)

    def _choose_terms(self) -> int:
        max_terms = self.profile.max_terms
        min_terms = self.profile.min_terms
        if self.operations == (Operation.POWER,):
            min_terms = max_terms = 2
        if not self.profile.term_weights:
            if min_terms > max_terms:
                raise GenerationError("power-only profile cannot produce this many terms")
            return self._random.randint(min_terms, max_terms)
        choices = [
            (terms, weight)
            for terms, weight in self.profile.term_weights
            if min_terms <= terms <= max_terms
        ]
        if (
            self.operations == (Operation.POWER,)
            and min_terms == 2
            and not any(terms == 2 for terms, _ in choices)
        ):
            choices.append((2, 1))
        if not choices:
            if min_terms > max_terms:
                raise GenerationError("power-only profile cannot produce this many terms")
            return self._random.randint(min_terms, max_terms)
        return self._random.choices(
            [terms for terms, _ in choices],
            weights=[weight for _, weight in choices],
            k=1,
        )[0]

    def _balanced_operation_slots(self, count: int) -> list[Operation]:
        if count == 0:
            return []
        base, remainder = divmod(count, len(self.operations))
        remaining = {operation: base for operation in self.operations}
        for operation in self._random.sample(self.operations, remainder):
            remaining[operation] += 1

        result: list[Operation] = []
        previous: Operation | None = None
        for _ in range(count):
            available = [operation for operation, amount in remaining.items() if amount]
            without_previous = [operation for operation in available if operation is not previous]
            choices = without_previous or available
            operation = self._random.choice(choices)
            result.append(operation)
            remaining[operation] -= 1
            previous = operation
        return result

    def _combine(self, left: _Node, operation: Operation) -> _Node:
        operation = Operation(operation)
        candidates: list[int]
        if operation is Operation.POWER:
            candidates = [
                exponent
                for exponent in (2, 3)
                if abs(left.value**exponent) <= self.profile.max_result
            ]
        elif operation is Operation.DIVIDE:
            candidates = [
                divisor
                for divisor in range(2, self.profile.max_value + 1)
                if left.value != 0
                and left.value % divisor == 0
                and abs(left.value // divisor) <= self.profile.max_result
            ]
        else:
            minimum = max(1, self.profile.min_value)
            if operation is Operation.MULTIPLY:
                minimum = max(2, minimum)
            candidates = [
                operand
                for operand in range(minimum, self.profile.max_value + 1)
                if abs(self._apply(operation, left.value, operand)) <= self.profile.max_result
            ]
        if not candidates:
            raise GenerationError("difficulty profile cannot satisfy operation constraints")

        operand = self._random.choice(candidates)
        value = self._apply(operation, left.value, operand)
        precedence = _PRECEDENCE[operation]
        needs_parentheses = left.precedence < precedence or (
            operation is Operation.POWER and left.precedence <= precedence
        )
        left_text = f"({left.text})" if needs_parentheses else left.text
        return _Node(
            f"{left_text} {operation.value} {operand}",
            value,
            precedence,
            left.operations + (operation,),
        )

    @staticmethod
    def _apply(operation: Operation, left: int, right: int) -> int:
        if operation is Operation.ADD:
            return left + right
        if operation is Operation.SUBTRACT:
            return left - right
        if operation is Operation.MULTIPLY:
            return left * right
        if operation is Operation.DIVIDE:
            return left // right
        return left**right


def canonical_problem_key(problem: Problem) -> tuple[object, ...]:
    """Return a structural key that collapses harmless display variations."""
    tree = ast.parse(problem.expression.replace("^", "**"), mode="eval")
    return _canonical_ast(tree.body)


def _canonical_ast(node: ast.AST) -> tuple[object, ...]:
    if isinstance(node, ast.Constant) and isinstance(node.value, int):
        return ("number", node.value)
    if not isinstance(node, ast.BinOp):
        raise ValueError("unsupported expression")
    operator = type(node.op).__name__
    left = _canonical_ast(node.left)
    right = _canonical_ast(node.right)
    if isinstance(node.op, (ast.Add, ast.Mult)):
        left, right = sorted((left, right), key=repr)
    return (operator, left, right)


def complexity_score(problem: Problem) -> int:
    """Return a deterministic, comparable complexity score for an expression."""
    tree = ast.parse(problem.expression.replace("^", "**"), mode="eval")
    operation_cost = {
        ast.Add: 1,
        ast.Sub: 1,
        ast.Mult: 3,
        ast.Div: 4,
        ast.Pow: 6,
    }

    def visit(node: ast.AST, depth: int = 0) -> int:
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return len(str(abs(node.value)))
        if isinstance(node, ast.BinOp):
            return (
                operation_cost[type(node.op)]
                + visit(node.left, depth + 1)
                + visit(node.right, depth + 1)
                + depth
            )
        raise ValueError("unsupported expression")

    return visit(tree.body)
