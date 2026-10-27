"""Progress groups, personal records and day streaks over a temporary database."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from numbra.core.challenge import AnswerAttempt, CompletedTraining, StagePlan
from numbra.core.models import Difficulty, Operation, Problem, StageKind, Topic
from numbra.core.stats import Stats


def _training(
    answers: tuple[tuple[bool, float], ...] = ((True, 2.0),),
    *,
    started_at: float = 100.0,
    difficulty: Difficulty = Difficulty.NORMAL,
    strict: bool = False,
    topics: tuple[Topic, ...] = (),
    duration: float = 360.0,
    generation_version: int = 4,
) -> CompletedTraining:
    problems = tuple(
        Problem(f"{i} + 1", i + 1, (Operation.ADD,), work_units=1) for i in range(len(answers))
    )
    attempts = tuple(
        AnswerAttempt(
            stage_number=1,
            problem_number=i + 1,
            expression=problems[i].expression,
            correct_answer=problems[i].answer,
            user_answer=str(problems[i].answer if correct else 0),
            is_correct=correct,
            elapsed_seconds=elapsed,
            timed_out=False,
            operation=Operation.ADD,
            overtime_seconds=0.0,
            score=Decimal("1") if correct else Decimal("0"),
        )
        for i, (correct, elapsed) in enumerate(answers)
    )
    return CompletedTraining(
        started_at=started_at,
        difficulty=difficulty,
        seed=1,
        operations=(Operation.ADD, Operation.SUBTRACT),
        duration_target_seconds=duration,
        actual_duration_seconds=10.0,
        stages=(StagePlan(1, StageKind.NORMAL, 10.0, problems),),
        attempts=attempts,
        strict=strict,
        topics=topics,
        generation_version=generation_version,
    )


def _at(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> float:
    return datetime(year, month, day, hour, minute).timestamp()


def test_progress_history_ignores_duration_and_versions(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "progress.sqlite3")
    stats.save(_training(started_at=1.0, duration=60.0, generation_version=3))
    stats.save(_training(started_at=2.0, strict=True))
    stats.save(_training(started_at=3.0, topics=(Topic.SQRT,)))
    stats.save(_training(started_at=4.0, difficulty=Difficulty.HARD))

    history = stats.progress_history(_training())

    assert [row.started_at for row in history] == [1.0]
    assert stats.progress_history(_training(), limit=0) == []


def test_average_correct_seconds(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "average.sqlite3")
    mixed = _training(((True, 2.0), (True, 4.0), (False, 9.0)))
    wrong = _training(((False, 1.0),), started_at=200.0)
    stats.save(mixed)
    stats.save(wrong)

    assert mixed.average_correct_seconds == 3.0
    assert wrong.average_correct_seconds is None
    by_time = {row.started_at: row.average_correct_seconds for row in stats.history()}
    assert by_time == {100.0: 3.0, 200.0: None}


def test_records_best_values_per_group(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "records.sqlite3")
    stats.save(_training(((True, 3.0), (False, 1.0)), started_at=1.0))
    stats.save(_training(((True, 5.0), (True, 5.0)), started_at=2.0))
    stats.save(_training(((True, 2.5),), started_at=3.0, strict=True))

    records = stats.records()

    assert len(records) == 2
    soft = records[0]
    assert (soft.difficulty, soft.strict, soft.sessions) == ("normal", False, 2)
    assert soft.operations == ("+", "-")
    assert soft.topics == ()
    assert soft.best_score_percent == 1.0
    assert soft.best_average_correct_seconds == 3.0
    assert records[1].strict is True


def test_streak_counts_days_not_sessions(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "streak.sqlite3")
    for started_at in (_at(2026, 10, 26), _at(2026, 10, 27, 9), _at(2026, 10, 27, 18)):
        stats.save(_training(started_at=started_at))

    assert stats.streak(date(2026, 10, 27)) == (2, 2)


def test_streak_survives_until_today_trains(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "yesterday.sqlite3")
    stats.save(_training(started_at=_at(2026, 10, 26)))

    assert stats.streak(date(2026, 10, 27)) == (1, 1)


def test_streak_breaks_after_missed_day(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "broken.sqlite3")
    for day in (20, 21, 22, 25):
        stats.save(_training(started_at=_at(2026, 10, day)))

    assert stats.streak(date(2026, 10, 27)) == (0, 3)


def test_streak_uses_local_midnight(tmp_path: Path) -> None:
    stats = Stats(tmp_path / "midnight.sqlite3")
    stats.save(_training(started_at=_at(2026, 10, 26, 23, 59)))
    stats.save(_training(started_at=_at(2026, 10, 27, 0, 1)))

    assert stats.streak(date(2026, 10, 27)) == (2, 2)


def test_streak_of_empty_history(tmp_path: Path) -> None:
    assert Stats(tmp_path / "empty.sqlite3").streak(date(2026, 10, 27)) == (0, 0)
