# Configuration

## Files and precedence

On first run, Numbra creates three files in its user configuration directory:

- `numbra.toml` — challenge defaults, timing, stage limits, and difficulty profiles.
- `temps.json` — a non-empty JSON array of strings. The current generator constructs expressions directly and does not use these strings.
- `design.toml` — Rich styles under the `[styles]` table.

For challenge values, command-line options take precedence over `numbra.toml`, which takes precedence over built-in defaults. `--strict` and `--cooldown` are command options with their own defaults. Invalid syntax, unknown fields, or invalid values produce a user-facing error that identifies the file or field.

## Paths

Configuration files use the platform configuration directory:

- Linux and other Unix platforms: `$XDG_CONFIG_HOME/numbra`, or `~/.config/numbra` when unset.
- macOS: `~/Library/Application Support/numbra`.
- Windows: `%APPDATA%\numbra`.

The SQLite database (`numbra.sqlite3`) and log (`numbra.log`) use the platform data directory:

- Linux and other Unix platforms: `$XDG_DATA_HOME/numbra`, or `~/.local/share/numbra` when unset.
- macOS: `~/Library/Application Support/numbra`.
- Windows: `%LOCALAPPDATA%\numbra`.

## Main settings

The default `numbra.toml` contains `[challenge]` values for `duration_minutes` (6), `difficulty` (`normal`), `stages` (3), and `operations` (`["+", "-", "*", "/"]`). An optional integer `seed` may be set; omit it to generate a new session seed. Supported difficulty values are `easy`, `normal`, and `hard`.

`[features]` accepts five boolean values, all `false` by default:

```toml
[features]
sqrt = false
trig = false
log = false
power = false
identities = false
```

There is no `advanced` configuration key. The shared operation selection accepts `+,-,*,/,sqrt,trig,log,power` (`^` aliases `power`). Explicit CLI `-o` replaces configured operations and topics, preserving the independent identities setting. `--advanced` adds all basic operations, topics and identities; `--identities/--no-identities` overrides identities. `--no-advanced` disables configured topics while retaining topics explicitly listed in `-o`. Existing `[features]` tables remain readable and files are not rewritten.

`[stages.fast]`, `[stages.normal]`, and `[stages.slow]` each accept a positive `limit_seconds`, defaulting to 5, 10, and 15 seconds. `[timing]` accepts `operation_bonus_enabled` and an `[timing.operation_bonus_seconds]` table. Bonuses must be finite and non-negative. Defaults are 0 seconds for `+` and `-`, 1 for `*`, 2 for `/`, and 3 for `^`.

## Difficulty profiles

Each `[difficulties.<level>]` table accepts `min_value`, `max_value`, `min_terms`, `max_terms`, and `max_result`. Defaults are:

| Level | Min value | Max value | Min terms | Max terms | Max result |
| --- | ---: | ---: | ---: | ---: | ---: |
| `easy` | 1 | 20 | 2 | 2 | 400 |
| `normal` | 2 | 50 | 2 | 3 | 500 |
| `hard` | 5 | 999 | 3 | 4 | 10,000 |

Profiles are static. Values must define a valid operand and term range, and `max_result` must be positive. The result bound is applied to generated intermediate values and answers.

Work-unit bands are fixed in `core/generator.py` (`WORK_BANDS`): easy 1–2, normal 2–5, hard 4–9. Four-number problems cannot exceed 9 units under the current heuristic, which is why `very-hard` (6–12) was removed in 1.3.

For migration, legacy `challenge.difficulty = "very-easy"` or `"very-hard"` is read as `easy` or `hard` and produces a warning (`_LEGACY_DIFFICULTIES` in `config/manager.py`). Legacy `[difficulties.very-easy]` and `[difficulties.very-hard]` tables are ignored with a warning. Stored sessions keep their original difficulty string and remain readable. Numbra does not rewrite the existing TOML file; edit or remove those legacy values yourself. A new configuration file contains only the current difficulty profiles.

## Templates and styles

`temps.json` must contain at least one string. It is parsed and validated but is not currently used to form generated expressions. `design.toml` accepts a `[styles]` table of string values. The CLI reads `accent`, `success`, `error`, and `timer`; omitted values use `bold cyan`, `green`, `bold red`, and `yellow` respectively.

## Validation

TOML files are parsed as TOML and `temps.json` as JSON. Unknown top-level or nested keys are rejected. Challenge duration and stage count must be at least 1; operations cannot be empty; stage limits must be positive; operation bonuses cannot be negative; and difficulty ranges must be valid. Integer fields require TOML integers, excluding booleans and fractional values; numeric fields accept only finite TOML integers or floats, excluding booleans and strings. Operations require an array of strings, and stage/profile sections require tables. File creation, reading, and UTF-8 decoding errors identify the affected path; validation errors identify the filename and field. Do not encode an absent seed as TOML `null`; omit the key.
