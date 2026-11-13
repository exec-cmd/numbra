"""Read and change numbra.toml by dotted key. Every write is validated before it reaches disk."""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from .defaults import _DEFAULT_TOML
from .manager import ConfigError, ConfigManager, _parse_settings
from .models import Settings
from .paths import ConfigPaths

_DEFAULTS = tomllib.loads(_DEFAULT_TOML)
_SEED_KEY = "challenge.seed"
_BARE_KEY = re.compile(r"[A-Za-z0-9_]+")
_UNSET = object()


def _flatten(table: dict[str, Any], prefix: str = "") -> list[tuple[str, object]]:
    items: list[tuple[str, object]] = []
    for name, value in table.items():
        if isinstance(value, dict):
            items.extend(_flatten(value, f"{prefix}{name}."))
        else:
            items.append((f"{prefix}{name}", value))
    return items


_KNOWN_KEYS = {key for key, _ in _flatten(_DEFAULTS)} | {_SEED_KEY}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for name, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(name), dict):
            merged[name] = _merge(base[name], value)
        else:
            merged[name] = value
    return merged


def _check_key(key: str) -> None:
    if key not in _KNOWN_KEYS:
        raise ConfigError(f"unknown configuration key: {key}")


def _load(paths: ConfigPaths) -> tuple[dict[str, Any], Any, dict[str, Any], Settings]:
    main, templates, design = ConfigManager(paths).load_documents()
    settings = _parse_settings(main, templates, design, paths)
    return main, templates, design, settings


def list_values(paths: ConfigPaths) -> list[tuple[str, object]]:
    """Effective value of every known key. The seed appears only when it is set."""
    main, _, _, settings = _load(paths)
    values = dict(_flatten(_merge(_DEFAULTS, main)))
    for level, profile in settings.challenge.profiles.items():
        values[f"difficulties.{level.value}.min_terms"] = profile.min_terms
        values[f"difficulties.{level.value}.max_terms"] = profile.max_terms
    return [(key, value) for key, value in values.items() if key in _KNOWN_KEYS]


def get_value(paths: ConfigPaths, key: str) -> object:
    """Effective value of one key, or None when the optional seed is unset."""
    _check_key(key)
    return dict(list_values(paths)).get(key)


def set_value(paths: ConfigPaths, key: str, raw: str) -> None:
    _update(paths, key, _parse_raw(raw))


def unset_value(paths: ConfigPaths, key: str) -> None:
    """Remove the key from the user file so the built-in default applies again."""
    _update(paths, key, _UNSET)


def format_value(value: object) -> str:
    """Render a value as a TOML literal, the same text that is written to numbra.toml."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        # JSON escapes are valid TOML escapes for the strings a validated config can hold.
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return f"[{', '.join(format_value(item) for item in value)}]"
    raise TypeError(f"cannot write {type(value).__name__} to numbra.toml")


def _parse_raw(raw: str) -> object:
    # A bare word such as `hard` is not TOML, so it stays a string.
    try:
        document = tomllib.loads(f"v = {raw}")
    except tomllib.TOMLDecodeError:
        return raw
    return document["v"] if document.keys() == {"v"} else raw


def _table(document: dict[str, Any], parents: list[str], create: bool) -> dict[str, Any] | None:
    table = document
    for name in parents:
        if name not in table:
            if not create:
                return None
            table[name] = {}
        table = table[name]
    return table


def _update(paths: ConfigPaths, key: str, value: object) -> None:
    """Set key to value in the user file, or remove it when value is _UNSET."""
    _check_key(key)
    main, templates, design, _ = _load(paths)
    document = copy.deepcopy(main)
    *parents, leaf = key.split(".")
    table = _table(document, parents, create=value is not _UNSET)
    if table is not None:
        if value is _UNSET:
            table.pop(leaf, None)
        else:
            table[leaf] = value
    if document == main:
        return
    try:
        _parse_settings(document, templates, design, paths)
    except ConfigError as exc:
        detail = str(exc).removeprefix(f"{paths.main.name}: ")
        raise ConfigError(f"{paths.main.name}: cannot set {key}: {detail}") from exc
    _write(paths.main, _dumps(document))


def _write(path: Path, text: str) -> None:
    # Replace in one step, so a failed write never leaves a half-written config.
    temp: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as file:
            temp = Path(file.name)
            file.write(text)
        os.replace(temp, path)
    except OSError as exc:
        if temp is not None:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
        raise ConfigError(f"{path.name}: cannot write config file: {exc}") from exc


def _key(name: str) -> str:
    return name if _BARE_KEY.fullmatch(name) else format_value(name)


def _dump_table(table: dict[str, Any], path: tuple[str, ...], lines: list[str]) -> None:
    if path:
        if lines:
            lines.append("")
        lines.append(f"[{'.'.join(_key(name) for name in path)}]")
    for name, value in table.items():
        if not isinstance(value, dict):
            lines.append(f"{_key(name)} = {format_value(value)}")
    for name, value in table.items():
        if isinstance(value, dict):
            _dump_table(value, (*path, name), lines)


def _dumps(document: dict[str, Any]) -> str:
    lines: list[str] = []
    _dump_table(document, (), lines)
    return "\n".join(lines) + "\n"
