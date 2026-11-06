from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from numbra.config import ConfigManager, ConfigPaths
from numbra.core.challenge import (
    AnswerAttempt,
    Challenge,
    ChallengeOptions,
    CompletedTraining,
    StagePlan,
)
from numbra.core.generator import complexity_score
from numbra.core.models import Difficulty, Operation, Problem, StageKind, Topic
from numbra.core.stats import AttemptRecord, Breakdown, GroupStats, Stats


def test_stats_closes_every_connection(tmp_path: Path, monkeypatch) -> None:
    connections = []
    connect = sqlite3.connect

    def capture_connection(*args, **kwargs):
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(sqlite3, "connect", capture_connection)
    stats = Stats(tmp_path / "closed.sqlite3")
    training = _training()
    stats.save(training)
    stats.history()
    stats.aggregate()
    stats.comparable_history(training)
    stats.reset()

    assert len(connections) == 6
    for connection in connections:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            connection.execute("SELECT 1")


def test_failed_save_rolls_back_the_whole_training(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "rollback.sqlite3")
    with closing(sqlite3.connect(stats.database_path)) as connection, connection:
        connection.execute(
            "CREATE TRIGGER fail_attempt BEFORE INSERT ON attempts "
            "BEGIN SELECT RAISE(ABORT, 'attempt rejected'); END"
        )

    with pytest.raises(sqlite3.IntegrityError, match="attempt rejected"):
        stats.save(_training())

    assert stats.history() == []
    with closing(sqlite3.connect(stats.database_path)) as connection:
        for table in ("trainings", "stages", "attempts"):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def test_comparable_history_stops_decoding_after_limit(tmp_path: Path, monkeypatch) -> None:
    import numbra.core.stats as stats_module

    stats = Stats(tmp_path / "limited.sqlite3")
    candidate = _training()
    for started_at in (100.0, 101.0):
        stats.save(replace(candidate, started_at=started_at))
    stats.save(replace(candidate, started_at=102.0, operations=(Operation.ADD,)))
    decoded = []
    original = stats_module._training_record

    def capture_record(row):
        decoded.append(row["started_at"])
        return original(row)

    monkeypatch.setattr(stats_module, "_training_record", capture_record)

    assert [row.started_at for row in stats.comparable_history(candidate, limit=1)] == [101.0]
    assert decoded == [101.0]


def test_aggregate_keeps_repeated_operation_counts(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "repeated.sqlite3")
    training = _training()
    problem = replace(training.stages[0].problems[0], operations=(Operation.DIVIDE,) * 2)
    stage = replace(training.stages[0], problems=(problem,))
    for correct in (True, True, False):
        attempt = replace(training.attempts[0], is_correct=correct)
        stats.save(replace(training, stages=(stage,), attempts=(attempt,)))

    aggregate = stats.aggregate()

    assert aggregate.by_operation == {"/": (6, 4)}
    assert aggregate.by_topic == {"power": (3, 2)}
    assert aggregate.completed_trainings == 3


def expected_problem_score(problem: Problem) -> Decimal:
    return Decimal("1") + Decimal(max(0, complexity_score(problem) - 3)) * Decimal("0.2")


