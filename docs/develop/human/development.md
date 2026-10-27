# Development

## Environment

Numbra targets Python 3.13 or newer and uses `uv`. Install the locked development environment with:

```bash
uv sync --locked --all-groups
```

If the environment restricts cache writes, set `UV_CACHE_DIR=/tmp/numbra-uv-cache` for the command. If `uv run pytest` fails with "Failed to spawn", the virtual environment was created at another path; recreate it (`rm -rf .venv && uv sync --locked --all-groups`) or run tools as `.venv/bin/python -m pytest`.

## Checks

Run the project checks with:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

For documentation-only changes, run `git diff --check` and review the rendered Markdown structure. Run focused checks while changing code, then the full set above before declaring a code change ready.

## Test map

- `tests/test_cli.py` covers help/version, option errors, result commands, timing input, and challenge output.
- `tests/test_config.py` covers generated defaults, parsing errors, profiles, and timing configuration.
- `tests/test_generator.py`, `tests/test_generation_features.py`, and `tests/test_generation_matrix.py` cover generator behavior, topic output, and broad seeded acceptance.
- `tests/test_generation_quality.py` covers band-level coverage per stage, operand repeat limits, small-quotient filtering, and seed reproducibility.
- `tests/test_expressions.py` covers exact expression parsing, rational evaluation, function domains, canonical forms, and work units.
- `tests/test_challenge.py` covers session setup, answer handling, stage budgets, timing, and comparable effort.
- `tests/test_operation_selection.py` covers operation and topic selection through configuration and CLI options.
- `tests/test_scoring.py` covers score boundaries, complexity-based scores, and strict timeouts.
- `tests/test_stats.py` and `tests/test_stats_migrations.py` cover persistence, aggregates, reset, schema migrations, comparable-history filters, and legacy `very-hard` rows.
- `tests/test_progress.py` covers progress groups, correct-answer averages, personal records, and day streaks.
- `tests/test_imports.py` checks that `numbra.core` loads without Typer or Rich and that public app imports resolve to one Typer app.

Tests should use injected clocks and temporary paths; they must not access a developer's real configuration, database, data, or log files.

## Change rules

Read the relevant implementation and tests before changing behavior. Keep changes small and preserve public imports, CLI flags, configuration files, stored data, and documented product rules. Put business rules in `core`, parsing and persistence in their existing packages, and terminal presentation in `cli`. Keep `pyproject.toml` and `uv.lock` synchronized when dependencies change; avoid new production dependencies when the standard library or an existing dependency is sufficient.

When a product rule changes, update its focused tests, CLI help where applicable, and both repository READMEs. Keep commands, flags, defaults, paths, and behavior accurate in both languages. Follow the full repository instructions in [AGENTS.md](../../../AGENTS.md).
