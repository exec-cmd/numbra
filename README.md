# numbra

English | [Русский](README_RU.md)

`numbra` is a terminal application for regular mental-arithmetic practice. It generates reproducible exercises, runs timed stages, and keeps local SQLite statistics.

## Requirements and installation

Python 3.13 or newer is required. With `uv`:

```bash
uv tool install numbra
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
| `--duration MINUTES` | config (6) | Target total duration; must be at least 1 |
| `--difficulty LEVEL` | `normal` | `easy`, `normal`, or `hard` |
| `--seed INTEGER` | config or generated | Reproduce the same stage and exercise sequence |
| `--operations LIST` | `+,-,*,/` | Comma-separated supported operations |
| `--stages INTEGER` | `3` | Exact number of stages; must be at least 1 |

For example:

```bash
numbra challenge --duration 6 --difficulty normal --seed 42 --operations +,-,*,/ --stages 3
```

`numbra results --limit 10` shows recent completed sessions and aggregate totals. `numbra --help`, `numbra --version`, and each command's `--help` document the installed interface.

Stages are `fast`, `normal`, or `slow`. Their default per-answer limits are 5, 10, and 15 seconds. Difficulty controls the deterministic distribution: for three stages, easy is 0/1/2 fast/normal/slow, normal is 1/1/1, and hard is 2/1/0. For another stage count, the largest-remainder method preserves the requested total.

## Configuration and data

On first run, numbra creates `numbra.toml`, `temps.json`, and `design.toml` in the platform's user configuration directory. The default database is `numbra.sqlite3` in the platform's user data directory. CLI options override the user file, which overrides built-in defaults. Invalid TOML, JSON, unknown keys, and invalid values are reported with the file and field name.

`examples/numbra.toml` is a complete editable example. A missing seed creates a new random seed per session; the displayed seed is stored with the results.

## Development

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

The core package does not depend on Typer or Rich and can be used independently. The timer uses Prompt Toolkit when installed; SQLite is provided by Python's standard library. There is no cloud sync, account system, GUI, or network API.

## License

MIT. See [LICENSE](LICENSE).
