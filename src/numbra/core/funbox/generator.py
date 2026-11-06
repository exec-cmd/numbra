from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable

from ..models import Difficulty, Problem
from . import derivatives, equations, fraction_tasks, graphs, logic, substitution
from .modes import FunboxMode

# Work-unit bands match the arithmetic generator, so scoring and the time budget stay comparable.
WORK_BANDS = {
    Difficulty.EASY: (1, 2),
    Difficulty.NORMAL: (2, 5),
    Difficulty.HARD: (4, 9),
}
# Retries before a repeat is accepted; a small mode would otherwise stall the session.
UNIQUE_ATTEMPTS = 50

_MAKERS: dict[FunboxMode, Callable[[random.Random, Difficulty, int], Problem]] = {
    FunboxMode.FRACTIONS: fraction_tasks.make,
    FunboxMode.SUBSTITUTION: substitution.make,
    FunboxMode.EQUATIONS: equations.make,
    FunboxMode.LOGIC: logic.make,
    FunboxMode.GRAPHS: graphs.make,
    FunboxMode.DERIVATIVES: derivatives.make,
}


class FunboxGenerator:
    """Experimental exercises with the ProblemGenerator surface that Challenge uses."""

    def __init__(self, modes: tuple[FunboxMode, ...], difficulty: Difficulty, seed: int) -> None:
        requested = {FunboxMode(mode) for mode in modes}
        if not requested:
            raise ValueError("at least one funbox mode is required")
        # Canonical order, so the same modes give the same sequence in any order.
        self.modes = tuple(mode for mode in FunboxMode if mode in requested)
        self.difficulty = Difficulty(difficulty)
        self._random = random.Random(seed)
        self._seen: set[str] = set()
        self._counts: Counter[FunboxMode] = Counter()
        self.warnings: list[str] = []

    def start_stage(self, pending: Problem | None = None) -> None:
        """Funbox has no per-stage balance; the carried-over candidate is already counted."""

    def generate_many(self, count: int) -> tuple[Problem, ...]:
        if count < 0:
            raise ValueError("count must not be negative")
        return tuple(self._next() for _ in range(count))

    def _next(self) -> Problem:
        least = min(self._counts[mode] for mode in self.modes)
        mode = self._random.choice([item for item in self.modes if self._counts[item] == least])
        self._counts[mode] += 1
        low, high = WORK_BANDS[self.difficulty]
        for _ in range(UNIQUE_ATTEMPTS):
            problem = _MAKERS[mode](self._random, self.difficulty, self._random.randint(low, high))
            if problem.expression not in self._seen:
                self._seen.add(problem.expression)
                return problem
        warning = "Selected funbox modes require repeated exercises; unique catalog exhausted."
        if warning not in self.warnings:
            self.warnings.append(warning)
        return problem
