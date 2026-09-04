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
