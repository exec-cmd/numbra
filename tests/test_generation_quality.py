"""Generator quality properties: band coverage, operand variety, no trivial steps."""

from __future__ import annotations

from collections import Counter

import pytest

from numbra.config.models import ChallengeConfig
from numbra.core.expressions import Expr
from numbra.core.generator import WORK_BANDS, DifficultyProfile, ProblemGenerator, complexity_score
from numbra.core.models import BASIC_OPERATIONS, Difficulty


def _generator(difficulty: Difficulty, seed: int) -> ProblemGenerator:
    config = ChallengeConfig().profiles[difficulty]
    profile = DifficultyProfile(
        config.min_value, config.max_value, config.min_terms, config.max_terms, config.max_result
    )
    return ProblemGenerator(profile, BASIC_OPERATIONS, seed, difficulty=difficulty)


def _nodes(expr: Expr) -> list[Expr]:
    return [expr, *(node for arg in expr.args for node in _nodes(arg))]


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
@pytest.mark.parametrize("seed", range(1, 6))
def test_stage_covers_every_band_level(difficulty: Difficulty, seed: int) -> None:
    generator = _generator(difficulty, seed)
    generator.start_stage()
    levels = {complexity_score(p) - 2 for p in generator.generate_many(12)}
    low, high = WORK_BANDS[difficulty]
    assert levels == set(range(low, high + 1))


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
@pytest.mark.parametrize("seed", range(1, 21))
def test_operands_do_not_repeat_excessively(difficulty: Difficulty, seed: int) -> None:
    problems = _generator(difficulty, seed).generate_many(30)
    counts = Counter(
        node.value
        for p in problems
        for node in _nodes(p.as_tree())
        if node.kind == "number" and node.value > 12
    )
    assert max(counts.values(), default=0) <= 3, counts.most_common(3)


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
def test_no_small_quotients(difficulty: Difficulty) -> None:
    problems = _generator(difficulty, 3).generate_many(300)
    for p in problems:
        for node in _nodes(p.as_tree()):
            if node.kind == "/":
                assert abs(node.evaluate()) >= 3, p.expression


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
def test_seed_reproduces_sequence(difficulty: Difficulty) -> None:
    first = [p.expression for p in _generator(difficulty, 11).generate_many(40)]
    second = [p.expression for p in _generator(difficulty, 11).generate_many(40)]
    assert first == second
