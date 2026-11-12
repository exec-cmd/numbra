import random

from numbra.core.expressions import Expr, parse_expression
from numbra.core.missing import missing_number


def test_missing_number_equation_has_one_integer_solution() -> None:
    tree = Expr.binary("+", Expr.number(17), Expr.number(25))
    text, answer, _ = missing_number(tree, random.Random(2))  # type: ignore[misc]
    lhs, rhs = text.rsplit(" = ", 1)
    assert isinstance(answer, int) and answer in {17, 25}
    assert parse_expression(lhs.replace("?", str(answer))).evaluate() == int(rhs)
    assert all(
        parse_expression(lhs.replace("?", str(value))).evaluate() != int(rhs)
        for value in range(answer - 20, answer + 21)
        if value != answer
    )


def test_missing_number_skips_ambiguous_zero_inverses() -> None:
    rng = random.Random(1)
    zero_factor = Expr.binary("*", Expr.number(4), Expr.number(0))
    assert missing_number(zero_factor, random.Random(0))[1] == 0  # type: ignore[index]
    assert missing_number(zero_factor, random.Random(1))[1] == 0  # type: ignore[index]
    zero_quotient = missing_number(Expr.binary("/", Expr.number(0), Expr.number(4)), rng)
    assert zero_quotient is not None and zero_quotient[0].startswith("? / 4 = 0")
    zero_chain = Expr.binary("+", Expr.binary("*", Expr.number(0), Expr.number(4)), Expr.number(1))
    assert all(
        "0 * ?" not in missing_number(zero_chain, random.Random(seed))[0]  # type: ignore[index]
        for seed in range(10)
    )


def test_function_subtree_is_not_a_missing_number_candidate() -> None:
    tree = Expr.function("sin", Expr.number(30))
    assert missing_number(tree, random.Random(1)) is None


def test_generator_applies_one_in_six_missing_forms_deterministically() -> None:
    from numbra.core.generator import DifficultyProfile, ProblemGenerator
    from numbra.core.models import Operation

    profile = DifficultyProfile(1, 50, 2, 3, 1000)
    first = tuple(
        problem
        for seed in range(12)
        for problem in ProblemGenerator(profile, (Operation.ADD,), seed).generate_many(50)
    )
    second = tuple(
        problem
        for seed in range(12)
        for problem in ProblemGenerator(profile, (Operation.ADD,), seed).generate_many(50)
    )
    share = sum("?" in problem.expression for problem in first) / len(first)
    assert 0.12 <= share <= 0.22
    assert first == second
    for problem in first:
        if "?" in problem.expression:
            assert isinstance(problem.answer, int)
            lhs, rhs = problem.expression.rsplit(" = ", 1)
            assert parse_expression(lhs.replace("?", str(problem.answer))).evaluate() == int(rhs)


def test_form_keeps_problem_metadata_and_skips_special_families() -> None:
    from numbra.core.generator import DifficultyProfile, ProblemGenerator, canonical_problem_key
    from numbra.core.models import Operation, Problem

    tree = Expr.binary("+", Expr.number(17), Expr.number(25))
    original = Problem("17 + 25", 42, (Operation.ADD,), tree=tree, work_units=3)
    generator = ProblemGenerator(DifficultyProfile(1, 50), (Operation.ADD,), 1)
    generator._forms = random.Random(1)
    formed = generator._apply_forms(original)
    assert "?" in formed.expression
    assert canonical_problem_key(formed) == canonical_problem_key(original)
    assert (formed.work_units, formed.operations, formed.tree) == (
        original.work_units,
        original.operations,
        original.tree,
    )
    forms_rng = random.Random(1)
    forms_rng.random()
    assert formed.solution_steps == missing_number(tree, random.Random(forms_rng.random()))[2]  # type: ignore[index]
    for family in ("tricks", "funbox"):
        generator._forms = random.Random(1)
        assert (
            "?"
            not in generator._apply_forms(
                Problem("17 + 25", 42, (Operation.ADD,), tree=tree, family=family)
            ).expression
        )
