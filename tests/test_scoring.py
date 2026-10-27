from decimal import Decimal
from pathlib import Path

from numbra.config import ConfigManager, ConfigPaths
from numbra.config.models import OperationTimingConfig
from numbra.core.challenge import (
    Challenge,
    ChallengeOptions,
    StagePlan,
    TrainingSession,
    score_for_elapsed,
)
from numbra.core.generator import complexity_score
from numbra.core.models import Difficulty, Operation, Problem, StageKind


def expected_problem_score(problem: Problem) -> Decimal:
    return Decimal("1") + Decimal(max(0, complexity_score(problem) - 3)) * Decimal("0.2")


def test_soft_score_is_full_until_limit_and_zero_at_two_limits() -> None:
    assert score_for_elapsed(10.0, 10.0) == 1.0
    assert score_for_elapsed(15.0, 10.0) == 0.5
    assert score_for_elapsed(20.0, 10.0) == 0.0
    assert score_for_elapsed(30.0, 10.0) == 0.0


def test_late_correct_answer_is_recorded_with_partial_score(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.ADD,))
    )

    answer = str(session.stages[0].problems[0].answer)
    limit = session.time_limit_for(0, 0)
    attempt = session.submit(0, 0, answer, elapsed_seconds=limit + 1.0)

    assert attempt.is_correct is True
    assert attempt.overtime_seconds == 1.0
    problem = session.stages[0].problems[0]
    assert attempt.score == expected_problem_score(problem) * score_for_elapsed(limit + 1.0, limit)


def test_score_depends_on_problem_complexity() -> None:
    simple = Problem("1 + 1", 2, (Operation.ADD,))
    complex_problem = Problem(
        "20 / 5 + 3 * 4",
        16,
        (Operation.DIVIDE, Operation.ADD, Operation.MULTIPLY),
    )
    session = TrainingSession(
        started_at=0.0,
        difficulty=Difficulty.NORMAL,
        seed=1,
        operations=(Operation.ADD, Operation.DIVIDE, Operation.MULTIPLY),
        target_seconds=60.0,
        stages=(
            StagePlan(
                1,
                StageKind.NORMAL,
                10.0,
                (simple, complex_problem),
            ),
        ),
        operation_timing=OperationTimingConfig(enabled=False),
    )

    simple_attempt = session.submit(0, 0, "2", elapsed_seconds=5.0)
    complex_attempt = session.submit(0, 1, "16", elapsed_seconds=5.0)
    completed = session.complete(actual_duration=10.0)

    assert complexity_score(complex_problem) > complexity_score(simple)
    assert complex_attempt.score > simple_attempt.score
    assert simple_attempt.score == Decimal("1.0")
    assert complex_attempt.score == expected_problem_score(complex_problem)
    assert completed.max_score == Decimal(
        expected_problem_score(simple) + expected_problem_score(complex_problem)
    )


def test_strict_timeout_never_awards_score(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.ADD,), strict=True)
    )
    answer = str(session.stages[0].problems[0].answer)

    attempt = session.submit(0, 0, answer, elapsed_seconds=6.0, timed_out=True)

    assert attempt.is_correct is False
    assert attempt.score == Decimal("0")
