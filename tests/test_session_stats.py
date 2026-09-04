from pathlib import Path

from numbra.config import ConfigManager, ConfigPaths
from numbra.core.challenge import Challenge, ChallengeOptions
from numbra.core.models import Difficulty, Operation, StageKind
from numbra.core.stages import allocate_stage_kinds
from numbra.core.stats import Stats


def test_session_has_multiple_problems_and_records_timeout(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(difficulty=Difficulty.NORMAL, seed=3, stages=3)
    )
    assert len(session.stages) == 3
    assert all(len(stage.problems) >= 1 for stage in session.stages)
    attempt = session.submit(0, 0, None, elapsed_seconds=10.0, timed_out=True)
    assert attempt.timed_out is True
    completed = session.complete(actual_duration=12.0)
    assert completed.timeouts == 1
    assert completed.total_examples == sum(len(stage.problems) for stage in session.stages)


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


def test_operation_bonus_changes_problem_limit(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.MULTIPLY,))
    )
    problem = session.stages[0].problems[0]
    assert session.time_limit_for(0, 0) == session.stages[0].limit_seconds + 1.0 * len(
        problem.operations
    )


def test_stats_reset_removes_history_but_keeps_schema(tmp_path: Path) -> None:
    database = tmp_path / "history.sqlite3"
    stats = Stats(database)
    stats.reset()
    assert database.exists()
    assert stats.history() == []


def test_all_difficulty_distributions_have_exact_stage_count() -> None:
    assert allocate_stage_kinds(3) == (StageKind.FAST, StageKind.NORMAL, StageKind.SLOW)
    assert len(allocate_stage_kinds(7)) == 7
