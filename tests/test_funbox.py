from __future__ import annotations

import operator
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from numbra.config import ConfigManager, ConfigPaths
from numbra.core.challenge import Challenge, ChallengeOptions, _matches_answer
from numbra.core.funbox import (
    FunboxGenerator,
    FunboxMode,
    GraphSpec,
    format_answer,
    parse_funbox_modes,
)
from numbra.core.funbox import generator as funbox_generator
from numbra.core.funbox.equations import inequality_answer
from numbra.core.generator import canonical_problem_key
from numbra.core.models import Difficulty, Problem, parse_inequality

BANDS = {Difficulty.EASY: (1, 2), Difficulty.NORMAL: (2, 5), Difficulty.HARD: (4, 9)}
ALL_CASES = [(mode, level) for mode in FunboxMode for level in Difficulty]
INTEGER_CASES = [case for case in ALL_CASES if case[0] is not FunboxMode.FRACTIONS]


def _integral(answer: object) -> bool:
    if isinstance(answer, (bool, int)):
        return True
    if isinstance(answer, Fraction):
        return answer.denominator == 1
    if isinstance(answer, (tuple, frozenset)):
        return all(item.denominator == 1 for item in answer)
    if isinstance(answer, str):
        return parse_inequality(answer) is not None
    raise AssertionError(f"unexpected answer type {type(answer).__name__}")


def _generate(mode: FunboxMode, level: Difficulty, seed: int = 11, count: int = 40):
    generator = FunboxGenerator((mode,), level, seed)
    return generator, generator.generate_many(count)


@pytest.mark.parametrize(("mode", "level"), ALL_CASES)
def test_seed_reproduces_the_sequence(mode: FunboxMode, level: Difficulty) -> None:
    _, first = _generate(mode, level)
    _, second = _generate(mode, level)
    assert [(p.expression, p.answer) for p in first] == [(p.expression, p.answer) for p in second]


@pytest.mark.parametrize(("mode", "level"), ALL_CASES)
def test_problems_are_unique_and_warning_free(mode: FunboxMode, level: Difficulty) -> None:
    generator, problems = _generate(mode, level)
    expressions = [problem.expression for problem in problems]
    assert len(set(expressions)) == len(expressions) == 40
    assert generator.warnings == []


@pytest.mark.parametrize(("mode", "level"), ALL_CASES)
def test_problems_carry_funbox_fields_and_work_units_in_band(
    mode: FunboxMode, level: Difficulty
) -> None:
    _, problems = _generate(mode, level)
    low, high = BANDS[level]
    for problem in problems:
        assert problem.family == "funbox"
        assert problem.strategy == mode.value
        assert problem.tree is None
        assert problem.operations == ()
        assert problem.topics == ()
        assert low <= problem.work_units <= high
        assert (problem.graph is not None) is (mode is FunboxMode.GRAPHS)


@pytest.mark.parametrize(("mode", "level"), INTEGER_CASES)
def test_answers_are_integral_except_fractions(mode: FunboxMode, level: Difficulty) -> None:
    _, problems = _generate(mode, level)
    assert all(_integral(problem.answer) for problem in problems)


@pytest.mark.parametrize("level", list(Difficulty))
def test_fractions_mode_gives_exact_fractions_with_small_denominators(level: Difficulty) -> None:
    _, problems = _generate(FunboxMode.FRACTIONS, level)
    fractions = [Fraction(problem.answer) for problem in problems]
    assert any(answer.denominator != 1 for answer in fractions)
    assert all(answer.denominator <= 12 for answer in fractions)


@pytest.mark.parametrize(("mode", "level"), ALL_CASES)
def test_every_answer_is_accepted_in_its_display_form(mode: FunboxMode, level: Difficulty) -> None:
    _, problems = _generate(mode, level)
    for problem in problems:
        assert _matches_answer(format_answer(problem.answer), problem.answer), problem.expression


def test_graph_points_stay_in_the_grid() -> None:
    for level in Difficulty:
        _, problems = _generate(FunboxMode.GRAPHS, level, count=60)
        for problem in problems:
            graph = problem.graph
            assert graph is not None
            if graph.kind == "place":
                x, y = problem.answer
                assert -10 <= x <= 10 and -10 <= y <= 10
                assert graph.x == x
                assert sum(c * graph.x**p for p, c in enumerate(graph.coefficients)) == y
            elif graph.figure == "parabola":
                h, k = problem.answer
                assert -10 <= h <= 10 and -10 <= k <= 10
            else:
                slope, intercept = problem.answer
                assert graph.coefficients == (intercept, slope)
                assert all(abs(slope * x + intercept) <= 10 for x in range(-4, 5))


