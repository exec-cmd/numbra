from __future__ import annotations

import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from ..config import OperationTimingConfig, Settings
from .generator import DifficultyProfile, ProblemGenerator, complexity_score
from .models import Difficulty, Operation, Problem, StageKind
from .stages import allocate_stage_kinds


@dataclass(frozen=True, slots=True)
class ChallengeOptions:
    duration_minutes: int | None = None
    difficulty: Difficulty | None = None
    seed: int | None = None
    operations: tuple[Operation, ...] | None = None
    stages: int | None = None
    strict: bool = False
    cooldown_seconds: float = 2.0


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
    overtime_seconds: float
    score: Decimal


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
    strict: bool = False
    cooldown_seconds: float = 2.0
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

    @property
    def max_score(self) -> Decimal:
        return sum(
            (max_score_for_problem(problem) for stage in self.stages for problem in stage.problems),
            Decimal(0),
        )

    @property
    def score(self) -> Decimal:
        return sum((attempt.score for attempt in self.attempts), Decimal(0))

    @property
    def score_percent(self) -> float:
        return float(self.score / self.max_score) if self.max_score else 0.0

    @property
    def grade(self) -> str:
        return grade_for_score(self.score_percent)


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
        strict: bool = False,
        cooldown_seconds: float = 2.0,
        monotonic_started: float | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.started_at = started_at
        self.difficulty = difficulty
        self.seed = seed
        self.operations = operations
        self.target_seconds = target_seconds
        self.stages = stages
        self.operation_timing = operation_timing
        self.strict = strict
        self.cooldown_seconds = cooldown_seconds
        self._clock = clock
        self._monotonic_started = monotonic_started if monotonic_started is not None else clock()
        self._attempts: dict[tuple[int, int], AnswerAttempt] = {}
        self._cancelled = False

    @property
    def total_examples(self) -> int:
        return sum(len(stage.problems) for stage in self.stages)

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
        limit = self.time_limit_for(stage_number, problem_number)
        elapsed = max(0.0, elapsed_seconds)
        overtime = max(0.0, elapsed - limit)
        score = Decimal(0)
        if correct:
            score = (
                Decimal(0)
                if self.strict and timed_out
                else score_for_problem(problem, elapsed, limit)
            )
        attempt = AnswerAttempt(
            stage_number + 1,
            problem_number + 1,
            problem.expression,
            problem.answer,
            parsed,
            correct,
            elapsed,
            timed_out,
            operation,
            overtime,
            score,
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
            actual_duration
            if actual_duration is not None
            else self._clock() - self._monotonic_started
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
            self.strict,
            self.cooldown_seconds,
        )


class Challenge:
    def __init__(
        self,
        settings: Settings,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings
        self.clock = clock
        self.wall_clock = wall_clock

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
        if not 1.0 <= options.cooldown_seconds <= 3.0:
            raise ValueError("cooldown_seconds must be between 1 and 3")
        if Operation.POWER in operations and difficulty not in (
            Difficulty.HARD,
            Difficulty.VERY_HARD,
        ):
            raise ValueError("operation ^ is available only for hard and very-hard difficulty")
        seed = (
            options.seed
            if options.seed is not None
            else (config.seed if config.seed is not None else secrets.randbits(63))
        )
        kinds = allocate_stage_kinds(stages_count)
        profile_config = config.profiles[difficulty]
        profile = DifficultyProfile(
            profile_config.min_value,
            profile_config.max_value,
            profile_config.min_terms,
            profile_config.max_terms,
            profile_config.max_result,
            _TERM_WEIGHTS[difficulty],
        )
        generator = ProblemGenerator(profile, operations, seed)
        budget = duration * 60 / stages_count
        max_bonus = max(
            (config.operation_timing.bonus_seconds.get(operation, 0.0) for operation in operations),
            default=0.0,
        )
        max_problem_bonus = (
            max_bonus * max(1, profile.max_terms - 1) if config.operation_timing.enabled else 0.0
        )
        counts = [
            max(1, int(budget // (config.stage_limits[kind] + max_problem_bonus))) for kind in kinds
        ]
        generated = generator.generate_many(sum(counts))
        cursor = 0
        plans = []
        for number, (kind, count) in enumerate(zip(kinds, counts, strict=True), 1):
            limit = config.stage_limits[kind]
            problems = generated[cursor : cursor + count]
            cursor += count
            plans.append(StagePlan(number, kind, limit, tuple(problems)))
        return TrainingSession(
            started_at=self.wall_clock(),
            difficulty=difficulty,
            seed=seed,
            operations=operations,
            target_seconds=duration * 60,
            stages=tuple(plans),
            operation_timing=config.operation_timing,
            strict=options.strict,
            cooldown_seconds=options.cooldown_seconds,
            monotonic_started=self.clock(),
            clock=self.clock,
        )


_TERM_WEIGHTS = {
    Difficulty.VERY_EASY: ((2, 1),),
    Difficulty.EASY: ((2, 1),),
    Difficulty.NORMAL: ((2, 7), (3, 3)),
    Difficulty.HARD: ((3, 4), (4, 6)),
    Difficulty.VERY_HARD: ((3, 2), (4, 8)),
}


def _matches_answer(value: str, expected: int | Decimal) -> bool:
    try:
        return Decimal(value) == Decimal(str(expected))
    except Exception:
        return False


def score_for_elapsed(elapsed_seconds: float, limit_seconds: float) -> Decimal:
    """Return the linear soft-time score for a correct answer."""
    if limit_seconds <= 0:
        raise ValueError("limit_seconds must be positive")
    elapsed = max(0.0, elapsed_seconds)
    factor = max(0.0, min(1.0, 2.0 - elapsed / limit_seconds))
    return Decimal(str(round(factor, 10)))


def max_score_for_problem(problem: Problem) -> Decimal:
    """Return the calibrated maximum score for a problem."""
    return Decimal(1) + Decimal(max(0, complexity_score(problem) - 3)) * Decimal("0.2")


def score_for_problem(problem: Problem, elapsed_seconds: float, limit_seconds: float) -> Decimal:
    """Return the task's complexity-weighted score for a correct answer."""
    return max_score_for_problem(problem) * score_for_elapsed(elapsed_seconds, limit_seconds)


def grade_for_score(score_percent: float) -> str:
    if score_percent >= 0.90:
        return "S"
    if score_percent >= 0.75:
        return "A"
    if score_percent >= 0.60:
        return "B"
    if score_percent >= 0.40:
        return "C"
    return "D"
