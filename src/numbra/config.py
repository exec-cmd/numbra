from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .core.models import Difficulty, Operation, StageKind


class ConfigError(ValueError):
    """A user-facing configuration error."""


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


@dataclass(frozen=True, slots=True)
class DifficultyConfig:
    min_value: int
    max_value: int
    min_terms: int
    max_terms: int


def _default_stage_limits() -> dict[StageKind, float]:
    return {StageKind.FAST: 5.0, StageKind.NORMAL: 10.0, StageKind.SLOW: 15.0}


def _default_profiles() -> dict[Difficulty, DifficultyConfig]:
    return {
        Difficulty.EASY: DifficultyConfig(1, 20, 2, 2),
        Difficulty.NORMAL: DifficultyConfig(2, 99, 2, 3),
        Difficulty.HARD: DifficultyConfig(10, 999, 3, 4),
    }


@dataclass(frozen=True, slots=True)
class ChallengeConfig:
    duration_minutes: int = 6
    difficulty: Difficulty = Difficulty.NORMAL
    stages: int = 3
    seed: int | None = None
    operations: tuple[Operation, ...] = tuple(Operation)
    stage_limits: dict[StageKind, float] = field(default_factory=_default_stage_limits)
    profiles: dict[Difficulty, DifficultyConfig] = field(default_factory=_default_profiles)


@dataclass(frozen=True, slots=True)
class Settings:
    challenge: ChallengeConfig
    templates: tuple[str, ...]
    styles: dict[str, str]


def default_config_paths() -> ConfigPaths:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", str(Path.home() / "AppData/Roaming"))) / "numbra"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/numbra"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "numbra"
    return ConfigPaths.from_root(base)


def default_database_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData/Local"))) / "numbra"
    elif sys.platform == "darwin":
        base = Path.home() / "Library/Application Support/numbra"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "numbra"
    return base / "numbra.sqlite3"


