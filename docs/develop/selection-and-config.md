# Selection and configuration

Read before changing operation/topic selection, `numbra.toml` parsing, defaults, CLI options that mirror config, or platform paths. Value precedence and the `tricks` exception are in `AGENTS.md`.

## Selection grammar

`parse_operation_selection` (`core/models.py`) is the single parser for `-o` and `challenge.operations`. It accepts `+ - * / ^ sqrt trig log power tricks`. `^` and `power` both end up as `Topic.POWER` in `Challenge.create_session`. `identities` is a topic but never an operator token: it comes from `[features]` or `--identities`.

## Resolution order in `create_session`

1. `-o` given: its items replace configured operations and topics. Only the configured `identities` value survives.
2. `--advanced`: every topic on except `tricks` (which keeps its configured or `-o` value), plus all basic operations. `--no-advanced`: topics off except those listed in `-o`.
3. `ChallengeOptions.sqrt/trig/log/power/identities/tricks` apply last. Only the CLI's `identities` is user-reachable; the rest serve programmatic callers and tests.
4. `-o power` together with `power=False` raises `ValueError`.

`advanced` is tri-state: `None` means the flag was not given. Keep that distinction when touching the CLI.

## Files

On first run `ConfigManager.load_or_create` writes `numbra.toml`, `temps.json`, and `design.toml` with exclusive-create (`"x"`), so existing files are never rewritten.

- `numbra.toml`: sections `challenge`, `features`, `timing`, `stages`, `difficulties`. Unknown keys are rejected at every level.
- `temps.json`: parsed and required to be a non-empty string array, but no code reads `settings.templates`. Keep it valid; do not build on it.
- `design.toml`: `[styles]` with `accent`, `success`, `error`, `timer`; the CLI falls back to built-in styles.
- Legacy `very-easy`/`very-hard` map to `easy`/`hard` with a warning (`_LEGACY_DIFFICULTIES`); legacy profile tables are ignored with a warning.

## Adding or changing a setting

1. Update the dataclass in `config/models.py` and the default in `config/defaults.py`.
2. Extend the allowed-key set and the parser in `config/manager.py`. Integer fields use `_integer` (rejects `bool` and floats); numeric fields use `_number` (finite only).
3. Raise `ConfigError` with the filename and field.
4. Cover it in `tests/test_config.py`, including a file without the new key, since users keep older files.
5. Update `docs/eng/configuration.md`.

An absent optional value is an omitted key; TOML has no `null`.

## Paths

`config/paths.py` calls `platformdirs` (`roaming=True` for config, `appauthor=False` for both) so Windows keeps `%APPDATA%\numbra` and `%LOCALAPPDATA%\numbra` without a doubled folder. `tests/conftest.py` redirects `XDG_*`, `APPDATA`, and `LOCALAPPDATA` to `tmp_path` for every test. Windows and macOS paths follow from `platformdirs` and have not been exercised locally.
