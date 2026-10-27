from pathlib import Path

import pytest

from numbra.config import ConfigError, ConfigManager, ConfigPaths


def test_config_manager_creates_defaults(tmp_path: Path) -> None:
    manager = ConfigManager(ConfigPaths.from_root(tmp_path))
    settings = manager.load_or_create()
    assert settings.challenge.duration_minutes == 6
    assert all(path.exists() for path in manager.paths.all_files())


def test_unknown_toml_field_mentions_file_and_field(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text("[challenge]\nunknown = 1\n", encoding="utf-8")
    with pytest.raises(ConfigError, match=r"numbra\.toml.*challenge\.unknown"):
        manager.load_or_create()


def test_invalid_json_is_user_facing_error(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.templates.write_text("{", encoding="utf-8")
    with pytest.raises(ConfigError, match="temps.json"):
        manager.load_or_create()


def test_new_difficulty_profiles_and_operation_timing_are_loaded(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.difficulty.value == "normal"
    assert settings.challenge.profiles["easy"].max_value == 20
    assert settings.challenge.profiles["very-hard"].max_value == 999
    assert settings.challenge.profiles["easy"].max_result == 400
    assert settings.challenge.profiles["very-hard"].max_result == 10_000
    assert settings.challenge.operation_timing.enabled is True
    assert settings.challenge.operation_timing.bonus_seconds["*"] == 1.0
    assert settings.challenge.features == {topic: False for topic in settings.challenge.features}
    assert settings.warnings == ()


def test_legacy_difficulty_maps_to_easy_and_warns_without_rewriting(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    text = paths.main.read_text(encoding="utf-8")
    paths.main.write_text(
        text.replace('difficulty = "normal"', 'difficulty = "very-easy"'), encoding="utf-8"
    )

    settings = manager.load_or_create()

    assert settings.challenge.difficulty.value == "easy"
    assert any("very-easy" in warning and "easy" in warning for warning in settings.warnings)
    assert 'difficulty = "very-easy"' in paths.main.read_text(encoding="utf-8")


def test_legacy_very_easy_profile_is_ignored_and_warned(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    with paths.main.open("a", encoding="utf-8") as file:
        file.write("\n[difficulties.very-easy]\nmax_value = 5\n")
    original = paths.main.read_text(encoding="utf-8")

    settings = manager.load_or_create()

    assert "very-easy" not in {level.value for level in settings.challenge.profiles}
    assert any("very-easy" in warning for warning in settings.warnings)
    assert paths.main.read_text(encoding="utf-8") == original


def test_feature_flags_load_and_validate_with_filename_and_field(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("sqrt = false", "sqrt = true"),
        encoding="utf-8",
    )

    settings = manager.load_or_create()

    assert {topic.value for topic, enabled in settings.challenge.features.items() if enabled} == {
        "sqrt",
    }
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace(
            "identities = false", "identities = false\nunknown = true"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match=r"numbra\.toml.*features\.unknown"):
        manager.load_or_create()


def test_feature_flag_must_be_boolean(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    manager = ConfigManager(paths)
    manager.load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("sqrt = false", "sqrt = 1"),
        encoding="utf-8",
    )

    with pytest.raises(ConfigError, match=r"numbra\.toml.*features\.sqrt.*boolean"):
        manager.load_or_create()


def test_operation_timing_can_be_disabled(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    ConfigManager(paths).load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace("enabled = true", "enabled = false"),
        encoding="utf-8",
    )
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.operation_timing.enabled is False


def test_operation_timing_disable_can_omit_bonus_table(tmp_path: Path) -> None:
    paths = ConfigPaths.from_root(tmp_path)
    ConfigManager(paths).load_or_create()
    paths.main.write_text(
        paths.main.read_text(encoding="utf-8").replace(
            '[timing]\noperation_bonus_enabled = true\n[timing.operation_bonus_seconds]\n"+" = 0\n"-" = 0\n"*" = 1\n"/" = 2\n',
            "[timing]\noperation_bonus_enabled = false\n",
        ),
        encoding="utf-8",
    )
    settings = ConfigManager(paths).load_or_create()
    assert settings.challenge.operation_timing.enabled is False
