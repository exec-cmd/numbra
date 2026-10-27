# Numbra: agent reference

Read the repository instructions in [`AGENTS.md`](../../../AGENTS.md) before changing code. This page is a compact map of the codebase; source and tests are authoritative when describing current runtime behavior.

## Project

Numbra is a Python 3.13+ terminal application for mental-arithmetic practice. It generates seeded exercises, runs timed training, and stores completed sessions in a local SQLite database. The core package is independent of Typer and Rich.

## Code map

- `src/numbra/cli/`: Typer commands, terminal rendering, interactive input, logging.
- `src/numbra/config/`: platform paths, default configuration, parsing, validation, public exports.
- `src/numbra/core/models.py`: arithmetic operations, expressions, and evaluation.
- `src/numbra/core/generator.py`: seeded exercise generation, constraints, operation balance, complexity ordering.
- `src/numbra/core/stages.py`: stage allocation and stage-kind rotation.
- `src/numbra/core/challenge.py`: session planning, timing, scoring, and grades.
- `src/numbra/core/stats.py` and `src/numbra/core/db/schema.py`: SQLite persistence and schema migration.
- `tests/`: CLI, configuration, generator, session/statistics, and product-rule coverage.

## Runtime contracts

- A seed reproduces exercise generation; selected operators are balanced. Finite catalogs can repeat after exhaustion, and the generator warns when that happens.
- Arithmetic uses exact rational results and standard precedence. The CLI accepts fractions such as `3/4`; exact rational intermediate values, including function arguments, have denominator at most 12. Advanced topics include bounded rational square roots, tabular trigonometry, bounded logarithms, powers, and identities.
- Difficulty uses static operand/result profiles and work-unit bands: easy 1–2, normal 2–5, hard 4–8, very-hard 6–12. It does not adapt from history. The default easy `max_result` is 400; other profiles are unchanged.
- Each stage targets comparable effort within the chosen work band. Stage kinds rotate `slow → normal → fast` and control timing, not difficulty.
- Advanced topics default off. The shared operation selection accepts `+,-,*,/,sqrt,trig,log,power` (`^` aliases `power`). Explicit CLI `-o` replaces configured operations and topics, preserving the independent identities setting. `--advanced` adds all basic operations, topics and identities; `--identities/--no-identities` overrides identities. `--no-advanced` disables configured topics while retaining topics explicitly listed in `-o`. Existing `[features]` tables remain readable and files are not rewritten.
- Exercise catalogs are finite. A catalog exhaustion may cause repeats, which are reported as a warning. Every enabled topic must fit in the requested duration or challenge startup reports a minimum duration.
- Soft timing keeps input open after the limit and reduces correct-answer points linearly to zero at twice the limit. Strict timing fails at the limit.
- Only completed trainings are saved. Cancellation does not persist a partial session.
- Topic aggregates are persisted. Previous-session comparisons require matching settings, topic selection, generation version, and scoring version; rows from earlier generator versions are not comparable to current sessions.
- SQLite schema changes must preserve existing data and use an idempotent `PRAGMA user_version` migration.

## Development

Use Python 3.13+ and `uv`. The project checks are listed in [`../human/development.md`](../human/development.md). Keep core business rules out of the CLI layer; use temporary paths and injected dependencies in tests.
