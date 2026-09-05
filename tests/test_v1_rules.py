import sqlite3
from collections import Counter
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
from numbra.core.generator import canonical_problem_key, complexity_score
from numbra.core.models import Difficulty, Operation, Problem, StageKind
from numbra.core.stats import Stats


def expected_problem_score(problem: Problem) -> Decimal:
    return Decimal("1") + Decimal(max(0, complexity_score(problem) - 3)) * Decimal("0.2")


def test_problem_uses_standard_operator_precedence() -> None:
    problem = Problem("20 + 15 * 8", 140, (Operation.ADD, Operation.MULTIPLY))

    assert problem.evaluate() == 140


def test_problem_supports_small_integer_powers() -> None:
    problem = Problem("(2 + 3) ^ 2", 25, (Operation.ADD, Operation.POWER))

    assert problem.evaluate() == 25


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
    attempt = session.submit(0, 0, answer, elapsed_seconds=6.0)

    assert attempt.is_correct is True
    assert attempt.overtime_seconds == 1.0
    problem = session.stages[0].problems[0]
    assert attempt.score == expected_problem_score(problem) * Decimal("0.8")


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


def test_difficulty_aggregate_uses_example_totals(tmp_path: Path) -> None:
    config = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    stats = Stats(tmp_path / "history.sqlite3")
    for seed in (1, 2):
        session = Challenge(config).create_session(
            ChallengeOptions(seed=seed, stages=1, operations=(Operation.ADD,))
        )
        for index, problem in enumerate(session.stages[0].problems):
            session.submit(0, index, str(problem.answer), 0.5)
        stats.save(session.complete(actual_duration=1.0))

    aggregate = stats.aggregate()

    assert aggregate.by_difficulty["normal"] == (
        aggregate.total_examples,
        aggregate.correct_answers,
    )


def test_generator_can_target_a_complexity_band(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(difficulty=Difficulty.NORMAL, seed=11, stages=1)
    )

    scores = [complexity_score(problem) for problem in session.stages[0].problems]

    assert max(abs(left - right) for left, right in zip(scores, scores[1:], strict=False)) <= 8


def test_session_generator_balances_operations_and_avoids_repeats(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    operations = (Operation.ADD, Operation.SUBTRACT, Operation.MULTIPLY, Operation.DIVIDE)
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=42, stages=1, duration_minutes=1, operations=operations)
    )
    problems = [problem for stage in session.stages for problem in stage.problems]
    counts = Counter(operation for problem in problems for operation in problem.operations)

    assert len({canonical_problem_key(problem) for problem in problems}) == len(problems)
    assert max(counts.values()) - min(counts.values()) <= 1


def test_difficulty_profiles_control_term_count_and_result_size(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    expected = {
        Difficulty.VERY_EASY: (2, 2),
        Difficulty.EASY: (2, 2),
        Difficulty.NORMAL: (2, 3),
        Difficulty.HARD: (3, 4),
        Difficulty.VERY_HARD: (3, 4),
    }

    for difficulty, (minimum, maximum) in expected.items():
        session = Challenge(settings).create_session(
            ChallengeOptions(
                difficulty=difficulty,
                seed=42,
                stages=1,
                duration_minutes=1,
                operations=(Operation.ADD,),
            )
        )
        profile = settings.challenge.profiles[difficulty]
        problems = session.stages[0].problems

        assert all(minimum <= len(problem.operations) + 1 <= maximum for problem in problems)
        assert all(abs(problem.answer) <= profile.max_result for problem in problems)


def test_strict_timeout_never_awards_score(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.ADD,), strict=True)
    )
    answer = str(session.stages[0].problems[0].answer)

    attempt = session.submit(0, 0, answer, elapsed_seconds=6.0, timed_out=True)

    assert attempt.is_correct is False
    assert attempt.score == Decimal("0")


def test_stats_persist_score_and_timer_mode(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.ADD,), strict=True)
    )
    problem = session.stages[0].problems[0]
    session.submit(0, 0, str(problem.answer), 0.5)
    stats = Stats(tmp_path / "history.sqlite3")
    stats.save(session.complete(actual_duration=1.0))

    record = stats.history(1)[0]

    assert record.strict is True
    expected_max_score = sum(
        expected_problem_score(item) for stage in session.stages for item in stage.problems
    )
    assert record.score == float(expected_problem_score(problem))
    assert record.max_score == float(expected_max_score)


def test_planned_limits_stay_within_requested_duration(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(
            duration_minutes=1,
            stages=1,
            operations=(Operation.DIVIDE,),
        )
    )

    planned = sum(session.time_limit_for(0, index) for index in range(session.total_examples))

    assert planned <= session.target_seconds


def test_stats_migrates_legacy_database(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL NOT NULL,
                status TEXT NOT NULL, difficulty TEXT NOT NULL, seed INTEGER NOT NULL,
                operations TEXT NOT NULL, target_seconds REAL NOT NULL, actual_seconds REAL NOT NULL,
                stages INTEGER NOT NULL, total_examples INTEGER NOT NULL, correct_answers INTEGER NOT NULL,
                timeouts INTEGER NOT NULL, average_response REAL NOT NULL
            );
            CREATE TABLE stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, training_id INTEGER NOT NULL,
                number INTEGER NOT NULL, kind TEXT NOT NULL, examples INTEGER NOT NULL,
                duration REAL NOT NULL
            );
            CREATE TABLE attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, stage_id INTEGER NOT NULL,
                number INTEGER NOT NULL, expression TEXT NOT NULL, correct_answer TEXT NOT NULL,
                user_answer TEXT, is_correct INTEGER NOT NULL, elapsed REAL NOT NULL,
                timed_out INTEGER NOT NULL, operation TEXT NOT NULL
            );
            INSERT INTO trainings VALUES (1, 1700000000, 'completed', 'normal', 1, '["+"]', 60, 2, 1, 1, 1, 0, 1);
            INSERT INTO stages VALUES (1, 1, 1, 'normal', 1, 1);
            INSERT INTO attempts VALUES (1, 1, 1, '1 + 1', '2', '2', 1, 1, 0, '+');
            """
        )

    stats = Stats(database)

    record = stats.history(1)[0]
    assert record.score == 1.0
    assert record.max_score == 1.0
    assert record.operations == ("+",)


def test_challenge_persists_wall_clock_timestamp(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(
        settings,
        clock=lambda: 12.0,
        wall_clock=lambda: 1_700_000_000.0,
    ).create_session(ChallengeOptions(stages=1, seed=1, operations=(Operation.ADD,)))

    assert session.started_at == 1_700_000_000.0
