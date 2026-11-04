# Workflow notes

Read when a command fails to start, when you add an import in `core` or at package level, or when you finish a change and need to know what to update. The command list itself is in `AGENTS.md`.

## Environment

- `uv run pytest` or `uv run mypy` may fail with "Failed to spawn" when the virtual environment was created at another path (for example an external drive). Run `uv run python -m pytest` and `uv run python -m mypy`, or recreate the environment with `rm -rf .venv && uv sync --locked --all-groups`.
- Sandboxed runs set `UV_CACHE_DIR=/tmp/numbra-uv-cache`.

## Import boundary

`numbra.core` must load without Typer or Rich. `numbra/__init__.py` and `core/__init__.py` use lazy `__getattr__` imports for this, and `tests/test_imports.py` fails when a terminal dependency leaks into `core` or when `numbra.app` and `numbra.cli.app` diverge. Put new terminal imports in `cli/`.

## Which tests answer which change

Start with the closest file, then run everything.

- Selection and config: `test_operation_selection.py`, `test_config.py`
- Generator and catalogs: `test_generator.py`, `test_generation_features.py`, `test_generation_quality.py`, `test_generation_matrix.py`, `test_expressions.py`, `test_tricks.py`
- Sessions and scoring: `test_challenge.py`, `test_scoring.py`
- Storage and progress: `test_stats.py`, `test_stats_migrations.py`, `test_progress.py`
- Commands and output: `test_cli.py`

## Documentation

User docs live in `docs/eng/` (`usage.md`, `training.md`, `configuration.md`) and the landing summary in `README.md`. Agent reference is this folder. A behavior change updates the matching `docs/eng/` page in the same change.

Done when the checks listed in `AGENTS.md` pass and `git status` shows only intended files.
