from pathlib import Path

import pytest

from numbra.config import (
    ConfigError,
    ConfigManager,
    ConfigPaths,
    get_value,
    list_values,
    set_value,
    unset_value,
)
from numbra.core.models import Operation, Topic


@pytest.fixture
def paths(tmp_path: Path) -> ConfigPaths:
    return ConfigPaths.from_root(tmp_path / "numbra")


def test_missing_config_is_created_with_defaults(paths: ConfigPaths) -> None:
    assert get_value(paths, "challenge.difficulty") == "normal"
    assert paths.main.exists()


def test_list_contains_flattened_defaults(paths: ConfigPaths) -> None:
    values = dict(list_values(paths))
    assert values["challenge.difficulty"] == "normal"
    assert values["challenge.operations"] == ["+", "-", "*", "/"]
    assert values["features.trig"] is False
    assert values["timing.operation_bonus_seconds.*"] == 1
    assert values["stages.fast.limit_seconds"] == 5
    assert values["difficulties.hard.max_value"] == 999
    assert values["generation.brackets"] is True
    assert "challenge.seed" not in values


def test_set_then_get_round_trips_through_the_file(paths: ConfigPaths) -> None:
    set_value(paths, "challenge.difficulty", "hard")
    set_value(paths, "features.trig", "true")
    set_value(paths, "stages.fast.limit_seconds", "7.5")

    assert get_value(paths, "challenge.difficulty") == "hard"
    assert get_value(paths, "features.trig") is True
    assert get_value(paths, "stages.fast.limit_seconds") == 7.5
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.difficulty.value == "hard"
    assert settings.challenge.features[Topic.TRIG] is True


def test_list_values_are_parsed_from_toml(paths: ConfigPaths) -> None:
    set_value(paths, "challenge.operations", '["+","*"]')

    assert get_value(paths, "challenge.operations") == ["+", "*"]
    assert ConfigManager(paths).load_or_create().challenge.operations == (
        Operation.ADD,
        Operation.MULTIPLY,
    )


def test_unset_restores_the_default(paths: ConfigPaths) -> None:
    set_value(paths, "challenge.difficulty", "hard")
    unset_value(paths, "challenge.difficulty")

    assert get_value(paths, "challenge.difficulty") == "normal"
    assert 'difficulty = "hard"' not in paths.main.read_text(encoding="utf-8")


def test_write_keeps_the_file_as_the_only_artifact(paths: ConfigPaths) -> None:
    set_value(paths, "challenge.difficulty", "hard")

    assert sorted(item.name for item in paths.root.iterdir()) == [
        "design.toml",
        "numbra.toml",
        "temps.json",
    ]


def test_write_does_not_follow_predictable_temp_symlink(paths: ConfigPaths) -> None:
    ConfigManager(paths).load_or_create()
    target = paths.root / "target"
    target.write_text("preserve this", encoding="utf-8")
    predictable_temp = paths.main.with_name(f"{paths.main.name}.tmp")
    try:
        predictable_temp.symlink_to(target)
    except (NotImplementedError, OSError) as exc:
        pytest.skip(f"symlinks are unavailable: {exc}")

    set_value(paths, "challenge.difficulty", "hard")

    assert target.read_text(encoding="utf-8") == "preserve this"
    assert get_value(paths, "challenge.difficulty") == "hard"


def test_invalid_value_leaves_file_unchanged_and_names_key_and_file(paths: ConfigPaths) -> None:
    ConfigManager(paths).load_or_create()
    before = paths.main.read_text(encoding="utf-8")

    with pytest.raises(ConfigError, match=r"numbra\.toml.*challenge\.difficulty"):
        set_value(paths, "challenge.difficulty", "bogus")
    with pytest.raises(ConfigError, match=r"numbra\.toml.*challenge\.duration_minutes"):
        set_value(paths, "challenge.duration_minutes", "0")

    assert paths.main.read_text(encoding="utf-8") == before


def test_unknown_key_is_rejected_for_every_operation(paths: ConfigPaths) -> None:
    with pytest.raises(ConfigError, match="challenge.nope"):
        get_value(paths, "challenge.nope")
    with pytest.raises(ConfigError, match="challenge.nope"):
        set_value(paths, "challenge.nope", "1")
    with pytest.raises(ConfigError, match="challenge.nope"):
        unset_value(paths, "challenge.nope")


def test_legacy_difficulty_tables_are_not_editable(paths: ConfigPaths) -> None:
    with pytest.raises(ConfigError, match="difficulties.very-easy.max_value"):
        set_value(paths, "difficulties.very-easy.max_value", "5")


def test_seed_set_and_unset(paths: ConfigPaths) -> None:
    assert get_value(paths, "challenge.seed") is None

    set_value(paths, "challenge.seed", "42")
    assert get_value(paths, "challenge.seed") == 42
    assert ("challenge.seed", 42) in list_values(paths)
    assert "seed = 42" in paths.main.read_text(encoding="utf-8")

    unset_value(paths, "challenge.seed")
    assert get_value(paths, "challenge.seed") is None
    assert "seed" not in paths.main.read_text(encoding="utf-8")
    assert ConfigManager(paths).load_or_create().challenge.seed is None


def test_plain_words_are_stored_as_strings(paths: ConfigPaths) -> None:
    set_value(paths, "challenge.difficulty", "hard")
    assert 'difficulty = "hard"' in paths.main.read_text(encoding="utf-8")


def test_unset_missing_key_is_a_no_op(paths: ConfigPaths) -> None:
    ConfigManager(paths).load_or_create()
    before = paths.main.read_text(encoding="utf-8")

    unset_value(paths, "challenge.seed")

    assert paths.main.read_text(encoding="utf-8") == before


def test_funbox_modes_are_listed_and_validated_on_write(paths: ConfigPaths) -> None:
    assert dict(list_values(paths))["funbox.modes"] == []
    set_value(paths, "funbox.modes", '["logic"]')
    assert get_value(paths, "funbox.modes") == ["logic"]
    with pytest.raises(ConfigError, match=r"funbox\.modes"):
        set_value(paths, "funbox.modes", '["nope"]')
    assert get_value(paths, "funbox.modes") == ["logic"]


def test_generation_brackets_round_trip(paths: ConfigPaths) -> None:
    assert get_value(paths, "generation.brackets") is True

    set_value(paths, "generation.brackets", "false")

    assert get_value(paths, "generation.brackets") is False
    assert ConfigManager(paths).load_or_create().challenge.brackets is False
    assert "brackets = false" in paths.main.read_text(encoding="utf-8")
