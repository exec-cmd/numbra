from fractions import Fraction

import pytest

from numbra.core.expressions import (
    Expr,
    canonical_key,
    expression_operations,
    meaningful,
    parse_expression,
    solution_steps,
    valid_bounds,
    work_units,
)
from numbra.core.models import Difficulty, Operation, Problem, Topic


def test_model_adds_topics_and_expression_metadata_without_shifting_positional_fields() -> None:
    assert [item.value for item in Difficulty] == ["easy", "normal", "hard", "very-hard"]
    problem = Problem("2 + 3", 5, (Operation.ADD,))
    assert problem.family == "arithmetic"
    assert problem.topics == ()
    assert problem.as_tree() == Expr.binary("+", Expr.number(2), Expr.number(3))
    assert problem.evaluate() == 5
    assert tuple(item.value for item in Topic) == ("sqrt", "trig", "log", "power", "identities")


def test_tree_evaluation_is_exact_and_does_not_trust_answer() -> None:
    tree = Expr.binary("/", Expr.number(1), Expr.number(3))
    problem = Problem("unused", 99, (), tree=tree)
    assert problem.evaluate() == Fraction(1, 3)
    assert problem.evaluate() != problem.answer


def test_legacy_expression_parser_preserves_precedence_and_rejects_unsafe_ast() -> None:
    assert parse_expression("20 + 15 * 8").evaluate() == 140
    assert Problem("20 + 15 * 8", -1, ()).evaluate() == 140
    for text in ("__import__('os').system('id')", "1 // 0", "x + 1", "[1, 2]"):
        with pytest.raises(ValueError):
            parse_expression(text)


def test_exact_fraction_division_and_restricted_powers() -> None:
    assert parse_expression("1 / 3 + 1 / 6").evaluate() == Fraction(1, 2)
    assert parse_expression("(2 + 3) ^ 2").evaluate() == 25
    for text in ("1 / 0", "2 ^ 4", "2 ^ -1"):
        with pytest.raises(ValueError):
            parse_expression(text).evaluate()


@pytest.mark.parametrize(
    "text,expected",
    [
        ("(2 ^ 3) ^ 2", 64),
        ("5 * (9 / 3)", 15),
        ("5 + (9 - 3)", 11),
        ("(-2) ^ 2", 4),
        ("(-2) ^ 3", -8),
    ],
)
def test_render_roundtrips_tree_association_and_negative_bases(text: str, expected: int) -> None:
    original = parse_expression(text)
    rendered = original.render()
    assert parse_expression(rendered).evaluate() == original.evaluate() == expected


def test_square_roots_are_exact_and_trigonometry_renders_degrees() -> None:
    assert Expr.function("sqrt", Expr.number(144)).evaluate() == 12
    with pytest.raises(ValueError):
        Expr.function("sqrt", Expr.number(2)).evaluate()
    assert Expr.function("sin", Expr.number(30)).render() == "sin(30°)"


def test_trigonometry_accepts_exactly_the_rational_table_values() -> None:
    rational = {
        "sin": {
            0: 0,
            30: Fraction(1, 2),
            90: 1,
            150: Fraction(1, 2),
            180: 0,
            210: Fraction(-1, 2),
            270: -1,
            330: Fraction(-1, 2),
        },
        "cos": {
            0: 1,
            60: Fraction(1, 2),
            90: 0,
            120: Fraction(-1, 2),
            180: -1,
            240: Fraction(-1, 2),
            270: 0,
            300: Fraction(1, 2),
        },
        "tan": {0: 0, 180: 0},
    }
    for name in ("sin", "cos", "tan"):
        for angle in range(0, 360, 30):
            expr = Expr.function(name, Expr.number(angle))
            if angle in rational[name]:
                assert expr.evaluate() == rational[name][angle]
            else:
                with pytest.raises(ValueError):
                    expr.evaluate()
    for angle, value in {45: 1, 135: -1, 225: 1, 315: -1}.items():
        assert Expr.function("tan", Expr.number(angle)).evaluate() == value


