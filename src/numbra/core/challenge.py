from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ..config import OperationTimingConfig, Settings
from .generator import DifficultyProfile, ProblemGenerator
from .models import Difficulty, Operation, Problem, StageKind
from .stages import allocate_stage_kinds


@dataclass(frozen=True, slots=True)
class ChallengeOptions:
    duration_minutes: int | None = None
    difficulty: Difficulty | None = None
    seed: int | None = None
    operations: tuple[Operation, ...] | None = None
    stages: int | None = None


@dataclass(frozen=True, slots=True)
class StagePlan:
    number: int
    kind: StageKind
    limit_seconds: float
    problems: tuple[Problem, ...]


@dataclass(frozen=True, slots=True)
class AnswerAttempt:
    stage_number: int
    problem_number: int
    expression: str
    correct_answer: int | Decimal
    user_answer: str | None
    is_correct: bool
    elapsed_seconds: float
    timed_out: bool
    operation: Operation


@dataclass(frozen=True, slots=True)
class CompletedTraining:
    started_at: float
    difficulty: Difficulty
    seed: int
    operations: tuple[Operation, ...]
    duration_target_seconds: float
    actual_duration_seconds: float
    stages: tuple[StagePlan, ...]
    attempts: tuple[AnswerAttempt, ...]
    cancelled: bool = False

    @property
    def total_examples(self) -> int:
        return sum(len(stage.problems) for stage in self.stages)

    @property
    def correct_answers(self) -> int:
        return sum(attempt.is_correct for attempt in self.attempts)

    @property
    def timeouts(self) -> int:
        return sum(attempt.timed_out for attempt in self.attempts)

    @property
    def average_response_seconds(self) -> float:
        answered = [attempt.elapsed_seconds for attempt in self.attempts if not attempt.timed_out]
        return sum(answered) / len(answered) if answered else 0.0

    @property
    def accuracy(self) -> float:
        return self.correct_answers / self.total_examples if self.total_examples else 0.0


class TrainingSession:
    def __init__(
        self,
        *,
        started_at: float,
        difficulty: Difficulty,
        seed: int,
        operations: tuple[Operation, ...],
        target_seconds: float,
        stages: tuple[StagePlan, ...],
        operation_timing: OperationTimingConfig,
    ) -> None:
        self.started_at = started_at
        self.difficulty = difficulty
        self.seed = seed
        self.operations = operations
        self.target_seconds = target_seconds
        self.stages = stages
        self.operation_timing = operation_timing
        self._attempts: dict[tuple[int, int], AnswerAttempt] = {}
        self._cancelled = False

    def time_limit_for(self, stage_number: int, problem_number: int) -> float:
        problem = self.stages[stage_number].problems[problem_number]
        return self.stages[stage_number].limit_seconds + self.operation_timing.bonus_for(
            problem.operations
        )

    def submit(
        self,
        stage_number: int,
        problem_number: int,
        user_answer: str | None,
        elapsed_seconds: float,
        timed_out: bool = False,
    ) -> AnswerAttempt:
        problem = self.stages[stage_number].problems[problem_number]
        parsed = user_answer.strip() if isinstance(user_answer, str) else None
        correct = False if timed_out or parsed is None else _matches_answer(parsed, problem.answer)
        operation = problem.operations[0] if problem.operations else Operation.ADD
        attempt = AnswerAttempt(
            stage_number + 1,
            problem_number + 1,
            problem.expression,
            problem.answer,
            parsed,
            correct,
            max(0.0, elapsed_seconds),
            timed_out,
            operation,
        )
        self._attempts[(stage_number, problem_number)] = attempt
        return attempt

    def cancel(self) -> None:
        self._cancelled = True

    def complete(self, actual_duration: float | None = None) -> CompletedTraining:
        if self._cancelled:
            raise RuntimeError("cancelled training cannot be completed")
        attempts = tuple(self._attempts[key] for key in sorted(self._attempts))
        duration = (
            actual_duration if actual_duration is not None else time.monotonic() - self.started_at
        )
        return CompletedTraining(
            self.started_at,
            self.difficulty,
            self.seed,
            self.operations,
            self.target_seconds,
            duration,
            self.stages,
            attempts,
        )


class Challenge:
    def __init__(self, settings: Settings, clock: Callable[[], float] = time.monotonic) -> None:
        self.settings = settings
        self.clock = clock

    def create_session(self, options: ChallengeOptions | None = None) -> TrainingSession:
        options = options or ChallengeOptions()
        config = self.settings.challenge
        duration = (
            options.duration_minutes
            if options.duration_minutes is not None
            else config.duration_minutes
        )
        difficulty = options.difficulty or config.difficulty
        stages_count = options.stages if options.stages is not None else config.stages
        operations = options.operations if options.operations is not None else config.operations
        if duration < 1 or stages_count < 1 or not operations:
            raise ValueError("invalid challenge options")
        seed = (
            options.seed
            if options.seed is not None
            else (config.seed if config.seed is not None else secrets.randbits(63))
        )
        kinds = allocate_stage_kinds(difficulty, stages_count)
        profile_config = config.profiles[difficulty]
        profile = DifficultyProfile(
            profile_config.min_value,
            profile_config.max_value,
            profile_config.min_terms,
            profile_config.max_terms,
        )
        generator = ProblemGenerator(profile, operations, seed)
        budget = duration * 60 / stages_count
        plans = []
        for number, kind in enumerate(kinds, 1):
            limit = config.stage_limits[kind]
            count = max(1, round(budget / limit))
            plans.append(
                StagePlan(number, kind, limit, tuple(generator.generate() for _ in range(count)))
            )
        return TrainingSession(
            started_at=self.clock(),
            difficulty=difficulty,
            seed=seed,
            operations=operations,
            target_seconds=duration * 60,
            stages=tuple(plans),
            operation_timing=config.operation_timing,
        )


def _matches_answer(value: str, expected: int | Decimal) -> bool:
    try:
        return Decimal(value) == Decimal(str(expected))
    except Exception:
        return False
