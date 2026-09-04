from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ConfigPaths:
    root: Path
    main: Path
    templates: Path
    design: Path

    @classmethod
    def from_root(cls, root: Path) -> ConfigPaths:
        return cls(root, root / "numbra.toml", root / "temps.json", root / "design.toml")

    def all_files(self) -> tuple[Path, ...]:
        return self.main, self.templates, self.design


def default_config_paths() -> ConfigPaths:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "numbra"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/numbra"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "numbra"
    return ConfigPaths.from_root(base)


def default_data_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "numbra"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/numbra"
    return Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "numbra"


def default_database_path() -> Path:
    return default_data_dir() / "numbra.sqlite3"


def default_log_path() -> Path:
    return default_data_dir() / "numbra.log"
