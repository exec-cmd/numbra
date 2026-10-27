from __future__ import annotations

from collections import Counter
from fractions import Fraction
from pathlib import Path

import pytest

from numbra.config import ConfigManager, ConfigPaths
from numbra.config.models import (
    ChallengeConfig,
    DifficultyConfig,
    OperationTimingConfig,
    Settings,
)
from numbra.core.challenge import (
    Challenge,
    ChallengeOptions,
    StagePlan,
    TrainingSession,
)
from numbra.core.expressions import Expr, valid_bounds
from numbra.core.generator import (
    GenerationError,
    canonical_problem_key,
    complexity_score,
)
from numbra.core.models import Difficulty, Operation, Problem, StageKind, Topic


def _settings(challenge: ChallengeConfig | None = None) -> Settings:
    return Settings(challenge or ChallengeConfig(), (), {})


def _number_leaves(problem: Problem) -> tuple[int, ...]:
    def visit(node: Expr) -> tuple[int, ...]:
        if node.kind == "number":
            return (node.value,)
        return tuple(value for child in node.args for value in visit(child))

    return visit(problem.as_tree())


def test_generated_problems_obey_configured_operand_and_result_bounds() -> None:
    base = ChallengeConfig()
    profile = DifficultyConfig(3, 7, 2, 2, 25)
    challenge_config = ChallengeConfig(
        duration_minutes=1,
        difficulty=Difficulty.EASY,
        stages=3,
        operations=(Operation.ADD,),
        profiles=base.profiles | {Difficulty.EASY: profile},
        stage_limits={kind: 1.0 for kind in StageKind},
        operation_timing=OperationTimingConfig(enabled=False),
    )

    session = Challenge(_settings(challenge_config)).create_session(
        ChallengeOptions(seed=7, difficulty=Difficulty.EASY, operations=(Operation.ADD,))
    )
    problems = [problem for stage in session.stages for problem in stage.problems]

    assert problems
    assert all(
        all(profile.min_value <= value <= profile.max_value for value in _number_leaves(problem))
        and valid_bounds(problem.as_tree(), profile.max_result)
        for problem in problems
    )


def test_short_budget_reports_minimum_duration() -> None:
    challenge_config = ChallengeConfig(
        operation_timing=OperationTimingConfig(True, {Operation.ADD: 50.0})
    )

    with pytest.raises(GenerationError, match="minimum duration: 2 minutes"):
        Challenge(_settings(challenge_config)).create_session(
            ChallengeOptions(
                duration_minutes=1,
                stages=1,
                operations=(Operation.ADD,),
                seed=1,
            )
        )


def test_fraction_answers_are_exact_and_invalid_numeric_input_is_wrong() -> None:
    problem = Problem(
        expression="sin(30°)",
        answer=Fraction(1, 2),
        operations=(),
        topics=(Topic.TRIG,),
    )
    stage = StagePlan(1, StageKind.NORMAL, 10.0, (problem,))
    session = TrainingSession(
        started_at=0.0,
        difficulty=Difficulty.EASY,
        seed=1,
        operations=(),
        target_seconds=10.0,
        stages=(stage,),
        operation_timing=OperationTimingConfig(enabled=False),
    )

    assert session.submit(0, 0, "1/2", 0.5).is_correct
    assert session.submit(0, 0, "0.5", 0.5).is_correct
    assert not session.submit(0, 0, "0.5000000001", 0.5).is_correct
    for answer in ("not a number", "1/0", "nan", ""):
        assert not session.submit(0, 0, answer, 0.5).is_correct


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


def test_operation_bonus_changes_problem_limit(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(seed=8, stages=1, operations=(Operation.MULTIPLY,))
    )
    problem = session.stages[0].problems[0]
    assert session.time_limit_for(0, 0) == session.stages[0].limit_seconds + 1.0 * len(
        problem.operations
    ) + max(0, complexity_score(problem) - 4)


def test_seeded_session_keeps_comparable_complexity_between_stages(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(settings).create_session(
        ChallengeOptions(
            difficulty=Difficulty.HARD,
            seed=42,
            stages=3,
            duration_minutes=3,
            operations=(Operation.ADD, Operation.SUBTRACT, Operation.MULTIPLY, Operation.DIVIDE),
        )
    )

    stage_complexities = [
        sum(complexity_score(problem) for problem in stage.problems) / len(stage.problems)
        for stage in session.stages
    ]

    assert max(stage_complexities) - min(stage_complexities) <= 1.0


def test_seed_reproduces_staged_problem_progression(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    options = ChallengeOptions(difficulty=Difficulty.HARD, seed=42, stages=3, duration_minutes=3)

    first = Challenge(settings).create_session(options)
    second = Challenge(settings).create_session(options)

    assert first.stages == second.stages


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
        Difficulty.EASY: (2, 2),
        Difficulty.NORMAL: (2, 3),
        Difficulty.HARD: (3, 4),
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


def test_challenge_persists_wall_clock_timestamp(tmp_path: Path) -> None:
    settings = ConfigManager(ConfigPaths.from_root(tmp_path / "config")).load_or_create()
    session = Challenge(
        settings,
        clock=lambda: 12.0,
        wall_clock=lambda: 1_700_000_000.0,
    ).create_session(ChallengeOptions(stages=1, seed=1, operations=(Operation.ADD,)))

    assert session.started_at == 1_700_000_000.0


def test_budget_boundary_does_not_consume_unshown_unique_exercises() -> None:
    from dataclasses import replace

    from numbra.config.models import DifficultyConfig, OperationTimingConfig

    config = ChallengeConfig()
    config = replace(
        config,
        profiles=config.profiles | {Difficulty.EASY: DifficultyConfig(1, 10, 2, 2, 20)},
        operation_timing=OperationTimingConfig(enabled=False),
    )
    session = Challenge(Settings(config, (), {})).create_session(
        ChallengeOptions(
            seed=7, difficulty=Difficulty.EASY, operations=(Operation.DIVIDE,), duration_minutes=1
        )
    )
    problems = [p for stage in session.stages for p in stage.problems]
    assert len(problems) == 7
    assert len({canonical_problem_key(p) for p in problems}) == 7
    assert not session.warnings
