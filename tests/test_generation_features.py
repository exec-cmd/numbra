from __future__ import annotations

from collections import Counter
from fractions import Fraction

from numbra.config.models import ChallengeConfig, Settings
from numbra.core.challenge import (
    Challenge,
    ChallengeOptions,
)
from numbra.core.expressions import Expr
from numbra.core.models import Difficulty, Operation, Problem, Topic


def _settings() -> Settings:
    return Settings(ChallengeConfig(), (), {})


def _kinds(problem: Problem) -> set[str]:
    def visit(node: Expr) -> set[str]:
        return {node.kind}.union(*(visit(child) for child in node.args))

    return visit(problem.as_tree())


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
        assert Fraction(problem.answer) == problem.evaluate()
        assert Fraction(problem.answer).denominator == 1
    i, j, problem = trig[0]
    assert session.submit(i, j, str(problem.answer), 0.5).is_correct


def test_hard_division_has_constructive_multi_step_tasks() -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, difficulty=Difficulty.HARD, operations=(Operation.DIVIDE,))
    )
    assert all(p.evaluate().denominator == 1 for s in session.stages for p in s.problems)
    assert all(len(p.operations) >= 2 for s in session.stages for p in s.problems)
