"""Property tests for the arithmetic constructor rules (update 005, R1-R4, R9, R10)."""

from __future__ import annotations

import itertools
import random
import re
from collections import Counter

import pytest

from numbra.config.models import ChallengeConfig
from numbra.core.expressions import Expr, canonical_key, parse_expression
from numbra.core.generator import DifficultyProfile, ProblemGenerator, canonical_problem_key
from numbra.core.models import BASIC_OPERATIONS, Difficulty, Operation, Problem
from numbra.core.permutation import permute_operands

SEEDS = (1, 2, 3, 4)
TERM_RANGES = {Difficulty.EASY: (2, 3), Difficulty.NORMAL: (2, 6), Difficulty.HARD: (3, 8)}


def _profile(difficulty: Difficulty) -> DifficultyProfile:
    c = ChallengeConfig().profiles[difficulty]
    return DifficultyProfile(c.min_value, c.max_value, c.min_terms, c.max_terms, c.max_result)


def _session(
    difficulty: Difficulty,
    seed: int,
    count: int = 40,
    operations: tuple[Operation, ...] = BASIC_OPERATIONS,
) -> tuple[Problem, ...]:
    generator = ProblemGenerator(_profile(difficulty), operations, seed, difficulty=difficulty)
    return generator.generate_many(count)


def _nodes(expr: Expr) -> list[Expr]:
    return [expr, *(node for arg in expr.args for node in _nodes(arg))]


def _terms(problem: Problem) -> int:
    return sum(node.kind == "number" for node in _nodes(problem.as_tree()))


def _bracket_shape(text: str) -> tuple[int, int]:
    """Return (max nesting depth, number of pairs) of the parentheses in `text`."""
    depth = deepest = pairs = 0
    for char in text:
        if char == "(":
            depth += 1
            pairs += 1
            deepest = max(deepest, depth)
        elif char == ")":
            depth -= 1
    return deepest, pairs


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
def test_r1_seed_reproduces_and_seeds_rarely_share_exercises(difficulty: Difficulty) -> None:
    sessions = {seed: _session(difficulty, seed, 30) for seed in SEEDS}
    assert sessions[1] == _session(difficulty, 1, 30)
    assert sessions[1] != sessions[2]
    keys = {seed: {canonical_problem_key(p) for p in ps} for seed, ps in sessions.items()}
    shared = [len(keys[a] & keys[b]) for a, b in itertools.combinations(SEEDS, 2)]
    assert sum(shared) / len(shared) <= 2.0, shared


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r2_term_counts_stay_in_range_and_short_chains_dominate(difficulty: Difficulty) -> None:
    low, high = TERM_RANGES[difficulty]
    counts = Counter(_terms(p) for seed in SEEDS for p in _session(difficulty, seed, 60))
    assert set(counts) <= set(range(low, high + 1)), counts
    assert counts[low] == max(counts.values()), counts
    assert counts[low] > counts[low + 1], counts


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r2_division_only_selection_allows_two_terms(difficulty: Difficulty) -> None:
    problems = _session(difficulty, 1, 20, (Operation.DIVIDE,))
    assert min(_terms(p) for p in problems) >= 2
    assert all(_terms(p) == 2 for p in problems)


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r3_brackets_are_shallow_and_mixed_with_flat_chains(difficulty: Difficulty) -> None:
    problems = [p for seed in SEEDS for p in _session(difficulty, seed, 60)]
    shapes = [_bracket_shape(p.expression) for p in problems]
    assert all(depth <= 1 and pairs <= 2 for depth, pairs in shapes), max(shapes)
    if difficulty is not Difficulty.EASY:
        assert any(pairs for _, pairs in shapes)
    assert any(not pairs and _terms(p) >= 3 for p, (_, pairs) in zip(problems, shapes, strict=True))


@pytest.mark.parametrize("difficulty", [Difficulty.NORMAL, Difficulty.HARD])
def test_r4_dividend_may_exceed_max_value_but_not_max_result(difficulty: Difficulty) -> None:
    profile = _profile(difficulty)
    dividends = [
        node.args[0].evaluate()
        for seed in SEEDS
        for p in _session(difficulty, seed, 60)
        for node in _nodes(p.as_tree())
        if node.kind == "/"
    ]
    assert dividends
    assert max(abs(d) for d in dividends) <= profile.max_result
    assert max(dividends) > profile.max_value, max(dividends)


def test_r9_templates_may_repeat_more_than_twice() -> None:
    templates = Counter(re.sub(r"\d+", "N", p.expression) for p in _session(Difficulty.EASY, 1, 60))
    assert max(templates.values()) > 2, templates.most_common(3)


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r10_at_most_one_division_per_exercise(difficulty: Difficulty) -> None:
    for seed in SEEDS:
        for p in _session(difficulty, seed, 60):
            assert p.expression.count("/") <= 1, p.expression


def _is_missing(problem: Problem) -> bool:
    return "?" in problem.expression


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r5_about_one_in_six_is_missing_number_with_unique_integer_answer(
    difficulty: Difficulty,
) -> None:
    problems = [p for seed in SEEDS for p in _session(difficulty, seed, 60)]
    hidden = [p for p in problems if _is_missing(p)]
    assert 0.10 <= len(hidden) / len(problems) <= 0.25, len(hidden)
    for p in hidden:
        lhs, rhs = p.expression.rsplit(" = ", 1)
        assert isinstance(p.answer, int)

        def holds(value: int, lhs: str = lhs, rhs: str = rhs) -> bool:
            try:
                return parse_expression(lhs.replace("?", f"({value})")).evaluate() == int(rhs)
            except ValueError:  # candidate 0 as a divisor
                return False

        assert [v for v in range(p.answer - 30, p.answer + 31) if holds(v)] == [p.answer], p


@pytest.mark.parametrize("difficulty", list(Difficulty))
def test_r6_permuted_exercises_keep_key_value_and_answer(difficulty: Difficulty) -> None:
    swapped = 0
    for seed in SEEDS:
        problems = _session(difficulty, seed, 60)
        keys = [canonical_problem_key(p) for p in problems]
        assert len(keys) == len(set(keys)), seed  # permutations count as one exercise
        for p in problems:
            if _is_missing(p):
                continue
            tree = parse_expression(p.expression)
            assert canonical_key(tree) == canonical_problem_key(p), p.expression
            assert tree.evaluate() == p.answer
            assert p.as_tree().render() == p.expression
            swapped += permute_operands(tree, random.Random(seed)) != tree
    assert swapped, "no commutative operand order ever varied"