def test_logarithms_use_exact_integer_bases_and_negative_exponents() -> None:
    for base in (2, 3, 5, 10):
        for exponent in range(-3, 5):
            argument = (
                Expr.number(base**exponent)
                if exponent >= 0
                else Expr.binary("/", Expr.number(1), Expr.number(base**-exponent))
            )
            assert Expr.function("log", Expr.number(base), argument).evaluate() == exponent
    with pytest.raises(ValueError):
        Expr.function("log", Expr.number(2), Expr.number(12)).evaluate()


def test_operations_are_postorder_arithmetic_only() -> None:
    expr = Expr.function(
        "sin",
        Expr.binary("+", Expr.number(30), Expr.binary("*", Expr.number(2), Expr.number(3))),
    )
    assert expression_operations(expr) == ("*", "+")


def test_canonical_key_flattens_associative_commutative_operations() -> None:
    a, b, c = (Expr.number(n) for n in (2, 3, 4))
    left = Expr.binary("+", Expr.binary("+", a, b), c)
    right = Expr.binary("+", c, Expr.binary("+", b, a))
    assert canonical_key(left) == canonical_key(right)


def test_meaningful_rejects_cancellation_and_degenerate_arithmetic() -> None:
    a, b = Expr.number(7), Expr.number(3)
    bad = (
        Expr.binary("-", a, a),
        Expr.binary("/", a, a),
        Expr.binary(
            "/",
            Expr.binary("+", Expr.number(3), Expr.number(5)),
            Expr.number(8),
        ),
        Expr.binary("*", Expr.number(0), a),
        Expr.binary("*", Expr.number(1), a),
        Expr.binary("-", Expr.binary("+", a, b), b),
        Expr.binary("/", Expr.binary("*", a, b), b),
        Expr.binary("+", a, Expr.binary("-", b, b)),
        Expr.binary("+", a, Expr.number(0)),
        Expr.binary("-", a, Expr.number(0)),
        Expr.binary("/", a, Expr.number(1)),
        Expr.binary("^", Expr.number(0), Expr.number(2)),
        Expr.binary("^", Expr.number(1), Expr.number(2)),
        Expr.binary("^", Expr.number(-1), Expr.number(3)),
        Expr.binary("/", Expr.binary("^", Expr.number(7), Expr.number(2)), Expr.number(7)),
        Expr.binary(
            "/",
            Expr.binary("^", Expr.number(7), Expr.number(3)),
            Expr.binary("^", Expr.number(7), Expr.number(2)),
        ),
    )
    assert all(not meaningful(expr) for expr in bad)
    assert meaningful(Expr.binary("+", a, b))


def test_bounds_check_every_exact_intermediate_and_denominator() -> None:
    assert valid_bounds(parse_expression("20 / 5 + 3 * 4"), 20)
    assert not valid_bounds(parse_expression("20 / 5 + 3 * 4"), 10)
    assert not valid_bounds(parse_expression("1 / 13"), 100)
    assert not valid_bounds(parse_expression("1 / 0"), 100)


def test_work_units_reward_shortcuts_and_decimal_structure() -> None:
    assert work_units(parse_expression("20 * 20")) < work_units(parse_expression("37 * 13"))
    assert work_units(parse_expression("2 * 8")) == 1
    assert work_units(parse_expression("20 + 30")) == 1
    assert work_units(parse_expression("19 + 21")) < work_units(parse_expression("18 + 27"))
    assert work_units(parse_expression("350 / 100")) == 1
    assert work_units(parse_expression("8 + 7")) > work_units(parse_expression("2 + 3"))
    assert work_units(parse_expression("18 / 9")) == 1
    assert work_units(parse_expression("2 ^ 2 * 3 ^ 2")) < 6
    assert work_units(parse_expression("18 ^ 2 / 9 ^ 2 + 354")) < 6


def test_solution_steps_are_exact_and_show_shortcuts() -> None:
    assert solution_steps(parse_expression("20 * 20")) == (
        "20 * 20: 2 * 2 = 4; restore 2 zero(s) = 400",
    )
    assert solution_steps(parse_expression("49 * 51")) == ("49 * 51: 50^2 - 1^2 = 2500 - 1 = 2499",)
    assert solution_steps(parse_expression("sin(30°)")) == (
        "sin(30°) = 1/2 (exact degree-table value)",
    )
    assert solution_steps(parse_expression("log(2, 1 / 8)"))[-1] == (
        "2^-3 = 1/8, so log(2, 1 / 8) = -3"
    )
