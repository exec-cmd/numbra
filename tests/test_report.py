"""Post-training report: recommendation, personal best, deltas and tallies."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from numbra.core.challenge import AnswerAttempt, CompletedTraining, StagePlan
from numbra.core.models import Difficulty, Operation, Problem, StageKind, Topic
from numbra.core.report import (
    Recommendation,
    StageKindTally,
    Tally,
    TrainingReport,
    area_name,
    build_report,
    setup_label,
)
from numbra.core.stats import Stats


def _training(
    correct: int,
    total: int = 20,
    *,
    started_at: float = 100.0,
    difficulty: Difficulty = Difficulty.NORMAL,
    elapsed: float = 2.0,
) -> CompletedTraining:
    problems = tuple(
        Problem(f"{i} + 1", i + 1, (Operation.ADD,), work_units=1) for i in range(total)
    )
    attempts = tuple(
        AnswerAttempt(
            stage_number=1,
            problem_number=i + 1,
            expression=problem.expression,
            correct_answer=problem.answer,
            user_answer=str(problem.answer) if i < correct else "0",
            is_correct=i < correct,
            elapsed_seconds=elapsed,
            timed_out=False,
            operation=Operation.ADD,
            overtime_seconds=0.0,
            score=Decimal(1) if i < correct else Decimal(0),
        )
        for i, problem in enumerate(problems)
    )
    return CompletedTraining(
        started_at=started_at,
        difficulty=difficulty,
        seed=1,
        operations=(Operation.ADD,),
        duration_target_seconds=360.0,
        actual_duration_seconds=10.0,
        stages=(StagePlan(1, StageKind.NORMAL, 10.0, problems),),
        attempts=attempts,
    )


def _finish(stats: Stats, training: CompletedTraining) -> TrainingReport:
    """Build the report the way the CLI does: read history, save, then read the streak."""
    comparable = stats.comparable_history(training, limit=1)
    report = build_report(
        training,
        comparable[0] if comparable else None,
        stats.progress_history(training),
        (1, 1),
    )
    stats.save(training)
    return report


@pytest.mark.parametrize(
    ("previous", "current", "expected"),
    [
        ((20, 20), 20, Recommendation.NEXT),
        ((17, 17), 17, Recommendation.NEXT),  # 0.85 is the inclusive threshold
        ((17, 16), 20, Recommendation.KEEP),  # 0.80 is below the next-level bar
        ((8, 8), 7, Recommendation.KEEP),  # 0.40 is not below the lower bar
        ((7, 7), 7, Recommendation.LOWER),
        ((7, 6), 0, Recommendation.LOWER),
    ],
)
def test_recommendation_thresholds(
    tmp_path: Path,
    previous: tuple[int, int],
    current: int,
    expected: Recommendation,
) -> None:
    stats = Stats(tmp_path / "thresholds.sqlite3")
    for started_at, correct in enumerate(previous, start=1):
        _finish(stats, _training(correct, started_at=float(started_at)))

    report = _finish(stats, _training(current, started_at=10.0))

    assert report.recommendation is expected


def test_recommendation_needs_two_earlier_sessions(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "single.sqlite3")
    _finish(stats, _training(20, started_at=1.0))

    report = _finish(stats, _training(20, started_at=2.0))

    assert report.recommendation is None


def test_hard_never_recommends_the_next_level(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "hard.sqlite3")
    for started_at in (1.0, 2.0):
        _finish(stats, _training(20, difficulty=Difficulty.HARD, started_at=started_at))

    report = _finish(stats, _training(20, difficulty=Difficulty.HARD, started_at=3.0))

    assert report.recommendation is Recommendation.KEEP


def test_first_training_has_no_history(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "first.sqlite3")

    report = _finish(stats, _training(15, started_at=1.0))

    assert report.comparison is None
    assert report.personal_best is None
    assert report.score_vs_best is None
    assert report.is_new_best is True
    assert report.best_correct_seconds is None
    assert report.previous_correct_seconds is None
    assert report.average_correct_seconds == 2.0


def test_personal_best_is_the_best_score_in_the_progress_group(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "best.sqlite3")
    _finish(stats, _training(10, started_at=1.0))
    _finish(stats, _training(18, started_at=2.0))

    below = _finish(stats, _training(15, started_at=3.0))
    assert below.is_new_best is False
    assert below.personal_best == pytest.approx(0.9)
    assert below.score_vs_best == pytest.approx(-0.15)

    above = _finish(stats, _training(20, started_at=4.0))
    assert above.is_new_best is True
    assert above.personal_best == pytest.approx(0.9)
    assert above.score_vs_best == pytest.approx(0.1)


def test_deltas_compare_with_the_previous_comparable_training(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "deltas.sqlite3")
    _finish(stats, _training(10, started_at=1.0, elapsed=4.0))
    _finish(stats, _training(5, started_at=2.0, elapsed=4.0))

    report = _finish(stats, _training(8, started_at=3.0, elapsed=2.0))

    assert report.comparison is not None
    assert report.comparison.previous.started_at == 2.0
    assert report.comparison.score_delta == pytest.approx(0.15)
    assert report.comparison.accuracy_delta == pytest.approx(0.15)
    assert report.comparison.average_delta == pytest.approx(-2.0)
    assert report.comparison.correct_time_delta == pytest.approx(-2.0)
    assert report.comparison.timeouts_delta == 0


def test_correct_time_delta_is_none_when_previous_has_no_correct_answers(
    tmp_path: Path,
) -> None:
    stats = Stats(tmp_path / "no-correct.sqlite3")
    _finish(stats, _training(0, started_at=1.0))

    report = _finish(stats, _training(10, started_at=2.0))

    assert report.comparison is not None
    assert report.comparison.correct_time_delta is None


def test_correct_answer_times_use_best_and_previous_group_rows(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "times.sqlite3")
    _finish(stats, _training(20, started_at=1.0, elapsed=2.0))
    _finish(stats, _training(20, started_at=2.0, elapsed=4.0))

    report = _finish(stats, _training(20, started_at=3.0, elapsed=3.0))

    assert report.average_correct_seconds == 3.0
    assert report.best_correct_seconds == 2.0
    assert report.previous_correct_seconds == 4.0


def test_tallies_by_stage_kind_operation_and_topic() -> None:
    sqrt_add = Problem("1 + 1", 2, (Operation.ADD,), topics=(Topic.SQRT,))
    multiply = Problem("2 * 3", 6, (Operation.MULTIPLY,))
    slow_add = Problem("4 + 4", 8, (Operation.ADD,), topics=(Topic.SQRT,))
    attempts = (
        AnswerAttempt(1, 1, "1 + 1", 2, "2", True, 2.0, False, Operation.ADD, 0.0, Decimal(1)),
        AnswerAttempt(
            1, 2, "2 * 3", 6, "0", False, 2.0, False, Operation.MULTIPLY, 0.0, Decimal(0)
        ),
        AnswerAttempt(2, 1, "4 + 4", 8, None, False, 10.0, True, Operation.ADD, 0.0, Decimal(0)),
    )
    training = CompletedTraining(
        started_at=1.0,
        difficulty=Difficulty.NORMAL,
        seed=1,
        operations=(Operation.ADD, Operation.MULTIPLY),
        duration_target_seconds=360.0,
        actual_duration_seconds=10.0,
        stages=(
            StagePlan(1, StageKind.NORMAL, 10.0, (sqrt_add, multiply)),
            StagePlan(2, StageKind.SLOW, 10.0, (slow_add,)),
        ),
        attempts=attempts,
    )

    report = build_report(training, None, [], (0, 0))

    assert report.stage_kinds == (
        StageKindTally(StageKind.NORMAL, 1, 2, 0),
        StageKindTally(StageKind.SLOW, 0, 1, 1),
    )
    # Operations sort by symbol value, so "*" comes before "+".
    assert report.operations == ((Operation.MULTIPLY, Tally(0, 1)), (Operation.ADD, Tally(1, 2)))
    assert report.topics == ((Topic.SQRT, Tally(1, 2)),)


def test_weakest_tally_picks_lowest_accuracy() -> None:
    base = _training(1, total=4)
    problems = tuple(
        Problem(
            f"{i} + 1",
            i + 1,
            (Operation.MULTIPLY if i == 0 else Operation.DIVIDE,),
            topics=(Topic.SQRT,) if i == 0 else (),
        )
        for i in range(4)
    )
    stage = replace(base.stages[0], problems=problems)
    attempts = tuple(
        replace(attempt, problem_number=i + 1, is_correct=i == 0)
        for i, attempt in enumerate(base.attempts)
    )
    report = build_report(replace(base, stages=(stage,), attempts=attempts), None, [], (0, 0))

    assert report.weakest == ("/", Tally(0, 3))


def test_weakest_tally_is_none_when_everything_is_correct() -> None:
    report = build_report(_training(4, total=4), None, [], (0, 0))

    assert report.weakest is None


def test_setup_label_and_area_name() -> None:
    assert setup_label("normal", False, ("+", "*"), ("sqrt",)) == "normal: + × sqrt"
    assert setup_label("normal", False, ("*", "+", "-", "/"), ()) == "normal: + − × ÷"
    assert setup_label("hard", True, ("/",), ()) == "hard, strict: ÷"
    assert setup_label("easy", False, (), ()) == "easy"
    assert area_name("*") == "multiplication"
    assert area_name("custom") == "custom"


def test_streak_is_passed_through() -> None:
    training = _training(20, started_at=1.0)

    report = build_report(training, None, [], (2, 3))

    assert (report.current_streak, report.longest_streak) == (2, 3)
