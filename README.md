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
| `-d, --difficulty LEVEL` | `normal` | `very-easy`, `easy`, `normal`, `hard`, or `very-hard` |
| `-S, --seed INTEGER` | config or generated | Reproduce the same stage and exercise sequence |
| `-o, --operations LIST` | `+,-,*,/` | Comma-separated supported operations |
| `-n, --stages INTEGER` | `3` | Exact number of stages; must be at least 1 |
| `--strict` | off | Fail immediately when an example reaches its limit |
| `--cooldown SECONDS` | `2` | Pause between examples; must be 1 to 3 |

For example:

```bash
numbra challenge --duration 6 --difficulty normal --seed 42 --operations +,-,*,/ --stages 3
```

`numbra results --limit 10` shows recent completed sessions and aggregate totals. Use `numbra results --reset` to clear history after confirmation, or `numbra results --reset --yes` in scripts. `numbra --help`, `numbra --version`, and each command's `--help` document the installed interface.

Stages are `fast`, `normal`, or `slow`. Their default per-answer limits are 5, 10, and 15 seconds. In soft mode, a correct answer receives full score through the limit, then a linear score down to zero at twice the limit; input remains available after that point. `--strict` turns the limit into an immediate failed attempt. `--cooldown` gives a short transition pause before the next example.

Difficulty is defined by a generator profile: very-easy and easy use two numbers, normal mixes two and three, hard uses three and four, and very-hard uses four more often. The profile also bounds operand size and the absolute size of intermediate results. Examples are unique within one training, and selected operations are distributed evenly. `fast`, `normal`, and `slow` stages change only the time limit. Parentheses use standard arithmetic precedence. Small powers (`^2` and `^3`) are available on hard and very-hard only when `^` is explicitly selected. Division is always exact; negative intermediate values and answers are allowed. Profile limits, including `max_result`, can be changed in `numbra.toml`.

## Configuration and data

On first run, numbra creates `numbra.toml`, `temps.json`, and `design.toml` in the platform's user configuration directory. The default database is `numbra.sqlite3` in the platform's user data directory. CLI options override the user file, which overrides built-in defaults. Invalid TOML, JSON, unknown keys, and invalid values are reported with the file and field name.

A missing seed creates a new random seed per session; the displayed seed is stored with the results. The database and `numbra.log` are stored in the platform's user data directory. Use `-v` for log messages in stderr; regular logs are written at DEBUG level.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
uv tool install dist/numbra-0.1.0-py3-none-any.whl
numbra --version
```

The core package does not depend on Typer or Rich and can be used independently. Prompt Toolkit provides the live countdown; SQLite and logging use Python's standard library. There is no cloud sync, account system, GUI, or network API.

## License

MIT. See [LICENSE](LICENSE).
