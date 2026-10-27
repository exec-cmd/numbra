# Numbra repository instructions

## Project scope

Numbra is a Python 3.13 terminal application for mental-arithmetic practice. It generates deterministic exercises, runs timed training stages, and stores completed results locally in SQLite. Keep it local-first: the project has no accounts, cloud synchronization, GUI, or network API.

Read the relevant implementation and tests before changing behavior. Prefer the smallest change that preserves existing public imports, CLI flags, configuration files, stored data, and documented product rules.

## Repository map

- `src/numbra/cli/` owns Typer commands, Rich output, Prompt Toolkit input, and logging setup.
- `src/numbra/config/` owns platform paths, default files, parsing, validation, and public config exports.
- `src/numbra/core/` owns arithmetic models, generation, stage allocation, sessions, scoring, and statistics. Keep this package independent of Typer and Rich.
- `src/numbra/core/db/schema.py` defines the SQLite schema. `Stats._migrate()` handles existing databases.
- `tests/` contains CLI, configuration, generator, session/statistics, and product-rule coverage.
- `README.md` and `README_RU.md` document the same user-visible behavior in English and Russian.

## Development commands

Use `uv` and keep `uv.lock` synchronized with `pyproject.toml`.

```bash
uv sync --locked --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv build
```

In restricted environments, set `UV_CACHE_DIR=/tmp/numbra-uv-cache` for `uv` commands. Do not treat dependency-download or cache-permission failures as product failures.

Run checks in proportion to the change. Start with the closest tests while iterating, then run the complete command set above before declaring a code change ready. Documentation-only changes require at least `git diff --check` and a review of the rendered Markdown structure.

## Architecture and compatibility

- Put business rules in `core`, persistence and file parsing in their existing packages, and terminal presentation in `cli`.
- Preserve the public package entry point `numbra:main`, `numbra.cli.app`, and exports from `numbra.config` unless a requested breaking change explicitly permits otherwise.
- Use injected clocks, paths, sleepers, and temporary directories in tests. Tests must not read or write the developer's real configuration, data, database, or log files.
- Keep dataclasses immutable where the current model uses `frozen=True, slots=True`.
- Do not add a production dependency when the standard library or an existing dependency is sufficient. If a dependency is necessary, update both `pyproject.toml` and `uv.lock` and explain the need.

## Product invariants

Treat these as contracts unless the task explicitly changes them:

- A seed reproduces the generated exercise sequence. Exercises are unique within one training, and selected operations are balanced across a generated batch.
- Arithmetic uses integer results and standard operator precedence. Division is exact, non-zero, and never divides a value by itself. Negative intermediate values and answers are allowed.
- Powers use `^`, are limited to exponents 2 and 3 by generation, and are available only for `hard` and `very-hard` when explicitly selected.
- Difficulty comes from transparent static profiles. Do not introduce history-adaptive generation implicitly. Respect operand, term-count, and `max_result` limits.
- Stage kinds cycle through `fast`, `normal`, and `slow`. They change timing, not generator difficulty.
- Soft mode keeps input open after the limit. A correct answer receives a linear time factor that reaches zero at twice the limit. Strict mode ends the attempt at the limit.
- Maximum problem score is complexity-calibrated: `1 + 0.2 * max(0, complexity_score - 3)`. Grades use the existing S/A/B/C/D thresholds.
- Cooldown defaults to two seconds and accepts values from one through three seconds.
- Cancelling a challenge does not save a partial session. Only completed training is persisted.

When changing one of these rules, update the implementation, focused tests, CLI help where applicable, and both READMEs in the same change.

## Configuration and persistence

CLI values override user configuration, which overrides built-in defaults. Keep validation errors user-facing and include the relevant filename or field when possible. TOML has no `null`; omit an optional seed rather than writing an invalid value.

Configuration belongs in the platform config directory. SQLite and `numbra.log` belong in the platform data directory. Logging setup must tolerate an unwritable data directory so that commands such as `--help` and `--version` remain usable.

Preserve existing SQLite data. Schema changes require an idempotent migration based on `PRAGMA user_version`, a legacy-database test, and compatible reads of older rows. Never solve a migration problem by deleting the user's database.

## Testing guidance

- Generator changes: verify seed reproducibility, uniqueness, operation balance, valid evaluation, difficulty bounds, and impossible-profile failure.
- Timing or scoring changes: test exact boundary values, strict and soft modes, operation bonuses, maximum score, grades, and persistence.
- CLI changes: test help text, exit codes, invalid input, cancellation or confirmation behavior, and isolated platform paths.
- Statistics changes: test saving, migration, reset behavior, aggregates, and comparable-history filtering with temporary SQLite files.
- Release-sensitive changes: build the wheel and smoke-test the installed `numbra --help`, `numbra --version`, and a non-interactive results command in a clean environment.

Do not weaken assertions merely to make a failing test pass. Diagnose whether the failure exposes an implementation defect, a stale expectation, or an environment limitation.

## Documentation and delivery

Keep commands, accepted flags, defaults, paths, and behavior in both READMEs synchronized with the code. Use concise factual prose and avoid documenting planned behavior as implemented.

Before editing, inspect `git status`, `git diff`, and `git diff --cached`. Preserve unrelated user changes and report exactly which files were changed and which checks ran. Do not commit, tag, push, publish a release, reset history, or delete user data unless the user explicitly requests it.
