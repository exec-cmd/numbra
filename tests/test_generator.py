from __future__ import annotations

import pytest

from numbra.core.generator import (
    DifficultyProfile,
    GenerationError,
    ProblemGenerator,
    canonical_problem_key,
)
from numbra.core.models import Difficulty, Operation, Problem
from numbra.core.stages import StageKind, allocate_stage_kinds


def test_same_seed_reproduces_problems() -> None:
    profile = DifficultyProfile(min_value=1, max_value=20, min_terms=2, max_terms=3)
    first = ProblemGenerator(profile, (Operation.ADD, Operation.DIVIDE), 42)
    second = ProblemGenerator(profile, (Operation.ADD, Operation.DIVIDE), 42)
    assert [first.generate() for _ in range(10)] == [second.generate() for _ in range(10)]


def test_brackets_toggle_changes_only_expression_and_keeps_keys() -> None:
    profile = DifficultyProfile(1, 20, 4, 4)
    grouped = ProblemGenerator(profile, (Operation.ADD, Operation.SUBTRACT), 42)
    plain = ProblemGenerator(profile, (Operation.ADD, Operation.SUBTRACT), 42, brackets=False)
    grouped_problems = grouped.generate_many(20)
    plain_problems = plain.generate_many(20)

    assert [p.expression.replace("(", "").replace(")", "") for p in grouped_problems] == [
        p.expression.replace("(", "").replace(")", "") for p in plain_problems
    ]
    assert [canonical_problem_key(p) for p in grouped_problems] == [
        canonical_problem_key(p) for p in plain_problems
    ]
    assert [p.answer for p in grouped_problems] == [p.answer for p in plain_problems]


@pytest.mark.parametrize("seed", (1, 2, 3, 42))
def test_hard_stage_length_orders_are_shuffled_per_stage(seed: int) -> None:
    profile = DifficultyProfile(1, 100, 3, 8, 10_000)
    generator = ProblemGenerator(
        profile,
        (Operation.ADD, Operation.SUBTRACT, Operation.MULTIPLY, Operation.DIVIDE),
        seed,
        difficulty=Difficulty.HARD,
    )

    stages = generator.generate_progressive_batches((7, 7, 7))
    length_orders = [tuple(len(problem.operations) + 1 for problem in stage) for stage in stages]

    assert len(set(length_orders)) > 1


def test_generated_problem_is_correct_and_division_is_integral() -> None:
    profile = DifficultyProfile(min_value=1, max_value=50, min_terms=2, max_terms=4)
    generator = ProblemGenerator(profile, tuple(Operation), 7)
    for _ in range(50):
        problem = generator.generate()
        assert problem.as_tree().evaluate() == problem.evaluate()
        if "?" not in problem.expression:
            assert problem.answer == problem.evaluate()
        if Operation.DIVIDE in problem.operations:
            assert problem.answer.denominator == 1


def test_division_does_not_use_the_same_number_as_divisor() -> None:
    profile = DifficultyProfile(min_value=1, max_value=50, min_terms=2, max_terms=2)
    problems = ProblemGenerator(profile, (Operation.DIVIDE,), 7).generate_many(20)

    assert all(
        left != right for problem in problems for left, right in [problem.expression.split(" / ")]
    )


def test_stage_distribution_is_exact_and_scales() -> None:
    assert allocate_stage_kinds(3) == (StageKind.SLOW, StageKind.NORMAL, StageKind.FAST)
    assert allocate_stage_kinds(6) == (
        StageKind.SLOW,
        StageKind.NORMAL,
        StageKind.FAST,
        StageKind.SLOW,
        StageKind.NORMAL,
        StageKind.FAST,
    )
    assert len(allocate_stage_kinds(7)) == 7


def test_generate_many_does_not_repeat_commutative_examples() -> None:
    profile = DifficultyProfile(min_value=1, max_value=10, min_terms=2, max_terms=2)
    problems = ProblemGenerator(profile, (Operation.ADD,), 42).generate_many(10)

    assert len({canonical_problem_key(problem) for problem in problems}) == 10


def test_generate_many_balances_selected_operations() -> None:
    profile = DifficultyProfile(min_value=1, max_value=50, min_terms=2, max_terms=2)
    problems = ProblemGenerator(profile, tuple(Operation), 42).generate_many(20)

    counts = {
        operation: sum(operation in problem.operations for problem in problems)
        for operation in Operation
    }

    assert max(counts.values()) - min(counts.values()) <= 2


def test_generate_many_supports_four_terms_and_negative_answers() -> None:
    profile = DifficultyProfile(min_value=1, max_value=10, min_terms=4, max_terms=4)
    problems = ProblemGenerator(profile, (Operation.SUBTRACT,), 4).generate_many(8)

    assert all(len(problem.operations) == 3 for problem in problems)
    assert any(problem.answer < 0 for problem in problems)


def test_generate_many_rejects_an_impossible_profile() -> None:
    profile = DifficultyProfile(min_value=10, max_value=10, min_terms=4, max_terms=4)

    with pytest.raises(GenerationError):
        ProblemGenerator(profile, (Operation.DIVIDE,), 42).generate_many(1)


def test_power_only_generation_avoids_impossible_four_term_chains() -> None:
    profile = DifficultyProfile(
        min_value=10,
        max_value=999,
        min_terms=3,
        max_terms=4,
        max_result=10_000,
        term_weights=((3, 2), (4, 8)),
    )

    problems = ProblemGenerator(profile, (Operation.POWER,), 42).generate_many(8)

    assert all(2 <= len(problem.operations) + 1 <= 3 for problem in problems)


def test_canonical_key_collapses_commutative_operand_order() -> None:
    first = Problem("2 + 3", 5, (Operation.ADD,))
    second = Problem("3 + 2", 5, (Operation.ADD,))

    assert canonical_problem_key(first) == canonical_problem_key(second)


def test_custom_term_range_remains_usable_without_matching_weights() -> None:
    profile = DifficultyProfile(
        min_value=1,
        max_value=10,
        min_terms=4,
        max_terms=4,
        term_weights=((2, 1), (3, 1)),
    )

    problems = ProblemGenerator(profile, (Operation.ADD,), 42).generate_many(1)

    assert len(problems[0].operations) == 3


def test_small_arithmetic_pool_repeats_with_warning_and_determinism() -> None:
    profile = DifficultyProfile(1, 2, 2, 2, 10)
    first = ProblemGenerator(profile, (Operation.ADD,), 42)
    second = ProblemGenerator(profile, (Operation.ADD,), 42)
    first_batch = first.generate_many(20)
    second_batch = second.generate_many(20)

    assert first_batch == second_batch
    assert first.warnings == [
        "Selected settings require repeated arithmetic exercises; unique catalog exhausted."
    ]
    assert len({canonical_problem_key(problem) for problem in first_batch}) < len(first_batch)


def test_hard_arithmetic_band_is_4_to_16() -> None:
    from numbra.config.models import ChallengeConfig
    from numbra.core.generator import WORK_BANDS, DifficultyProfile, complexity_score
    from numbra.core.models import BASIC_OPERATIONS

    assert WORK_BANDS[Difficulty.HARD] == (4, 16)
    config = ChallengeConfig().profiles[Difficulty.HARD]
    profile = DifficultyProfile(
        config.min_value, config.max_value, config.min_terms, config.max_terms, config.max_result
    )
    generator = ProblemGenerator(profile, BASIC_OPERATIONS, 7, difficulty=Difficulty.HARD)
    assert all(4 <= complexity_score(p) - 2 <= 16 for p in generator.generate_many(60))
