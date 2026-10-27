# numbra

English | [Русский](README_RU.md)

`numbra` is a terminal application for regular mental-arithmetic practice. It generates reproducible exercises, runs timed stages, and keeps local SQLite statistics.

## Requirements and installation

Python 3.13 or newer is required. With `uv`:

```bash
uv tool install .
```

To install a ready wheel, download `numbra-<version>-py3-none-any.whl` from the release assets and run:

```bash
uv tool install ./numbra-<version>-py3-none-any.whl
numbra --version
```

For a checkout, install development dependencies with `uv sync --all-groups` and run the command as `uv run numbra`.

## Quick start

```bash
numbra challenge
numbra results
```

The default session targets six minutes and has three stages. Use `Ctrl+C` to cancel; an incomplete session is not saved.

## Commands

`numbra challenge` accepts:

| Option | Default | Meaning |
| --- | --- | --- |
| `-t, --duration MINUTES` | config (6) | Target total duration; must be at least 1 |
| `-d, --difficulty LEVEL` | `normal` | `easy`, `normal`, `hard`, or `very-hard` |
| `-S, --seed INTEGER` | config or generated | Reproduce the same stage and exercise sequence |
| `-o, --operations LIST` | `+,-,*,/` | Comma-separated `+,-,*,/,sqrt,trig,log,power`; `^` aliases `power` |
| `-n, --stages INTEGER` | `3` | Exact number of stages; must be at least 1 |
| `--strict` | off | Fail immediately when an example reaches its limit |
| `--cooldown SECONDS` | `2` | Pause between examples; must be 1 to 3 |
| `--advanced` / `--no-advanced` | config | Enable all basic operations and advanced topics / disable advanced topics |
| `--identities` / `--no-identities` | config | Independently enable or disable numerical identities |

With `-o "sqrt"`, every exercise contains a square root; standalone arithmetic exercises are excluded. Topic exercises use the selected basic operators, or all four when none are selected. `identities` is not an `-o` value; the separate `--sqrt`, `--trig`, `--log`, and `--power` flags have been removed.

For example:

```bash
numbra challenge --duration 6 --difficulty normal --seed 42 --operations +,-,*,/ --stages 3
```

`numbra results --limit 10` shows recent completed sessions and aggregate totals by operation, topic, and difficulty. Previous-session comparisons require matching difficulty, operations, stages, strict mode, duration, topics, generation/scoring versions, and settings fingerprint, so results from earlier generator versions are not treated as comparable to current sessions. Use `numbra results --reset` to clear history after confirmation, or `numbra results --reset --yes` in scripts. `numbra --help`, `numbra --version`, and each command's `--help` document the installed interface.

Stage kinds repeat `slow`, `normal`, `fast`; their default per-answer limits are 15, 10, and 5 seconds. Each stage receives a comparable share of the active-time budget, and examples are selected within the difficulty's static workload band, rather than making later stages harder. A correct answer receives at least 1 point, with 0.2 added for each workload point above the minimum. In soft mode, points decrease linearly to zero at twice the limit; input remains available. `--strict` makes the limit an immediate failed attempt. `--cooldown` pauses before the next example.

Difficulty uses static operand/result profiles and a transparent work-unit rubric: easy 1–2, normal 2–5, hard 4–8, and very-hard 6–12 units. Defaults use 2 terms for easy, 2–3 for normal, and 3–4 for hard and very-hard. Each catalog is finite; when a selected catalog is exhausted, examples repeat and the session prints a warning. Arithmetic honors standard precedence and exact division; answers may be entered as integers or fractions such as `3/4`. Negative intermediate values and answers are allowed. Advanced topics default to off and are selected through `-o`, for example `-o "sqrt,power"`. Powers use exponents 2 and 3; `^` aliases `power`. Enable numerical identities independently with `--identities`. The built-in easy `max_result` is 400; other default profiles are unchanged.

Advanced catalogs are bounded: square roots cover perfect squares with roots 2–20; powers use bases 2–20 and exponents 2 or 3; logarithms use bases 2, 3, 5, or 10 and integer results −3 through 4; trigonometry uses exact rational values from its degree tables; identities use bounded sum/product patterns. Exact rational intermediate values, including function arguments, have denominators at most 12; candidates outside that bound are excluded. Configured or enabled topics must fit the session budget, otherwise Numbra reports the minimum duration needed.

## Configuration and data

On first run, numbra creates `numbra.toml`, `temps.json`, and `design.toml` in the platform's user configuration directory. The default `[features]` table sets `sqrt`, `trig`, `log`, `power`, and `identities` to `false`; there is no `advanced` config key. CLI options override the user file, which overrides built-in defaults. Explicit `-o` replaces configured operations and topics while keeping the independent identities setting. `--advanced` adds all basic operations, topics and identities; `--no-identities` disables identities regardless of argument order. Invalid TOML, JSON, unknown keys, and invalid values are reported with the file and field name. Legacy `difficulty = "very-easy"` maps to `easy` with a warning; a legacy `[difficulties.very-easy]` profile is ignored with a warning. Existing files are not rewritten.

A missing seed creates a new random seed per session; the displayed seed is stored with the results. The database and `numbra.log` are stored in the platform's user data directory. Use `-v` for log messages in stderr; regular logs are written at DEBUG level.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv tool install dist/numbra-1.0.1-py3-none-any.whl
numbra --version
```

The core package does not depend on Typer or Rich and can be used independently. Prompt Toolkit provides the live countdown; SQLite and logging use Python's standard library. There is no cloud sync, account system, GUI, or network API.

## License

MIT. See [LICENSE](LICENSE).
