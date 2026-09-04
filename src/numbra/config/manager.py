from __future__ import annotations

import json
import math
import tomllib
from typing import Any

from ..core.models import Difficulty, Operation, StageKind
from .defaults import _DEFAULT_DESIGN, _DEFAULT_TEMPLATES, _DEFAULT_TOML
from .models import ChallengeConfig, DifficultyConfig, OperationTimingConfig, Settings
from .paths import ConfigPaths, default_config_paths


class ConfigError(ValueError):
    """A user-facing configuration error."""


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
    unknown_challenge = set(challenge) - {
        "duration_minutes",
        "difficulty",
        "stages",
        "seed",
        "operations",
    }
    if unknown_challenge:
        raise ConfigError(
            f"{paths.main.name}: unknown field challenge.{sorted(unknown_challenge)[0]}"
        )
    unknown_root = set(main) - {"challenge", "timing", "stages", "difficulties"}
    if unknown_root:
        raise ConfigError(f"{paths.main.name}: unknown field {sorted(unknown_root)[0]}")
    try:
        duration = int(challenge.get("duration_minutes", 6))
        stages = int(challenge.get("stages", 3))
        difficulty = Difficulty(challenge.get("difficulty", Difficulty.NORMAL))
        seed_value = challenge.get("seed")
        seed = None if seed_value is None else int(seed_value)
        operation_values = challenge.get(
            "operations", [item.value for item in Operation if item is not Operation.POWER]
        )
        operations = tuple(Operation(value) for value in operation_values)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid challenge field: {exc}") from exc
    if duration < 1:
        raise ConfigError(f"{paths.main.name}: challenge.duration_minutes must be at least 1")
    if stages < 1:
        raise ConfigError(f"{paths.main.name}: challenge.stages must be at least 1")
    if not operations:
        raise ConfigError(f"{paths.main.name}: challenge.operations must not be empty")

    limits = _parse_stage_limits(main.get("stages", {}), paths)
    profiles = _parse_profiles(main.get("difficulties", {}), paths)
    timing = _parse_timing(main.get("timing", {}), paths)
    if not isinstance(templates, list) or not all(isinstance(item, str) for item in templates):
        raise ConfigError(f"{paths.templates.name}: expected an array of strings")
    if not templates:
        raise ConfigError(f"{paths.templates.name}: template list must not be empty")
    if set(design) - {"styles"}:
        raise ConfigError(
            f"{paths.design.name}: unknown field {sorted(set(design) - {'styles'})[0]}"
        )
    style_values = design.get("styles", {})
    if not isinstance(style_values, dict) or not all(
        isinstance(value, str) for value in style_values.values()
    ):
        raise ConfigError(f"{paths.design.name}: styles must be a table of strings")
    return Settings(
        ChallengeConfig(duration, difficulty, stages, seed, operations, limits, profiles, timing),
        tuple(templates),
        style_values,
    )


def _parse_stage_limits(value: Any, paths: ConfigPaths) -> dict[StageKind, float]:
    if not value:
        return {kind: default for kind, default in zip(StageKind, (5.0, 10.0, 15.0), strict=True)}
    if not isinstance(value, dict) or set(value) - {kind.value for kind in StageKind}:
        raise ConfigError(f"{paths.main.name}: unknown field stages")
    limits: dict[StageKind, float] = {}
    try:
        for kind in StageKind:
            raw = value.get(kind.value, {})
            if not isinstance(raw, dict) or set(raw) - {"limit_seconds"}:
                raise ValueError(f"unknown field stages.{kind.value}")
            limit = float(
                raw.get(
                    "limit_seconds",
                    {StageKind.FAST: 5, StageKind.NORMAL: 10, StageKind.SLOW: 15}[kind],
                )
            )
            if not math.isfinite(limit) or limit <= 0:
                raise ValueError(f"stages.{kind.value}.limit_seconds must be positive")
            limits[kind] = limit
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid stages field: {exc}") from exc
    return limits


def _parse_profiles(value: Any, paths: ConfigPaths) -> dict[Difficulty, DifficultyConfig]:
    defaults = {
        Difficulty.VERY_EASY: (1, 10, 2, 2, 20),
        Difficulty.EASY: (1, 20, 2, 2, 100),
        Difficulty.NORMAL: (2, 50, 2, 3, 500),
        Difficulty.HARD: (5, 150, 3, 4, 3_000),
        Difficulty.VERY_HARD: (10, 999, 3, 4, 10_000),
    }
    if not isinstance(value, dict):
        raise ConfigError(f"{paths.main.name}: difficulties must be a table")
    profiles: dict[Difficulty, DifficultyConfig] = {}
    try:
        for level in Difficulty:
            raw = value.get(level.value, {})
            if not isinstance(raw, dict) or set(raw) - {
                "min_value",
                "max_value",
                "min_terms",
                "max_terms",
                "max_result",
            }:
                raise ValueError(f"unknown field difficulties.{level.value}")
            profile = DifficultyConfig(
                *(
                    int(raw.get(name, default))
                    for name, default in zip(
                        ("min_value", "max_value", "min_terms", "max_terms", "max_result"),
                        defaults[level],
                        strict=True,
                    )
                )
            )
            if profile.min_value < 0 or profile.max_value < profile.min_value:
                raise ValueError(f"difficulties.{level.value} has invalid value range")
            if profile.min_terms < 2 or profile.max_terms < profile.min_terms:
                raise ValueError(f"difficulties.{level.value} has invalid term range")
            if profile.max_result < 1:
                raise ValueError(f"difficulties.{level.value}.max_result must be positive")
            profiles[level] = profile
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid difficulties field: {exc}") from exc
    return profiles


def _parse_timing(value: Any, paths: ConfigPaths) -> OperationTimingConfig:
    if value == {}:
        return ChallengeConfig().operation_timing
    if not isinstance(value, dict) or set(value) - {
        "operation_bonus_enabled",
        "operation_bonus_seconds",
    }:
        raise ConfigError(f"{paths.main.name}: unknown field timing")
    enabled = value.get("operation_bonus_enabled", True)
    defaults = ChallengeConfig().operation_timing.bonus_seconds
    bonuses = value.get("operation_bonus_seconds", defaults)
    if not isinstance(enabled, bool) or not isinstance(bonuses, dict):
        raise ConfigError(f"{paths.main.name}: invalid timing field")
    try:
        parsed = defaults | {Operation(key): float(raw) for key, raw in bonuses.items()}
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"{paths.main.name}: invalid timing operation field: {exc}") from exc
    if any(not math.isfinite(seconds) or seconds < 0 for seconds in parsed.values()):
        raise ConfigError(f"{paths.main.name}: timing bonuses must be non-negative")
    return OperationTimingConfig(enabled, parsed)