def test_results_reads_legacy_very_hard_rows(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from numbra.cli import app
    from numbra.config import default_database_path

    stats = Stats(default_database_path())
    stats.save(_training())
    with closing(sqlite3.connect(stats.database_path)) as connection, connection:
        connection.execute("UPDATE trainings SET difficulty = 'very-hard'")

    assert [row.difficulty for row in stats.history()] == ["very-hard"]
    result = CliRunner().invoke(app, ["results"])
    assert result.exit_code == 0
    assert "very-hard" in result.stdout


def _training(
    *,
    started_at: float = 100.0,
    seed: int = 1,
    topics: tuple[Topic, ...] = (Topic.POWER,),
    generation_version: int = 2,
    scoring_version: int = 2,
    settings_fingerprint: str = "settings-a",
) -> CompletedTraining:
    problem = Problem(
        expression="3 / 2",
        answer=Fraction(3, 2),
        operations=(Operation.DIVIDE,),
        strategy="fraction division",
        work_units=7,
        topics=topics,
    )
    stage = StagePlan(1, StageKind.NORMAL, 30.0, (problem,))
    attempt = AnswerAttempt(
        stage_number=1,
        problem_number=1,
        expression=problem.expression,
        correct_answer=Fraction(3, 2),
        user_answer="3/2",
        is_correct=True,
        elapsed_seconds=0.5,
        timed_out=False,
        operation=Operation.DIVIDE,
        overtime_seconds=0.0,
        score=Decimal("0.75"),
    )
    return CompletedTraining(
        started_at=started_at,
        difficulty=Difficulty.NORMAL,
        seed=seed,
        operations=(Operation.DIVIDE,),
        duration_target_seconds=30.0,
        actual_duration_seconds=0.5,
        stages=(stage,),
        attempts=(attempt,),
        topics=topics,
        generation_version=generation_version,
        scoring_version=scoring_version,
        settings_fingerprint=settings_fingerprint,
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


def test_stats_saves_and_aggregates_completed_training(tmp_path: Path) -> None:
    config = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(config).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.ADD,))
    )
    session.submit(0, 0, str(session.stages[0].problems[0].answer), 0.5, False)
    completed = session.complete(actual_duration=1.0)
    stats = Stats(tmp_path / "history.sqlite3")
    stats.save(completed)
    assert len(stats.history(10)) == 1
    aggregate = stats.aggregate()
    assert aggregate.completed_trainings == 1
    assert aggregate.total_examples == completed.total_examples
    assert aggregate.correct_answers == 1


def _funbox_training(started_at: float) -> CompletedTraining:
    """Same settings as _training, but one problem with no arithmetic operation or topic."""
    base = _training(started_at=started_at, topics=())
    problem = replace(base.stages[0].problems[0], family="funbox", strategy="logic", operations=())
    return replace(base, mode="funbox", stages=(replace(base.stages[0], problems=(problem,)),))


def test_funbox_sessions_stay_out_of_challenge_results(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "history.sqlite3")
    _save_outcomes(stats, [(True, 1.0), (False, 3.0)], topics=())
    funbox_start = 100.0 + 10 * 86400
    stats.save(_funbox_training(funbox_start))
    with closing(sqlite3.connect(tmp_path / "history.sqlite3")) as connection:
        modes = connection.execute("SELECT mode FROM trainings ORDER BY id").fetchall()
    assert modes == [("challenge",), ("funbox",)]

    challenge = _training(topics=())
    assert [record.started_at for record in stats.history()] == [100.0]
    assert [record.started_at for record in stats.funbox_history()] == [funbox_start]
    assert stats.aggregate().completed_trainings == 1
    assert stats.aggregate().total_examples == 2
    assert [record.started_at for record in stats.comparable_history(challenge, 10)] == [100.0]
    assert len(stats.progress_history(challenge)) == 1
    assert [record.sessions for record in stats.records()] == [1]
    assert sum(group.attempts for group in stats.breakdown().operations) == 2
    assert stats.trick_stats() == []
    assert stats.streak(datetime.fromtimestamp(funbox_start).date()) == (0, 1)


def test_funbox_stats_group_attempts_by_mode(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "history.sqlite3")
    stats.save(_funbox_training(100.0))
    stats.save(_funbox_training(200.0))

    groups = stats.funbox_stats()

    assert [(group.kind, group.name, group.attempts, group.correct) for group in groups] == [
        ("mode", "logic", 2, 2)
    ]
    assert groups[0].average_correct_seconds == 0.5


