# Persistence and statistics

Read before changing `core/stats.py`, `core/db/schema.py`, saved fields, history queries, records, streaks, or the level recommendation.

## Schema and migration

- `SCHEMA` (`core/db/schema.py`) creates the full current layout for new databases. `Stats._migrate` brings older databases forward by `PRAGMA user_version` (currently 2).
- A column added to `SCHEMA` needs a matching migration block: the next `if version == N:` step checks `PRAGMA table_info`, adds missing columns, backfills, and sets the new version. Each step is safe to run twice.
- Add a legacy-database test in `tests/test_stats_migrations.py` that builds the old layout by hand, opens it with `Stats`, and reads the old rows back.
- Fix a migration problem in the migration. The user's database file stays in place.

## Writes

`Stats.save` writes one training, its stages, and its attempts in a single connection. Only completed sessions are saved. `seed` is an SQLite `INTEGER`, so it must fit a signed 64-bit value; a larger seed fails at save time, after the session.

`reset` deletes rows from `attempts`, `stages`, `trainings` and keeps the schema.

## Two kinds of history

- `comparable_history`: exact match on difficulty, stage count, strict mode, target duration, topics, `generation_version`, `scoring_version`, and `settings_fingerprint`; operations compare as a sorted set. Feeds `Previous comparable` and `Delta`.
- Progress group (`_group`, used by `progress_history`, `records`, and the recommendation): difficulty, strict mode, sorted operations, sorted topics. Duration, stage count, and versions do not matter, so records survive generator updates.

Topics in `comparable_history` compare as the stored JSON string, so the order written by `create_session` (the `Topic` enum order) is part of the match.

Mean time of correct answers comes from the `_COMPLETED` join over `attempts`; a training with no correct answer yields `NULL`/`None`.

## Streak

`streak(today)` counts distinct local dates (`datetime.fromtimestamp`) with a completed training. The current run stays alive through the end of the day after the last training. Tests pass `today` explicitly.

## Where rules live

The recommendation thresholds live in `build_report` (`core/report.py`), while the product rule is in `AGENTS.md`. Change both together, and cover the change in `tests/test_report.py`. The CLI only renders the report.

Done when the focused stats tests pass against `tmp_path` databases, and an old-layout database opens and reads back.
