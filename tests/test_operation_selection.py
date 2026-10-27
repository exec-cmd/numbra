"""Unified operation selection through CLI and configuration."""

from dataclasses import replace
from typing import Any

import pytest
from typer.testing import CliRunner

from numbra.cli import app
from numbra.cli.app import _parse_operations
from numbra.config import ConfigManager, ConfigPaths
from numbra.config.models import ChallengeConfig, Settings
from numbra.core.challenge import Challenge, ChallengeOptions, TrainingSession
from numbra.core.models import Difficulty, Operation, Topic


def _settings(challenge: ChallengeConfig | None = None) -> Settings:
    return Settings(challenge or ChallengeConfig(), (), {})


def _session(selection: str, **kwargs: Any) -> TrainingSession:
    config = ChallengeConfig(features={topic: True for topic in Topic})
    return Challenge(Settings(config, (), {})).create_session(
        ChallengeOptions(operations=_parse_operations(selection), seed=42, **kwargs)
    )


@pytest.mark.parametrize("level", list(Difficulty))
@pytest.mark.parametrize("topic", ["sqrt", "trig", "log", "power", "^"])
def test_topic_only_selection_contains_topic_in_every_problem(level, topic):
    result = _session(topic, difficulty=level, identities=False)
    expected = Topic.POWER if topic == "^" else Topic(topic)
    problems = [p for stage in result.stages for p in stage.problems]
    assert result.operations == ()
    assert result.topics == (expected,)
    assert problems and all(expected in p.topics for p in problems)
    assert all(p.family != "arithmetic" for p in problems)
    assert result.generation_version == 4
    again = _session(topic, difficulty=level, identities=False)
    assert result.stages == again.stages


def test_selection_replaces_config_topics_but_keeps_independent_identities():
    result = _session("+,sqrt")
    assert result.operations == (Operation.ADD,)
    assert set(result.topics) == {Topic.SQRT, Topic.IDENTITIES}
    assert all(
        set(p.operations) <= {Operation.ADD, Operation.MULTIPLY}
        for s in result.stages
        for p in s.problems
        if p.family == "sqrt"
    )


def test_advanced_adds_basic_operations_and_all_topics():
    result = _session("sqrt", advanced=True, identities=False)
    assert set(result.operations) == {
        Operation.ADD,
        Operation.SUBTRACT,
        Operation.MULTIPLY,
        Operation.DIVIDE,
    }
    assert set(result.topics) == set(Topic) - {Topic.IDENTITIES}
    assert any(p.family == "arithmetic" for s in result.stages for p in s.problems)


def test_no_advanced_keeps_explicit_selection():
    result = _session("sqrt", advanced=False)
    assert result.operations == ()
    assert result.topics == (Topic.SQRT,)


def test_config_accepts_same_selection_and_preserves_file(tmp_path):
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    text = '[challenge]\noperations = ["sqrt", "log", "power"]\n'
    paths.main.write_text(text)
    settings = manager.load_or_create()
    result = Challenge(settings).create_session(ChallengeOptions(seed=1))
    assert result.operations == ()
    assert set(result.topics) == {Topic.SQRT, Topic.LOG, Topic.POWER}
    assert paths.main.read_text() == text


def test_cli_selection_overrides_config_selection():
    config = replace(ChallengeConfig(), operations=(Operation.POWER,))
    result = Challenge(Settings(config, (), {})).create_session(
        ChallengeOptions(operations=_parse_operations("+"), seed=1)
    )
    assert result.operations == (Operation.ADD,)
    assert result.topics == ()


@pytest.mark.parametrize(
    "flag",
    ["--sqrt", "--trig", "--log", "--power", "--no-sqrt", "--no-trig", "--no-log", "--no-power"],
)
def test_removed_cli_flags_are_rejected(flag):
    assert CliRunner().invoke(app, ["challenge", flag]).exit_code == 2


def test_identities_is_not_an_operation():
    with pytest.raises(ValueError, match="unsupported operation"):
        _parse_operations("identities")


def test_topic_only_training_persists_selection_and_generator_version(tmp_path):
    from numbra.core.stats import Stats

    training = _session("trig", identities=False)
    for i, stage in enumerate(training.stages):
        for j, problem in enumerate(stage.problems):
            assert training.submit(i, j, str(problem.answer), 0.1).is_correct
    completed = training.complete(actual_duration=1)
    stats = Stats(tmp_path / "results.sqlite3")
    stats.save(completed)
    record = stats.history(1)[0]
    assert record.operations == ()
    assert record.topics == ("trig",)
    assert record.generation_version == 4
    assert stats.comparable_history(completed)
    assert not stats.comparable_history(replace(completed, generation_version=2))


def test_power_alias_and_duplicate_selection_have_same_seed_sequence():
    canonical = _session("+,power", identities=False)
    alias = _session(" +, ^, +, power ", identities=False)
    assert canonical.operations == alias.operations
    assert canonical.topics == alias.topics
    assert canonical.stages == alias.stages
    assert canonical.settings_fingerprint == alias.settings_fingerprint


def test_cli_feature_flags_override_config_and_advanced_defaults() -> None:
    base = ChallengeConfig()
    features = base.features | {Topic.LOG: True}
    challenge_config = ChallengeConfig(features=features)

    session = Challenge(_settings(challenge_config)).create_session(
        ChallengeOptions(seed=42, advanced=True, sqrt=False)
    )

    assert set(session.topics) == set(Topic) - {Topic.SQRT}


def test_advanced_flags_can_disable_trig_and_power() -> None:
    session = Challenge(_settings()).create_session(
        ChallengeOptions(seed=42, advanced=True, trig=False, power=False)
    )
    assert Topic.TRIG not in session.topics
    assert Topic.POWER not in session.topics
    assert all("^" not in p.expression for s in session.stages for p in s.problems)
    with pytest.raises(ValueError, match="power"):
        Challenge(_settings()).create_session(
            ChallengeOptions(operations=(Operation.POWER,), power=False)
        )


def test_general_cli_disable_overrides_legacy_power_in_config() -> None:
    from dataclasses import replace

    cfg = replace(ChallengeConfig(), operations=(Operation.POWER,))
    session = Challenge(Settings(cfg, (), {})).create_session(
        ChallengeOptions(seed=42, advanced=False)
    )
    assert Topic.POWER not in session.topics
    assert all("^" not in p.expression for stage in session.stages for p in stage.problems)