def test_reset_clears_funbox_sessions_too(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "history.sqlite3")
    stats.save(_funbox_training(100.0))

    stats.reset()

    assert stats.funbox_history() == []
    assert stats.funbox_stats() == []


def test_stats_reset_removes_history_but_keeps_schema(tmp_path: Path) -> None:
    database = tmp_path / "history.sqlite3"
    stats = Stats(database)
    stats.reset()
    assert database.exists()
    assert stats.history() == []


def test_save_round_trips_training_and_attempt_metadata(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "metadata.sqlite3")
    training = _training(topics=(Topic.POWER, Topic.IDENTITIES))

    stats.save(training)

    record = stats.history(1)[0]
    with sqlite3.connect(stats.database_path) as connection:
        saved_training = connection.execute(
            "SELECT topics, generation_version, scoring_version, settings_fingerprint "
            "FROM trainings"
        ).fetchone()
        saved_attempt = connection.execute(
            "SELECT correct_answer, topics, work_units, strategy FROM attempts"
        ).fetchone()
    assert record.topics == ("power", "identities")
    assert record.generation_version == 2
    assert record.scoring_version == 2
    assert record.settings_fingerprint == "settings-a"
    assert saved_training == ('["power", "identities"]', 2, 2, "settings-a")
    assert saved_attempt == (
        "3/2",
        '["power", "identities"]',
        7,
        "fraction division",
    )


def test_aggregate_counts_topics_from_attempts(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "topics.sqlite3")
    stats.save(_training(topics=(Topic.POWER, Topic.IDENTITIES)))

    aggregate = stats.aggregate()

    assert aggregate.by_topic == {"power": (1, 1), "identities": (1, 1)}


def test_comparable_history_matches_contract_and_ignores_seed(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "comparable.sqlite3")
    candidate = _training(started_at=100.0, seed=22)
    stats.save(replace(candidate, started_at=101.0, seed=1))
    stats.save(replace(candidate, started_at=102.0, topics=(Topic.POWER, Topic.SQRT)))
    stats.save(replace(candidate, started_at=103.0, generation_version=1))
    stats.save(replace(candidate, started_at=104.0, scoring_version=1))
    stats.save(replace(candidate, started_at=105.0, settings_fingerprint="settings-b"))
    for offset in range(6, 18):
        stats.save(
            replace(
                candidate,
                started_at=100.0 + offset,
                settings_fingerprint=f"other-settings-{offset}",
            )
        )

    rows = stats.comparable_history(candidate, limit=10)

    assert [row.started_at for row in rows] == [101.0]


def _save_outcomes(
    stats: Stats,
    outcomes: list[tuple[bool, float]],
    *,
    difficulty: Difficulty = Difficulty.NORMAL,
    operation: Operation = Operation.DIVIDE,
    topics: tuple[Topic, ...] = (),
    strategy: str = "",
) -> None:
    base = _training(topics=topics)
    problem = replace(
        base.stages[0].problems[0], operations=(operation,), topics=topics, strategy=strategy
    )
    stage = StagePlan(1, StageKind.NORMAL, 30.0, (problem,) * len(outcomes))
    attempts = tuple(
        replace(
            base.attempts[0], problem_number=number, is_correct=correct, elapsed_seconds=elapsed
        )
        for number, (correct, elapsed) in enumerate(outcomes, start=1)
    )
    stats.save(
        replace(
            base,
            difficulty=difficulty,
            operations=(operation,),
            stages=(stage,),
            attempts=attempts,
        )
    )


