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

`ProblemGenerator` uses a seeded Python random generator, finite arithmetic/topic catalogs, and a static `DifficultyProfile`. It checks operand and `max_result` constraints, groups problems by work signature, and rotates among arithmetic and enabled topic families. The work-unit heuristic defines bands of 1–2 (easy), 2–5 (normal), and 4–9 (hard); a four-number problem cannot exceed 9 units. `normal` and `hard` catalogs drop divisions with a quotient below 3.

Each pick ranks candidates — up to `CANDIDATE_WINDOW` unseen problems per signature group — by a tuple: operator imbalance beyond a slack of 2, whether a large operand (> 12) would exceed `OPERAND_REPEAT_CAP` uses in the session, distance to the target level, total operand reuse, and exact imbalance. Target levels come from a seeded, shuffled cycle over the band's available levels; `start_stage()` restarts the cycle, so every stage spreads evenly over the band and stages stay comparable. Stage kinds independently control base answer limits. Catalogs cycle after unique entries are exhausted and return a warning when repeats become necessary.

`core/tricks.py` holds the `TRICKS` registry and `trick_catalog(max_result)`, which builds single-trick problems with explicit work units. The generator routes `Topic.TRICKS` there with `TRICK_MAX_RESULT` (400/2,500/10,000) instead of the profile's `max_result`, groups trick problems by `(strategy, units)`, ranks them by per-session strategy use, and leaves them out of operation balance. `trick_levels()` derives the levels shown by `numbra tricks`; `Stats.trick_stats()` aggregates trick attempts by `strategy` for `results`.

`Problem.evaluate()` uses a small expression tree and exact rational arithmetic. It supports integer arithmetic, rational square roots, table-backed rational trigonometric values, bounded logarithms, and exponents 2 and 3. Square-root roots are 2–20; power bases are 2–20; logarithm bases are 2, 3, 5, and 10 with integer results −3 through 4. Trigonometric catalogs include only exact rational values. Rational intermediate values, including function arguments, are bounded to denominator 12; candidates over that cap are excluded. The generator does not infer difficulty from saved history.

## Persistence

`Stats` stores completed training summaries, stage rows, and attempts in SQLite, including topic membership, work units, strategy, and generation/scoring versions. The database is migrated idempotently using `PRAGMA user_version`; migration preserves previous rows. Two kinds of history lookups exist. `comparable_history()` requires matching difficulty, operations, stage count, strict mode, duration, enabled topics, generation/scoring versions, and settings fingerprint; sessions from earlier generator versions are not comparable. `progress_history()`, `records()`, and the level recommendation use the looser progress group — difficulty, strict mode, sorted operations, sorted topics — so they survive generator updates. `streak(today)` counts consecutive local dates with a completed training; the current streak may end today or yesterday. The mean time of correct answers is computed per training by a correlated subquery over `attempts`; none of this needs a schema change. Reset deletes data rows without dropping the schema.

## Compatibility boundaries

The public command entry point is `numbra:main`; `numbra.cli.app` and exports from `numbra.config` are also compatibility surfaces. Core business rules belong in `core`; terminal concerns remain in `cli`; configuration parsing and persistence stay in their current packages. Preserve existing config files and SQLite data. Repository change requirements are defined in [AGENTS.md](../../../AGENTS.md).