def test_repeats_are_allowed_only_after_the_mode_is_exhausted(monkeypatch) -> None:
    def constant(rng, level, units) -> Problem:
        return Problem(
            expression="same",
            answer=True,
            operations=(),
            family="funbox",
            strategy="logic",
            work_units=units,
        )

    monkeypatch.setitem(funbox_generator._MAKERS, FunboxMode.LOGIC, constant)
    generator = FunboxGenerator((FunboxMode.LOGIC,), Difficulty.EASY, 1)
    assert [p.expression for p in generator.generate_many(2)] == ["same", "same"]
    generator.generate_many(3)
    assert len(generator.warnings) == 1


def test_modes_rotate_by_least_used_count() -> None:
    generator = FunboxGenerator(
        (FunboxMode.LOGIC, FunboxMode.DERIVATIVES, FunboxMode.EQUATIONS), Difficulty.NORMAL, 3
    )
    counts: dict[str, int] = {}
    for problem in generator.generate_many(9):
        counts[problem.strategy] = counts.get(problem.strategy, 0) + 1
    assert counts == {"logic": 3, "derivatives": 3, "equations": 3}


def test_empty_mode_list_is_rejected() -> None:
    with pytest.raises(ValueError, match="at least one funbox mode"):
        FunboxGenerator((), Difficulty.EASY, 1)


def test_parse_funbox_modes_keeps_canonical_order_and_rejects_unknown() -> None:
    assert parse_funbox_modes("logic, Equations,logic") == (
        FunboxMode.EQUATIONS,
        FunboxMode.LOGIC,
    )
    with pytest.raises(ValueError, match="unsupported funbox mode 'nope'"):
        parse_funbox_modes("logic,nope")
    with pytest.raises(ValueError, match="must not be empty"):
        parse_funbox_modes(" , ")


@pytest.mark.parametrize(
    ("value", "expected", "matches"),
    [
        ("x > 4", "x>4", True),
        (">4", "x>4", True),
        ("x>4", "x>4", True),
        ("x ≥ 4", "x>=4", True),
        ("x <= -2", "x<=-2", True),
        ("x≤-2", "x<=-2", True),
        ("x >= 4", "x>4", False),
        ("x < 4", "x>4", False),
        ("4", "x>4", False),
        ("x = 4", "x=4", False),
    ],
)
def test_inequality_text_matching(value: str, expected: str, matches: bool) -> None:
    assert _matches_answer(value, expected) is matches


@pytest.mark.parametrize(
    ("slope", "relation", "root", "expected"),
    [
        (2, ">", 4, "x>4"),
        (-2, "<", 3, "x>3"),
        (-1, ">=", 5, "x<=5"),
        (-3, "<=", -2, "x>=-2"),
    ],
)
def test_negative_slope_flips_the_inequality(
    slope: int, relation: str, root: int, expected: str
) -> None:
    assert inequality_answer(slope, relation, root) == expected


RELATIONS = {
    ">": operator.gt,
    "<": operator.lt,
    ">=": operator.ge,
    "<=": operator.le,
}


def test_inequality_answer_agrees_with_the_inequality_everywhere() -> None:
    constant = 5
    for slope in (-4, -1, 1, 3):
        for relation, compare in RELATIONS.items():
            for root in (-2, 0, 3):
                bound = slope * root + constant
                canonical = parse_inequality(inequality_answer(slope, relation, root))
                assert canonical is not None
                symbol, bound_value = canonical
                for x in range(-8, 9):
                    holds = compare(slope * x + constant, bound)
                    expected = RELATIONS[symbol](x, bound_value)
                    assert holds == expected, (slope, relation, root, x)


@pytest.mark.parametrize(
    ("value", "accepted"),
    [
        ("2, 3", True),
        ("3 2", True),
        ("3;2", True),
        ("(2, 3)", True),
        ("2", False),
        ("2, 4", False),
        ("", False),
    ],
)
def test_root_sets_are_compared_without_order(value: str, accepted: bool) -> None:
    assert _matches_answer(value, frozenset({Fraction(2), Fraction(3)})) is accepted


def test_double_root_is_typed_once() -> None:
    assert _matches_answer("2", frozenset({Fraction(2)}))
    assert format_answer(frozenset({Fraction(2)})) == "2"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " True "])
