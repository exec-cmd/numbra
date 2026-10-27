from __future__ import annotations

import sqlite3
from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

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
from numbra.core.stats import Stats


def expected_problem_score(problem: Problem) -> Decimal:
    return Decimal("1") + Decimal(max(0, complexity_score(problem) - 3)) * Decimal("0.2")


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
