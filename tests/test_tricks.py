"""Mental-math tricks: catalog contents, explicit units, limits and topic behavior."""

from __future__ import annotations

from fractions import Fraction

import pytest

from numbra.core.expressions import canonical_key, parse_expression
from numbra.core.models import Topic
from numbra.core.tricks import TRICKS, trick_catalog

IDS = [trick.id for trick in TRICKS]


def test_registry_lists_fourteen_unique_tricks() -> None:
    assert len(IDS) == 14
    assert len(set(IDS)) == 14
    assert all(trick.rule and trick.example for trick in TRICKS)


def test_every_trick_has_problems() -> None:
    present = {p.strategy for p in (*trick_catalog(2_500), *trick_catalog(10_000))}
    assert present == set(IDS)


def test_trick_problems_are_tagged_and_exact() -> None:
    for p in trick_catalog(10_000):
        assert p.family == "tricks"
        assert p.topics == (Topic.TRICKS,)
        assert p.strategy in IDS
        assert Fraction(p.answer) == p.evaluate()


@pytest.mark.parametrize(
    ("expression", "strategy", "units"),
    [
        ("43 * 11", "times-11", 1),
        ("47 * 11", "times-11", 2),
        ("437 * 11", "times-11", 4),
        ("97 * 94", "near-100", 5),
        ("96 * 97", "near-100", 4),
        ("65 * 65", "square-ending-5", 3),
        ("1000 - 376", "complement", 2),
        ("48 * 5", "times-5", 1),
        ("48 * 48", "square-near-50", 3),
        ("43 * 43", "square-near-50", 4),
        ("43 * 47", "same-decade", 3),
    ],
)
def test_trick_units_match_table(expression: str, strategy: str, units: int) -> None:
    key = canonical_key(parse_expression(expression))
    matches = [p for p in trick_catalog(10_000) if canonical_key(p.as_tree()) == key]
    assert [(p.strategy, p.work_units) for p in matches] == [(strategy, units)]


@pytest.mark.parametrize("limit", [400, 2_500, 10_000])
def test_catalog_respects_result_limit(limit: int) -> None:
    catalog = trick_catalog(limit)
    assert catalog
    assert all(abs(p.answer) <= limit for p in catalog)


def test_catalog_has_no_duplicate_problems() -> None:
    keys = [canonical_key(p.as_tree()) for p in trick_catalog(10_000)]
    assert len(keys) == len(set(keys))


def _session(*, features: dict[Topic, bool] | None = None, seed: int = 3, **options):
    from numbra.config.models import ChallengeConfig, Settings
    from numbra.core.challenge import Challenge, ChallengeOptions

    config = ChallengeConfig(features=ChallengeConfig().features | (features or {}))
    return Challenge(Settings(config, (), {})).create_session(
        ChallengeOptions(seed=seed, **options)
    )


def test_selection_parses_tricks() -> None:
    from numbra.core.models import Operation, parse_operation_selection

    assert parse_operation_selection(["+", "tricks"]) == (Operation.ADD, Topic.TRICKS)


@pytest.mark.parametrize("difficulty", ["easy", "normal", "hard"])
def test_tricks_only_selection(difficulty: str) -> None:
    from numbra.core.generator import TRICK_MAX_RESULT, WORK_BANDS, complexity_score
    from numbra.core.models import Difficulty

    level = Difficulty(difficulty)
    session = _session(difficulty=level, operations=(Topic.TRICKS,))
    problems = [p for stage in session.stages for p in stage.problems]
    low, high = WORK_BANDS[level]
    assert session.topics == (Topic.TRICKS,)
    assert problems
    for p in problems:
        assert p.topics == (Topic.TRICKS,) and p.strategy in IDS
        assert low <= complexity_score(p) - 2 <= high
        assert abs(p.answer) <= TRICK_MAX_RESULT[level]


def test_advanced_does_not_toggle_tricks() -> None:
    assert Topic.TRICKS not in _session(advanced=True).topics
    assert Topic.TRICKS in _session(advanced=False, features={Topic.TRICKS: True}).topics


def test_config_feature_enables_tricks() -> None:
    assert Topic.TRICKS in _session(features={Topic.TRICKS: True}).topics
    assert Topic.TRICKS not in _session().topics


def test_easy_tricks_variety() -> None:
    from numbra.core.models import Difficulty

    session = _session(difficulty=Difficulty.EASY, operations=(Topic.TRICKS,), duration_minutes=20)
    assert len({p.strategy for s in session.stages for p in s.problems}) >= 8


@pytest.mark.parametrize("seed", range(1, 6))
def test_tricks_do_not_skew_operation_balance(seed: int) -> None:
    from collections import Counter

    from numbra.core.models import BASIC_OPERATIONS

    session = _session(seed=seed, operations=(*BASIC_OPERATIONS, Topic.TRICKS))
    for stage in session.stages:
        counts = Counter(
            op for p in stage.problems if p.family == "arithmetic" for op in p.operations
        )
        assert max(counts.values()) - min(counts.values()) <= 2, counts


def test_tricks_seed_reproduces() -> None:
    first = _session(operations=(Topic.TRICKS,), seed=9)
    second = _session(operations=(Topic.TRICKS,), seed=9)
    assert first.stages == second.stages


@pytest.mark.parametrize("trick", TRICKS, ids=IDS)
def test_trick_examples_are_correct(trick) -> None:
    parts = [part.strip() for part in trick.example.split("=")]
    assert parse_expression(parts[0]).evaluate() == int(parts[-1])


@pytest.mark.parametrize(
    ("expression", "strategy", "units"),
    [
        ("88 * 89", "near-100", 5),
        ("88 * 95", "near-100", 5),
        ("41 * 41", "square-near-50", 4),
        ("25 * 25", "square-ending-5", 2),
        ("21 * 29", "same-decade", 3),
    ],
)
def test_specific_tricks_keep_their_problems(expression: str, strategy: str, units: int) -> None:
    test_trick_units_match_table(expression, strategy, units)


def test_advanced_keeps_tricks_from_configured_operations() -> None:
    from numbra.config.models import ChallengeConfig, Settings
    from numbra.core.challenge import Challenge, ChallengeOptions
    from numbra.core.models import Operation

    config = ChallengeConfig(operations=(Operation.ADD, Topic.TRICKS))
    for advanced in (True, False):
        session = Challenge(Settings(config, (), {})).create_session(
            ChallengeOptions(seed=1, advanced=advanced)
        )
        assert Topic.TRICKS in session.topics
