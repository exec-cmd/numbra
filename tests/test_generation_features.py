from __future__ import annotations

from collections import Counter
from fractions import Fraction

import pytest

from numbra.config.models import ChallengeConfig, Settings
from numbra.core.challenge import (
    Challenge,
    ChallengeOptions,
)
from numbra.core.expressions import Expr, parse_expression
from numbra.core.models import Difficulty, Operation, Problem, Topic


def _settings() -> Settings:
    return Settings(ChallengeConfig(), (), {})


def _leaves(expr: Expr) -> set[int]:
    return (
        {expr.value} if expr.kind == "number" else set().union(*(_leaves(arg) for arg in expr.args))
    )


def _kinds(problem: Problem) -> set[str]:
    def visit(node: Expr) -> set[str]:
        return {node.kind}.union(*(visit(child) for child in node.args))

    return visit(problem.as_tree())


def _count_kind(node: Expr, kind: str) -> int:
    return (node.kind == kind) + sum(_count_kind(child, kind) for child in node.args)


def test_enabled_function_topics_produce_their_functions() -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, difficulty=Difficulty.NORMAL, advanced=True)
    )
    problems = [problem for stage in session.stages for problem in stage.problems]

    assert any(Topic.SQRT in problem.topics and "sqrt" in _kinds(problem) for problem in problems)
    assert any(
        Topic.TRIG in problem.topics and _kinds(problem) & {"sin", "cos", "tan"}
        for problem in problems
    )
    assert any(Topic.LOG in problem.topics and "log" in _kinds(problem) for problem in problems)
    assert any(Topic.POWER in problem.topics and "^" in _kinds(problem) for problem in problems)


def test_stage_balance_is_not_global_difficulty_sorting() -> None:
    session = Challenge(_settings()).create_session(ChallengeOptions(seed=42))
    for stage in session.stages:
        counts = Counter(op for p in stage.problems for op in p.operations)
        assert set(counts) == set(session.operations)
        assert max(counts.values()) - min(counts.values()) <= 2


def test_trig_answers_are_integers_and_accepted() -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, difficulty=Difficulty.EASY, trig=True)
    )
    trig = [
        (i, j, problem)
        for i, stage in enumerate(session.stages)
        for j, problem in enumerate(stage.problems)
        if Topic.TRIG in problem.topics
    ]
    assert trig
    for _, _, problem in trig:
        if "?" in problem.expression:
            lhs, rhs = problem.expression.rsplit(" = ", 1)
            assert (
                Fraction(rhs) == parse_expression(lhs.replace("?", str(problem.answer))).evaluate()
            )
            assert problem.answer in _leaves(problem.as_tree())
        else:
            assert Fraction(problem.answer) == problem.evaluate()
        assert Fraction(problem.answer).denominator == 1
    i, j, problem = trig[0]
    assert session.submit(i, j, str(problem.answer), 0.5).is_correct


@pytest.mark.parametrize(
    ("operation", "difficulty"),
    ((Operation.MULTIPLY, Difficulty.HARD), (Operation.DIVIDE, Difficulty.EASY)),
)
def test_single_operation_sessions_generate_bounded_integer_answers(
    operation: Operation, difficulty: Difficulty
) -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, difficulty=difficulty, operations=(operation,))
    )
    problems = [problem for stage in session.stages for problem in stage.problems]
    maximum = _settings().challenge.profiles[difficulty].max_result

    assert problems
    assert all(Fraction(problem.answer).denominator == 1 for problem in problems)
    assert all(abs(problem.answer) <= maximum for problem in problems)
    if operation is Operation.DIVIDE:
        assert any("repeated arithmetic exercises" in warning for warning in session.warnings)


def test_hard_division_only_generates_integer_answers_with_at_most_one_division() -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, difficulty=Difficulty.HARD, operations=(Operation.DIVIDE,))
    )
    problems = [problem for stage in session.stages for problem in stage.problems]

    assert problems
    assert all(Fraction(problem.answer).denominator == 1 for problem in problems)
    assert all(_count_kind(problem.as_tree(), "/") <= 1 for problem in problems)