def test_attempts_lists_one_training_in_stage_and_example_order(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "attempts.sqlite3")
    training = _training()
    problem = training.stages[0].problems[0]
    second_stage = StagePlan(2, StageKind.FAST, 10.0, (problem, problem))
    base = training.attempts[0]
    attempts = (
        replace(base, stage_number=2, problem_number=2, expression="second"),
        replace(base, stage_number=2, problem_number=1, expression="first"),
        base,
    )
    stats.save(replace(training, stages=(training.stages[0], second_stage), attempts=attempts))
    stats.save(_training(started_at=200.0))
    identifier = next(row.identifier for row in stats.history() if row.started_at == 100.0)

    rows = stats.attempts(identifier)

    assert [(row.stage_number, row.kind, row.number, row.expression) for row in rows] == [
        (1, "normal", 1, "3 / 2"),
        (2, "fast", 1, "first"),
        (2, "fast", 2, "second"),
    ]
    assert rows[0] == AttemptRecord(
        1,
        "normal",
        1,
        "3 / 2",
        "3/2",
        "3/2",
        True,
        0.5,
        False,
        0.75,
        "fraction division",
        ("power",),
    )


def test_breakdown_averages_correct_answers_only(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "breakdown.sqlite3")
    _save_outcomes(stats, [(True, 1.0), (True, 3.0), (False, 9.0)], topics=(Topic.POWER,))
    _save_outcomes(
        stats, [(False, 2.0), (False, 4.0)], difficulty=Difficulty.HARD, operation=Operation.ADD
    )

    breakdown = stats.breakdown()

    assert [row.name for row in breakdown.difficulties] == ["normal", "hard"]
    assert breakdown.difficulties[0] == GroupStats("difficulty", "normal", 3, 2, 2.0)
    assert breakdown.difficulties[1] == GroupStats("difficulty", "hard", 2, 0, None)
    assert breakdown.operations == (
        GroupStats("operation", "+", 2, 0, None),
        GroupStats("operation", "/", 3, 2, 2.0),
    )
    assert breakdown.operations[1].accuracy == pytest.approx(2 / 3)
    assert breakdown.topics == (GroupStats("topic", "power", 3, 2, 2.0),)


def test_breakdown_and_weak_spots_are_empty_without_history(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "empty.sqlite3")

    assert stats.breakdown() == Breakdown((), (), ())
    assert stats.weak_spots() == []
    assert stats.attempts(1) == []


def test_weak_spots_apply_threshold_and_rank_by_accuracy_then_time(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "weak.sqlite3")
    _save_outcomes(stats, [(True, 2.0)] + [(False, 1.0)] * 4, operation=Operation.MULTIPLY)
    _save_outcomes(stats, [(True, 4.0)] + [(False, 1.0)] * 4, operation=Operation.ADD)
    _save_outcomes(stats, [(True, 1.0)] * 4 + [(False, 1.0)], operation=Operation.SUBTRACT)
    _save_outcomes(stats, [(False, 1.0)] * 4, operation=Operation.DIVIDE)

    assert [(row.name, row.attempts) for row in stats.weak_spots()] == [
        ("+", 5),
        ("*", 5),
        ("-", 5),
    ]
    assert [row.name for row in stats.weak_spots(min_attempts=4)] == ["/", "+", "*"]
    assert [row.name for row in stats.weak_spots(limit=1)] == ["+"]


def test_weak_spots_include_trick_strategies(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "tricks.sqlite3")
    _save_outcomes(
        stats,
        [(False, 1.0)] * 5,
        operation=Operation.MULTIPLY,
        topics=(Topic.TRICKS,),
        strategy="times-11",
    )

    assert GroupStats("trick", "times-11", 5, 0, None) in stats.weak_spots()


def test_weak_spots_skip_flawless_groups_and_the_tricks_topic(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "flawless.sqlite3")
    _save_outcomes(stats, [(True, 1.0)] * 5, operation=Operation.ADD)
    _save_outcomes(
        stats,
        [(False, 1.0)] * 5,
        operation=Operation.MULTIPLY,
        topics=(Topic.TRICKS,),
        strategy="times-11",
    )

    names = [(row.kind, row.name) for row in stats.weak_spots(limit=10)]

    assert ("operation", "+") not in names
    assert ("topic", "tricks") not in names
    assert ("trick", "times-11") in names
