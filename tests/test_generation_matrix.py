"""Deterministic acceptance matrix, including an independent arithmetic evaluator."""

from fractions import Fraction
from math import isqrt

import pytest

from numbra.config.models import ChallengeConfig, Settings
from numbra.core.challenge import Challenge, ChallengeOptions
from numbra.core.expressions import Expr, parse_expression
from numbra.core.generator import (
    TRICK_MAX_RESULT,
    WORK_BANDS,
    canonical_problem_key,
    complexity_score,
)
from numbra.core.models import Difficulty, Topic


def independent(expr: Expr) -> Fraction:
    if expr.kind == "number":
        return Fraction(expr.value)
    args = [independent(child) for child in expr.args]
    if expr.kind == "+":
        return args[0] + args[1]
    if expr.kind == "-":
        return args[0] - args[1]
    if expr.kind == "*":
        return args[0] * args[1]
    if expr.kind == "/":
        return args[0] / args[1]
    if expr.kind == "^":
        return args[0] ** int(args[1])
    if expr.kind == "sqrt":
        return Fraction(isqrt(args[0].numerator), isqrt(args[0].denominator))
    if expr.kind == "log":
        for exponent in range(-3, 5):
            if args[0] ** exponent == args[1]:
                return Fraction(exponent)
        raise AssertionError("non-exact logarithm")
    # First-quadrant rational facts and exact quadrant symmetries.
    angle = int(args[0]) % 360
    if expr.kind == "tan":
        return Fraction({0: 0, 45: 1, 135: -1, 180: 0, 225: 1, 315: -1}[angle])
    if expr.kind == "cos":
        angle = (angle + 90) % 360
    return {
        0: Fraction(0),
        30: Fraction(1, 2),
        90: Fraction(1),
        150: Fraction(1, 2),
        180: Fraction(0),
        210: Fraction(-1, 2),
        270: Fraction(-1),
        330: Fraction(-1, 2),
    }[angle]


@pytest.mark.parametrize("level", list(Difficulty))
@pytest.mark.parametrize("feature", [None, *list(Topic), "advanced"])
def test_one_hundred_seeds_per_difficulty_and_topic(
    level: Difficulty, feature: Topic | str | None
) -> None:
    settings = Settings(ChallengeConfig(), (), {})
    first = None
    for seed in range(100):
        flags = (
            {}
            if feature is None
            else {"advanced": True}
            if feature == "advanced"
            else {"identities": True}
            if feature is Topic.IDENTITIES
            else {"operations": (Topic(feature),)}
        )
        session = Challenge(settings).create_session(
            ChallengeOptions(difficulty=level, seed=seed, **flags)
        )
        problems = [p for stage in session.stages for p in stage.problems]
        expected_topics = (
            set(Topic) - {Topic.TRICKS}
            if feature == "advanced"
            else set()
            if feature is None
            else {Topic(feature)}
        )
        assert set(session.topics) == expected_topics
        assert {topic for p in problems for topic in p.topics} == expected_topics
        assert (
            sum(
                session.time_limit_for(i, j)
                for i, s in enumerate(session.stages)
                for j in range(len(s.problems))
            )
            <= session.target_seconds
        )
        keys = [canonical_problem_key(p) for p in problems]
        assert len(set(keys)) == len(keys) or session.warnings
        for p in problems:
            assert Fraction(p.answer) == independent(p.as_tree())
            assert Fraction(p.answer) == independent(parse_expression(p.expression))
            assert WORK_BANDS[level][0] <= complexity_score(p) - 2 <= WORK_BANDS[level][1]
            limit = (
                TRICK_MAX_RESULT[level]
                if p.family == "tricks"
                else settings.challenge.profiles[level].max_result
            )
            assert abs(p.answer) <= limit
            assert Fraction(p.answer).denominator <= 12
            if p.family == "arithmetic":
                assert set(p.operations) <= set(session.operations)
        if seed == 0:
            first = tuple(p.expression for p in problems)
    again = Challenge(settings).create_session(ChallengeOptions(difficulty=level, seed=0, **flags))
    assert tuple(p.expression for s in again.stages for p in s.problems) == first
