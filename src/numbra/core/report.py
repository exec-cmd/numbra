from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from .challenge import CompletedTraining
from .models import Difficulty, Operation, StageKind, Topic
from .stats import TrainingRecord


class Recommendation(StrEnum):
    NEXT = "next"
    LOWER = "lower"
    KEEP = "keep"


RECOMMENDATION_TEXT = {
    Recommendation.NEXT: "Recommendation: try the next difficulty level.",
    Recommendation.LOWER: "Recommendation: repeat or lower the difficulty level.",
    Recommendation.KEEP: "Recommendation: keep the current difficulty level.",
}

# One name per metric, used by the TUI, the CLI and the docs.
METRIC_HELP: dict[str, str] = {
    "Score": "Points for speed and difficulty, as a percent of the maximum.",
    "Accuracy": "Share of correct answers.",
    "Grade": "Letter for the score: S 90%+, A 75%+, B 60%+, C 40%+, D below.",
    "Time": "Average seconds per correct answer.",
    "Streak": "Days in a row with a completed training.",
    "Personal best": "Best score with the same difficulty, timing mode, operations and topics.",
}

AREA_NAMES: dict[str, str] = {
    "+": "addition",
    "-": "subtraction",
    "*": "multiplication",
    "/": "division",
    "^": "powers",
    "power": "powers",
    "sqrt": "square roots",
    "trig": "trigonometry",
    "log": "logarithms",
}
OPERATION_SYMBOLS: dict[str, str] = {"+": "+", "-": "−", "*": "×", "/": "÷", "^": "^"}


def area_name(name: str) -> str:
    """Readable name of an operation, topic or trick strategy ("*" -> "multiplication")."""
    return AREA_NAMES.get(name, name)


def setup_label(
    difficulty: str, strict: bool, operations: Sequence[str], topics: Sequence[str]
) -> str:
    """One training setup in words: "normal, strict: + − × ÷ sqrt"."""
    label = f"{difficulty}, strict" if strict else difficulty
    selections = [
        *(OPERATION_SYMBOLS.get(operation, operation) for operation in operations),
        *topics,
    ]
    return f"{label}: {' '.join(selections)}" if selections else label


@dataclass(frozen=True, slots=True)
class Tally:
    correct: int
    total: int


@dataclass(frozen=True, slots=True)
class StageKindTally:
    kind: StageKind
    correct: int
    total: int
    timeouts: int


@dataclass(frozen=True, slots=True)
class Comparison:
    """Deltas against the previous comparable training (same settings and duration)."""

    previous: TrainingRecord
    score_delta: float
    accuracy_delta: float
    average_delta: float
    timeouts_delta: int
    correct_time_delta: float | None = None


@dataclass(frozen=True, slots=True)
class TrainingReport:
    stage_kinds: tuple[StageKindTally, ...]
    operations: tuple[tuple[Operation, Tally], ...]
    topics: tuple[tuple[Topic, Tally], ...]
    comparison: Comparison | None
    average_correct_seconds: float | None
    best_correct_seconds: float | None
    previous_correct_seconds: float | None
    personal_best: float | None
    score_vs_best: float | None
    is_new_best: bool
    current_streak: int
    longest_streak: int
    recommendation: Recommendation | None

    @property
    def weakest(self) -> tuple[str, Tally] | None:
        """Operation or topic with the lowest accuracy that has a miss; None when all are right."""
        candidates = [
            (name.value, tally)
            for name, tally in (*self.operations, *self.topics)
            if tally.correct < tally.total
        ]
        return min(
            candidates,
            key=lambda item: (item[1].correct / item[1].total, -item[1].total),
            default=None,
        )


def build_report(
    completed: CompletedTraining,
    previous: TrainingRecord | None,
    progress: Sequence[TrainingRecord],
    streak: tuple[int, int],
) -> TrainingReport:
    """Summarise a finished training.

    ``previous`` and ``progress`` must be read before the training is saved, and ``streak``
    after, so the saved training counts toward the streak but not toward the history.
    ``progress`` is newest first and holds the whole progress group.
    """
    stage_kinds = []
    for kind in StageKind:
        stage_numbers = {stage.number for stage in completed.stages if stage.kind is kind}
        kind_attempts = [item for item in completed.attempts if item.stage_number in stage_numbers]
        kind_total = sum(len(stage.problems) for stage in completed.stages if stage.kind is kind)
        if kind_total:
            stage_kinds.append(
                StageKindTally(
                    kind,
                    sum(item.is_correct for item in kind_attempts),
                    kind_total,
                    sum(item.timed_out for item in kind_attempts),
                )
            )

    operation_totals: dict[Operation, list[int]] = {}
    topic_totals: dict[Topic, list[int]] = {}
    for attempt in completed.attempts:
        stage = completed.stages[attempt.stage_number - 1]
        problem = stage.problems[attempt.problem_number - 1]
        for operation in problem.operations:
            totals = operation_totals.setdefault(operation, [0, 0])
            totals[0] += 1
            totals[1] += int(attempt.is_correct)
        for topic in problem.topics:
            totals = topic_totals.setdefault(topic, [0, 0])
            totals[0] += 1
            totals[1] += int(attempt.is_correct)

    comparison = None
    if previous is not None:
        comparison = Comparison(
            previous,
            completed.score_percent - previous.score_percent,
            completed.accuracy - previous.accuracy,
            completed.average_response_seconds - previous.average_response_seconds,
            completed.timeouts - previous.timeouts,
            None
            if completed.average_correct_seconds is None or previous.average_correct_seconds is None
            else completed.average_correct_seconds - previous.average_correct_seconds,
        )

    known_times = [
        row.average_correct_seconds for row in progress if row.average_correct_seconds is not None
    ]
    best = max((row.score_percent for row in progress), default=None)
    score_vs_best = None if best is None else completed.score_percent - best

    recommendation = None
    if len(progress) >= 2:
        scores = [completed.score_percent, *(row.score_percent for row in progress[:2])]
        if all(score >= 0.85 for score in scores) and completed.difficulty is not Difficulty.HARD:
            recommendation = Recommendation.NEXT
        elif all(score < 0.40 for score in scores):
            recommendation = Recommendation.LOWER
        else:
            recommendation = Recommendation.KEEP

    return TrainingReport(
        stage_kinds=tuple(stage_kinds),
        operations=tuple(
            (operation, Tally(totals[1], totals[0]))
            for operation, totals in sorted(
                operation_totals.items(), key=lambda item: item[0].value
            )
        ),
        topics=tuple(
            (topic, Tally(totals[1], totals[0]))
            for topic, totals in sorted(topic_totals.items(), key=lambda item: item[0].value)
        ),
        comparison=comparison,
        average_correct_seconds=completed.average_correct_seconds,
        best_correct_seconds=min(known_times, default=None),
        previous_correct_seconds=progress[0].average_correct_seconds if progress else None,
        personal_best=best,
        score_vs_best=score_vs_best,
        is_new_best=best is None or completed.score_percent > best,
        current_streak=streak[0],
        longest_streak=streak[1],
        recommendation=recommendation,
    )
