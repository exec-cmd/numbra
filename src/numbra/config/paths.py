from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_config_path, user_data_path


@dataclass(frozen=True, slots=True)
class ConfigPaths:
    root: Path
    main: Path
    templates: Path
    design: Path

    @classmethod
    def from_root(cls, root: Path) -> ConfigPaths:
        return cls(root, root / "numbra.toml", root / "temps.json", root / "design.toml")


def default_config_paths() -> ConfigPaths:
    # roaming=True keeps Windows on %APPDATA%; appauthor=False avoids a doubled folder there.
    return ConfigPaths.from_root(user_config_path("numbra", appauthor=False, roaming=True))


def default_data_dir() -> Path:
    return user_data_path("numbra", appauthor=False)


def default_database_path() -> Path:
    return default_data_dir() / "numbra.sqlite3"


def default_log_path() -> Path:
    return default_data_dir() / "numbra.log"
