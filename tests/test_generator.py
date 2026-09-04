from numbra.core.generator import DifficultyProfile, ProblemGenerator
from numbra.core.models import Difficulty, Operation
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
    assert allocate_stage_kinds(Difficulty.EASY, 3) == (
        StageKind.NORMAL,
        StageKind.SLOW,
        StageKind.SLOW,
    )
    assert allocate_stage_kinds(Difficulty.HARD, 3).count(StageKind.FAST) == 2
    assert len(allocate_stage_kinds(Difficulty.NORMAL, 8)) == 8
