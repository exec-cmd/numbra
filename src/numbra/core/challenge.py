from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from decimal import Decimal
from fractions import Fraction

from ..config import OperationTimingConfig, Settings
from .generator import (
    DifficultyProfile,
    GenerationError,
    ProblemGenerator,
    canonical_problem_key,
    complexity_score,
)
from .models import (
    BASIC_OPERATIONS,
    Difficulty,
    Operation,
    Problem,
    StageKind,
    Topic,
    parse_operation_selection,
)
from .stages import allocate_stage_kinds


@dataclass(frozen=True, slots=True)
class ChallengeOptions:
    duration_minutes: int | None = None
    difficulty: Difficulty | None = None
    seed: int | None = None
    operations: tuple[Operation | Topic, ...] | None = None
    stages: int | None = None
    strict: bool = False
    cooldown_seconds: float = 2.0
    advanced: bool | None = None
    sqrt: bool | None = None
    trig: bool | None = None
    log: bool | None = None
    power: bool | None = None
    identities: bool | None = None


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
    correct_answer: int | Decimal | Fraction
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
    topics: tuple[Topic, ...] = ()
    generation_version: int = 4
    scoring_version: int = 2
    settings_fingerprint: str = ""

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
        topics: tuple[Topic, ...] = (),
        warnings: tuple[str, ...] = (),
        settings_fingerprint: str = "",
    ) -> None:
        self.topics = topics
        self.warnings = warnings
        self.settings_fingerprint = settings_fingerprint
        self.generation_version = 4
        self.scoring_version = 2
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
        return self.stages[stage_number].limit_seconds + _problem_bonus(
            problem, self.operation_timing
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
        limit = self.time_limit_for(stage_number, problem_number)
        timed_out = timed_out or (self.strict and elapsed_seconds >= limit)
        correct = False if timed_out or parsed is None else _matches_answer(parsed, problem.answer)
        operation = problem.operations[0] if problem.operations else Operation.ADD
        elapsed = max(0.0, elapsed_seconds)
        overtime = max(0.0, elapsed - limit)
        score = score_for_problem(problem, elapsed, limit) if correct else Decimal(0)
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
            topics=self.topics,
            settings_fingerprint=self.settings_fingerprint,
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
        raw_operations = options.operations if options.operations is not None else config.operations
        if duration < 1 or stages_count < 1 or not raw_operations:
            raise ValueError("invalid challenge options")
        if not 1.0 <= options.cooldown_seconds <= 3.0:
            raise ValueError("cooldown_seconds must be between 1 and 3")
        selection = parse_operation_selection(item.value for item in raw_operations)
        operations: tuple[Operation, ...] = tuple(
            item
            for item in selection
            if isinstance(item, Operation) and item is not Operation.POWER
        )
        selected_topics = {
            Topic.POWER if item is Operation.POWER else item
            for item in selection
            if isinstance(item, Topic) or item is Operation.POWER
        }
        features = (
            dict(config.features)
            if options.operations is None
            else {Topic.IDENTITIES: config.features.get(Topic.IDENTITIES, False)}
        )
        if options.advanced is not None:
            features = {topic: options.advanced for topic in Topic}
            if options.advanced:
                operations = BASIC_OPERATIONS
        if options.operations is not None or options.advanced is None:
            features.update({topic: True for topic in selected_topics})
        # Retain programmatic option compatibility; CLI selection uses -o exclusively.
        for topic in Topic:
            selected = getattr(options, topic.value)
            if selected is not None:
                features[topic] = selected
        if Topic.POWER in selected_topics and options.power is False:
            raise ValueError("--operations power conflicts with power=False")
        operations = tuple(dict.fromkeys(operations))
        topics = tuple(topic for topic in Topic if features.get(topic, False))
        if not operations and not topics and options.operations is None:
            operations = BASIC_OPERATIONS
        if not operations and not topics:
            raise ValueError("at least one operation or topic is required")
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
        )

        def prepare(minutes: int) -> tuple[tuple[StagePlan, ...], tuple[str, ...], bool]:
            generator = ProblemGenerator(
                profile, operations, seed, difficulty=difficulty, topics=topics
            )
            budget = minutes * 60 / stages_count
            plans = []
            covered: set[Topic] = set()
            pending: Problem | None = None
            displayed: set[tuple[object, ...]] = set()
            has_repeats = False
            for number, kind in enumerate(kinds, 1):
                generator.start_stage(pending)
                used = 0.0
                problems = []
                while True:
                    candidate = pending if pending is not None else generator.generate_many(1)[0]
                    limit = config.stage_limits[kind] + _problem_bonus(
                        candidate, config.operation_timing
                    )
                    if used + limit > budget:
                        pending = candidate
                        break
                    pending = None
                    key = canonical_problem_key(candidate)
                    has_repeats = has_repeats or key in displayed
                    displayed.add(key)
                    problems.append(candidate)
                    covered.update(candidate.topics)
                    used += limit
                if not problems:
                    return (), (), False
                plans.append(StagePlan(number, kind, config.stage_limits[kind], tuple(problems)))
            actual_warnings = tuple(generator.warnings) if has_repeats else ()
            return tuple(plans), actual_warnings, set(topics) <= covered

        plans, warnings, covered = prepare(duration)
        if not plans or not covered:
            recommended = duration + 1
            while recommended <= max(60, stages_count):
                trial, _, complete = prepare(recommended)
                if trial and complete:
                    break
                recommended += 1
            raise GenerationError(
                f"Time budget cannot cover all stages and enabled topics; minimum duration: {recommended} minutes"
            )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "profile": asdict(profile),
                    "timing": asdict(config.operation_timing),
                    "limits": config.stage_limits,
                    "topics": [topic.value for topic in topics],
                    "operations": [op.value for op in operations],
                    "generation": 3,
                    "scoring": 2,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return TrainingSession(
            started_at=self.wall_clock(),
            difficulty=difficulty,
            seed=seed,
            operations=operations,
            target_seconds=duration * 60,
            stages=plans,
            operation_timing=config.operation_timing,
            strict=options.strict,
            cooldown_seconds=options.cooldown_seconds,
            monotonic_started=self.clock(),
            clock=self.clock,
            topics=topics,
            warnings=warnings,
            settings_fingerprint=fingerprint,
        )


def _problem_bonus(problem: Problem, timing: OperationTimingConfig) -> float:
    if not timing.enabled:
        return 0.0
    bonus = timing.bonus_for(problem.operations) + max(0, complexity_score(problem) - 4)

    def visit(node: object) -> float:
        from .expressions import Expr

        if not isinstance(node, Expr):
            return 0.0
        extra = {"sqrt": 1.0, "sin": 2.0, "cos": 2.0, "tan": 2.0, "log": 2.0}.get(node.kind, 0.0)
        return extra + sum(visit(child) for child in node.args)

    return bonus + visit(problem.as_tree())


def _matches_answer(value: str, expected: int | Decimal | Fraction) -> bool:
    try:
        if len(value) > 128 or not re.fullmatch(
            r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]{1,3})?|[+-]?[0-9]+\s*/\s*[+-]?[0-9]+",
            value,
        ):
            return False
        return Fraction(value) == Fraction(expected)
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
