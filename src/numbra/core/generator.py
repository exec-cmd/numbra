from __future__ import annotations

import random
from dataclasses import dataclass

from .models import Operation, Problem


@dataclass(frozen=True, slots=True)
class DifficultyProfile:
    min_value: int
    max_value: int
    min_terms: int = 2
    max_terms: int = 2


class ProblemGenerator:
    def __init__(
        self, profile: DifficultyProfile, operations: tuple[Operation, ...], seed: int
    ) -> None:
        if not operations:
            raise ValueError("at least one operation is required")
        if profile.min_value < 0 or profile.max_value < profile.min_value:
            raise ValueError("invalid difficulty range")
        self.profile = profile
        self.operations = operations
        self._random = random.Random(seed)

    def generate(self) -> Problem:
        terms = self._random.randint(self.profile.min_terms, self.profile.max_terms)
        values = [self._random.randint(self.profile.min_value, self.profile.max_value)]
        selected: list[Operation] = []
        result = values[0]
        for _ in range(terms - 1):
            operation = self._random.choice(self.operations)
            operand = self._random.randint(max(1, self.profile.min_value), self.profile.max_value)
            if operation is Operation.DIVIDE:
                divisors = [value for value in range(1, abs(result) + 1) if result % value == 0]
                if divisors:
                    operand = self._random.choice(divisors)
                else:
                    operation = self._random.choice(
                        tuple(item for item in self.operations if item is not Operation.DIVIDE)
                        or (Operation.ADD,)
                    )
            if operation is Operation.SUBTRACT and result < operand:
                operand = min(result, operand) if result > 0 else 0
            if operation is Operation.ADD:
                result += operand
            elif operation is Operation.SUBTRACT:
                result -= operand
            elif operation is Operation.MULTIPLY:
                result *= operand
            else:
                result //= operand
            values.append(operand)
            selected.append(operation)
        parts = [str(values[0])]
        for operation, value in zip(selected, values[1:], strict=True):
            parts.extend((operation.value, str(value)))
        return Problem(" ".join(parts), result, tuple(selected))