class ConfigManager:
    def __init__(self, paths: ConfigPaths | None = None) -> None:
        self.paths = paths or default_config_paths()

    def load_or_create(self) -> Settings:
        self.paths.root.mkdir(parents=True, exist_ok=True)
        for path, content in (
            (self.paths.main, _DEFAULT_TOML),
            (self.paths.templates, _DEFAULT_TEMPLATES),
            (self.paths.design, _DEFAULT_DESIGN),
        ):
            if not path.exists():
                path.write_text(content, encoding="utf-8")
        try:
            with self.paths.main.open("rb") as file:
                main = tomllib.load(file)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"{self.paths.main.name}: invalid TOML: {exc}") from exc
        try:
            templates = json.loads(self.paths.templates.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ConfigError(f"{self.paths.templates.name}: invalid JSON: {exc}") from exc
        try:
            with self.paths.design.open("rb") as file:
                design = tomllib.load(file)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ConfigError(f"{self.paths.design.name}: invalid TOML: {exc}") from exc
        return _parse_settings(main, templates, design, self.paths)


def _parse_settings(
    main: dict[str, Any], templates: Any, design: dict[str, Any], paths: ConfigPaths
) -> Settings:
    challenge = main.get("challenge")
    if not isinstance(challenge, dict):
        raise ConfigError(f"{paths.main.name}: missing field challenge")
    root_unknown = set(main) - {"challenge", "stages", "difficulties"}
    if root_unknown:
        raise ConfigError(f"{paths.main.name}: unknown field {sorted(root_unknown)[0]}")
    allowed = {"duration_minutes", "difficulty", "stages", "seed", "operations"}
    unknown = set(challenge) - allowed
    if unknown:
        raise ConfigError(f"{paths.main.name}: unknown field challenge.{sorted(unknown)[0]}")
    try:
        duration = int(challenge.get("duration_minutes", 6))
        stages = int(challenge.get("stages", 3))
        difficulty = Difficulty(challenge.get("difficulty", Difficulty.NORMAL))
        seed_value = challenge.get("seed")
        seed = None if seed_value is None else int(seed_value)
        operation_values = challenge.get("operations", [item.value for item in Operation])
        operations = tuple(Operation(value) for value in operation_values)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid challenge field: {exc}") from exc
    if duration < 1:
        raise ConfigError(f"{paths.main.name}: challenge.duration_minutes must be at least 1")
    if stages < 1:
        raise ConfigError(f"{paths.main.name}: challenge.stages must be at least 1")
    if not operations:
        raise ConfigError(f"{paths.main.name}: challenge.operations must not be empty")
    stage_values = main.get("stages", {})
    limits: dict[StageKind, float] = {}
    if stage_values:
        if not isinstance(stage_values, dict) or set(stage_values) - {
            kind.value for kind in StageKind
        }:
            raise ConfigError(f"{paths.main.name}: unknown field stages")
        try:
            for kind in StageKind:
                raw = stage_values.get(kind.value, {})
                if set(raw) - {"limit_seconds"}:
                    raise ValueError(f"unknown field stages.{kind.value}")
                limits[kind] = float(raw["limit_seconds"])
                if limits[kind] <= 0:
                    raise ValueError("limit_seconds must be positive")
        except (KeyError, TypeError, ValueError) as exc:
            raise ConfigError(f"{paths.main.name}: invalid stages field: {exc}") from exc
    else:
        limits = {StageKind.FAST: 5.0, StageKind.NORMAL: 10.0, StageKind.SLOW: 15.0}
    profiles: dict[Difficulty, DifficultyConfig] = {}
    difficulty_values = main.get("difficulties", {})
    if not isinstance(difficulty_values, dict):
        raise ConfigError(f"{paths.main.name}: difficulties must be a table")
    try:
        for level in Difficulty:
            raw = difficulty_values.get(level.value, {})
            if set(raw) - {"min_value", "max_value", "min_terms", "max_terms"}:
                raise ValueError(f"unknown field difficulties.{level.value}")
            profiles[level] = DifficultyConfig(
                int(
                    raw.get(
                        "min_value",
                        {Difficulty.EASY: 1, Difficulty.NORMAL: 2, Difficulty.HARD: 10}[level],
                    )
                ),
                int(
                    raw.get(
                        "max_value",
                        {Difficulty.EASY: 20, Difficulty.NORMAL: 99, Difficulty.HARD: 999}[level],
                    )
                ),
                int(
                    raw.get(
                        "min_terms",
                        {Difficulty.EASY: 2, Difficulty.NORMAL: 2, Difficulty.HARD: 3}[level],
                    )
                ),
                int(
                    raw.get(
                        "max_terms",
                        {Difficulty.EASY: 2, Difficulty.NORMAL: 3, Difficulty.HARD: 4}[level],
                    )
                ),
            )
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid difficulties field: {exc}") from exc
    if not isinstance(templates, list) or not all(isinstance(item, str) for item in templates):
        raise ConfigError(f"{paths.templates.name}: expected an array of strings")
    unknown_design = set(design) - {"styles"}
    if unknown_design:
        raise ConfigError(f"{paths.design.name}: unknown field {sorted(unknown_design)[0]}")
    style_values = design.get("styles", {})
    if not isinstance(style_values, dict) or not all(
        isinstance(value, str) for value in style_values.values()
    ):
        raise ConfigError(f"{paths.design.name}: styles must be a table of strings")
    if not templates:
        raise ConfigError(f"{paths.templates.name}: template list must not be empty")
    return Settings(
        ChallengeConfig(duration, difficulty, stages, seed, operations, limits, profiles),
        tuple(templates),
        style_values,
    )


_DEFAULT_TOML = '[challenge]\nduration_minutes = 6\ndifficulty = "normal"\nstages = 3\noperations = ["+", "-", "*", "/"]\n\n[stages.fast]\nlimit_seconds = 5\n[stages.normal]\nlimit_seconds = 10\n[stages.slow]\nlimit_seconds = 15\n\n[difficulties.easy]\nmin_value = 1\nmax_value = 20\nmin_terms = 2\nmax_terms = 2\n[difficulties.normal]\nmin_value = 2\nmax_value = 99\nmin_terms = 2\nmax_terms = 3\n[difficulties.hard]\nmin_value = 10\nmax_value = 999\nmin_terms = 3\nmax_terms = 4\n'
_DEFAULT_TEMPLATES = '["{left} {operation} {right}"]\n'
_DEFAULT_DESIGN = (
    '[styles]\naccent = "bold cyan"\nsuccess = "green"\nerror = "bold red"\ntimer = "yellow"\n'
)
