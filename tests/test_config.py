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
    assert settings.challenge.profiles["very-easy"].max_value == 10
    assert settings.challenge.profiles["very-hard"].max_value == 999
    assert settings.challenge.profiles["very-easy"].max_result == 20
    assert settings.challenge.profiles["very-hard"].max_result == 10_000
    assert settings.challenge.operation_timing.enabled is True
    assert settings.challenge.operation_timing.bonus_seconds["*"] == 1.0


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