def test_true_is_accepted_as_one_or_true(value: str) -> None:
    assert _matches_answer(value, True)


@pytest.mark.parametrize("value", ["0", "false", "FALSE"])
def test_false_is_accepted_as_zero_or_false(value: str) -> None:
    assert _matches_answer(value, False)


@pytest.mark.parametrize("value", ["yes", "1 0", "2"])
def test_other_words_are_not_booleans(value: str) -> None:
    assert not _matches_answer(value, True)
    assert not _matches_answer(value, False)


def test_ordered_pairs_keep_their_order() -> None:
    expected = (Fraction(4), Fraction(5))
    assert _matches_answer("4, 5", expected)
    assert _matches_answer("(4, 5)", expected)
    assert not _matches_answer("5, 4", expected)
    assert not _matches_answer("4", expected)
    assert not _matches_answer("4, 5, 6", expected)


def test_fraction_and_decimal_input_is_compared_exactly() -> None:
    assert _matches_answer("11/12", Fraction(11, 12))
    assert _matches_answer("0.75", Fraction(3, 4))
    assert not _matches_answer("0.333", Fraction(1, 3))
    assert _matches_answer("6/3", 2)


def test_format_answer_matches_the_documented_forms() -> None:
    assert format_answer(Fraction(11, 12)) == "11/12"
    assert format_answer(Fraction(4)) == "4"
    assert format_answer(Decimal("3.5")) == "3.5"
    assert format_answer(True) == "true"
    assert format_answer(False) == "false"
    assert format_answer((Fraction(4), Fraction(5))) == "4, 5"
    assert format_answer(frozenset({Fraction(3), Fraction(2)})) == "2, 3"
    assert format_answer("x>4") == "x > 4"
    assert format_answer("x>=-2") == "x >= -2"


def test_graph_spec_is_frozen_and_typed() -> None:
    spec = GraphSpec("place", "line", (-3, 2), 4)
    assert spec.coefficients == (-3, 2)
    with pytest.raises(AttributeError):
        spec.x = 5  # type: ignore[misc]


def test_canonical_key_uses_the_display_text_for_funbox() -> None:
    problem = _generate(FunboxMode.SUBSTITUTION, Difficulty.HARD, count=1)[1][0]
    assert canonical_problem_key(problem) == ("funbox", problem.expression)


def _settings(tmp_path: Path):
    return ConfigManager(ConfigPaths.from_root(tmp_path)).load_or_create()


def test_funbox_session_uses_no_operation_bonus(tmp_path: Path) -> None:
    challenge = Challenge(_settings(tmp_path))
    session = challenge.create_session(
        ChallengeOptions(
            duration_minutes=1,
            stages=1,
            seed=5,
            funbox=(FunboxMode.LOGIC,),
        )
    )
    assert session.mode == "funbox"
    problem = session.stages[0].problems[0]
    assert problem.family == "funbox"
    assert session.time_limit_for(0, 0) == session.stages[0].limit_seconds
    attempt = session.submit(0, 0, format_answer(problem.answer), elapsed_seconds=0.0)
    assert attempt.is_correct
    completed = session.complete(actual_duration=1.0)
    assert completed.mode == "funbox"
    assert completed.operations == ()


def test_funbox_fingerprint_differs_from_ordinary_sessions(tmp_path: Path) -> None:
    challenge = Challenge(_settings(tmp_path))
    ordinary = challenge.create_session(ChallengeOptions(duration_minutes=1, stages=1, seed=5))
    funbox = challenge.create_session(
        ChallengeOptions(duration_minutes=1, stages=1, seed=5, funbox=(FunboxMode.LOGIC,))
    )
    other_order = challenge.create_session(
        ChallengeOptions(
            duration_minutes=1,
            stages=1,
            seed=5,
            funbox=(FunboxMode.LOGIC, FunboxMode.EQUATIONS),
        )
    )
    reversed_order = challenge.create_session(
        ChallengeOptions(
            duration_minutes=1,
            stages=1,
            seed=5,
            funbox=(FunboxMode.EQUATIONS, FunboxMode.LOGIC),
        )
    )
    assert ordinary.mode == "challenge"
    assert funbox.settings_fingerprint != ordinary.settings_fingerprint
    assert other_order.settings_fingerprint == reversed_order.settings_fingerprint


def test_empty_funbox_selection_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one funbox mode"):
        Challenge(_settings(tmp_path)).create_session(ChallengeOptions(funbox=()))
