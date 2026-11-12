from __future__ import annotations

import random

from numbra.core.expressions import canonical_key, parse_expression
from numbra.core.generator import DifficultyProfile, ProblemGenerator, canonical_problem_key
from numbra.core.models import Operation, Problem, Topic
from numbra.core.permutation import permute_operands


def test_commutative_forms_vary_for_addition_and_multiplication() -> None:
    for expression in ("7 + 25", "7 * 25"):
        tree = parse_expression(expression)
        forms = {permute_operands(tree, random.Random(seed)).render() for seed in range(400)}
        assert forms == {
            expression,
            expression.replace("7", "TEMP").replace("25", "7").replace("TEMP", "25"),
        }


def test_key_value_and_metadata_survive_permutation() -> None:
    tree = parse_expression("7 + 25 * 3")
    original = Problem(
        "7 + 25 * 3", 82, (Operation.ADD, Operation.MULTIPLY), tree=tree, work_units=7
    )
    permuted_tree = permute_operands(tree, random.Random(4))
    permuted = Problem(
        permuted_tree.render(),
        permuted_tree.evaluate(),
        original.operations,
        tree=permuted_tree,
        work_units=original.work_units,
    )

    assert canonical_key(permuted_tree) == canonical_key(tree)
    assert canonical_problem_key(permuted) == canonical_problem_key(original)
    assert (
        permuted_tree.evaluate(),
        permuted.answer,
        permuted.work_units,
        permuted.operations,
    ) == (tree.evaluate(), original.answer, original.work_units, original.operations)


def test_permutation_adds_no_brackets_and_parses_to_same_value() -> None:
    tree = parse_expression("7 + (25 - 3) + 4 * (8 / 2)")
    permuted = permute_operands(tree, random.Random(9))

    assert permuted.render().count("(") <= tree.render().count("(")
    assert parse_expression(permuted.render()).evaluate() == tree.evaluate()


def test_generated_session_has_no_duplicate_canonical_keys() -> None:
    for seed in (1, 7, 42):
        profile = DifficultyProfile(1, 500, 2, 3, 10_000)
        problems = ProblemGenerator(
            profile, (Operation.ADD, Operation.MULTIPLY), seed
        ).generate_many(80)
        keys = [canonical_problem_key(problem) for problem in problems]
        assert len(keys) == len(set(keys))


def test_subtraction_and_division_are_never_swapped() -> None:
    for expression in ("25 - 7", "28 / 7"):
        tree = parse_expression(expression)
        assert permute_operands(tree, random.Random(2)) == tree


def test_trick_metadata_survives_permutation() -> None:
    generator = ProblemGenerator(
        DifficultyProfile(1, 100, 2, 2, 10_000), (), 17, topics=(Topic.TRICKS,)
    )
    problems = generator.generate_many(80)

    assert problems
    assert all(problem.family == "tricks" for problem in problems)
    assert all(problem.strategy and problem.work_units is not None for problem in problems)
    assert all(problem.answer == problem.evaluate() for problem in problems)


def test_forms_are_seeded_and_do_not_advance_arithmetic_rng() -> None:
    profile = DifficultyProfile(1, 500, 2, 3, 10_000)
    first = ProblemGenerator(profile, (Operation.ADD, Operation.MULTIPLY), 91)
    second = ProblemGenerator(profile, (Operation.ADD, Operation.MULTIPLY), 91)

    first_batch = first.generate_many(50)
    second_batch = second.generate_many(50)
    assert first_batch == second_batch
    assert first._random.getstate() == second._random.getstate()
