# Architecture

## Package map

- `src/numbra/cli/` owns Typer commands, Rich output, timed terminal input, and logging setup.
- `src/numbra/config/` owns platform paths, defaults, parsing, validation, and public configuration exports.
- `src/numbra/core/` owns arithmetic models, generation, stage allocation, sessions, scoring, and statistics. Keep it independent of Typer and Rich.
- `src/numbra/core/db/schema.py` defines the SQLite schema; `Stats._migrate()` handles older databases.
- `tests/` covers the CLI, configuration, generation, sessions, statistics, and product rules.

## Training flow

The `numbra challenge` command loads settings, combines them with operation selection and tri-state advanced/identities CLI options, and asks `Challenge` to create a `TrainingSession`. The shared operation selection accepts `+,-,*,/,sqrt,trig,log,power` (`^` aliases `power`). Explicit CLI `-o` replaces configured operations and topics, preserving the independent identities setting. `--advanced` adds all basic operations, topics and identities; `--identities/--no-identities` overrides identities. `--no-advanced` disables configured topics while retaining topics explicitly listed in `-o`. Existing `[features]` tables remain readable and files are not rewritten. The session gets an explicit or generated seed, stage kinds, a difficulty profile, enabled topics, and generated problems. The CLI presents problems and gathers timed integer or fractional answers; the session records attempts and computes scores. On normal completion, the CLI saves the completed session and displays its result. Cancellation exits without saving.

## Generation

`ProblemGenerator` uses a seeded Python random generator, finite arithmetic/topic catalogs, and a static `DifficultyProfile`. It checks operand and `max_result` constraints, groups problems by work signature, balances operator counts, and rotates among arithmetic and enabled topic families. The work-unit heuristic defines bands of 1–2 (easy), 2–5 (normal), 4–8 (hard), and 6–12 (very-hard). Stage batches aim for comparable effort within the selected band; stage kinds independently control base answer limits. Catalogs cycle after unique entries are exhausted and return a warning when repeats become necessary.

`Problem.evaluate()` uses a small expression tree and exact rational arithmetic. It supports integer arithmetic, rational square roots, table-backed rational trigonometric values, bounded logarithms, and exponents 2 and 3. Square-root roots are 2–20; power bases are 2–20; logarithm bases are 2, 3, 5, and 10 with integer results −3 through 4. Trigonometric catalogs include only exact rational values. Rational intermediate values, including function arguments, are bounded to denominator 12; candidates over that cap are excluded. The generator does not infer difficulty from saved history.

## Persistence

`Stats` stores completed training summaries, stage rows, and attempts in SQLite, including topic membership, work units, strategy, and generation/scoring versions. The database is migrated idempotently using `PRAGMA user_version`; migration preserves previous rows. Comparable-session filtering requires matching difficulty, operations, stage count, strict mode, duration, enabled topics, generation/scoring versions, and settings fingerprint. Sessions from earlier generator versions are not comparable to current sessions. Reset deletes data rows without dropping the schema.

## Compatibility boundaries

The public command entry point is `numbra:main`; `numbra.cli.app` and exports from `numbra.config` are also compatibility surfaces. Core business rules belong in `core`; terminal concerns remain in `cli`; configuration parsing and persistence stay in their current packages. Preserve existing config files and SQLite data. Repository change requirements are defined in [AGENTS.md](../../../AGENTS.md).
