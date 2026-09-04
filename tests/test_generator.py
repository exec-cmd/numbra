import pytest

from numbra.core.generator import (
    DifficultyProfile,
    GenerationError,
    ProblemGenerator,
    canonical_problem_key,
)
from numbra.core.models import Operation, Problem
from numbra.core.stages import StageKind, allocate_stage_kinds


def test_same_seed_reproduces_problems() -> None:
    profile = DifficultyProfile(min_value=1, max_value=20, min_terms=2, max_terms=3)
    first = ProblemGenerator(profile, (Operation.ADD, Operation.DIVIDE), 42)
    second = ProblemGenerator(profile, (Operation.ADD, Operation.DIVIDE), 42)
    assert [first.generate() for _ in range(10)] == [second.generate() for _ in range(10)]


def test_generated_problem_is_correct_and_division_is_integral() -> None:
    profile = DifficultyProfile(min_value=1, max_value=50, min_terms=2, max_terms=4)
    generator = ProblemGenerator(profile, tuple(Operation), 7)
    for _ in range(50):
        problem = generator.generate()
        assert problem.answer == problem.evaluate()
        if Operation.DIVIDE in problem.operations:
            assert problem.answer.denominator == 1


def test_stage_distribution_is_exact_and_scales() -> None:
    assert allocate_stage_kinds(3) == (StageKind.FAST, StageKind.NORMAL, StageKind.SLOW)
    assert allocate_stage_kinds(6) == (
        StageKind.FAST,
        StageKind.NORMAL,
        StageKind.SLOW,
        StageKind.FAST,
        StageKind.NORMAL,
        StageKind.SLOW,
    )


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

    assert counts == {operation: 4 for operation in Operation}


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
