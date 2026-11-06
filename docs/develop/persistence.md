# Persistence and statistics

Read before changing `core/stats.py`, `core/db/schema.py`, saved fields, history queries, records, streaks, or the level recommendation.

## Schema and migration

- `SCHEMA` (`core/db/schema.py`) creates the full current layout for new databases. `Stats._migrate` brings older databases forward by `PRAGMA user_version` (currently 3).
- A column added to `SCHEMA` needs a matching migration block: the next `if version == N:` step checks `PRAGMA table_info`, adds missing columns, backfills, and sets the new version. Each step is safe to run twice.
- Add a legacy-database test in `tests/test_stats_migrations.py` that builds the old layout by hand, opens it with `Stats`, and reads the old rows back.
- Fix a migration problem in the migration. The user's database file stays in place.

Version 3 adds `trainings.mode TEXT NOT NULL DEFAULT 'challenge'`. Its step checks `PRAGMA table_info` first, and existing rows read as `challenge`. Funbox sessions are saved with `mode = 'funbox'`.

## Writes

`Stats.save` writes one training, its stages, and its attempts in a single connection. Only completed sessions are saved. `seed` is an SQLite `INTEGER`, so it must fit a signed 64-bit value; a larger seed fails at save time, after the session.

`reset` deletes rows from `attempts`, `stages`, `trainings` and keeps the schema.

## Funbox sessions

Every ordinary read filters `trainings.mode = 'challenge'`: `history`, `aggregate`, `breakdown`, `weak_spots`, `trick_stats`, `comparable_history`, `progress_history`, `records`, and `streak`. A new read query over `trainings` must add the same filter, or funbox results leak into records, the recommendation, or the streak. `funbox_history(limit)` and `funbox_stats()` (per mode, from `attempts.strategy`) are the only readers of funbox rows. `reset` deletes both kinds.

## Two kinds of history

- `comparable_history`: exact match on difficulty, stage count, strict mode, target duration, topics, `generation_version`, `scoring_version`, and `settings_fingerprint`; operations compare as a sorted set. Feeds `Previous comparable` and `Delta`.
- Progress group (`_group`, used by `progress_history`, `records`, and the recommendation): difficulty, strict mode, sorted operations, sorted topics. Duration, stage count, and versions do not matter, so records survive generator updates.

Topics in `comparable_history` compare as the stored JSON string, so the order written by `create_session` (the `Topic` enum order) is part of the match.

Mean time of correct answers comes from the `_COMPLETED` join over `attempts`; a training with no correct answer yields `NULL`/`None`. `_COMPLETED` already carries the challenge filter.

## Results views

- `breakdown()` groups attempts of completed trainings by difficulty, operation, and topic. `weak_spots()` adds trick strategies (attempts whose topics include `tricks`). Operations and topics come from each attempt's stored JSON, so a repeated operation counts once per entry.
- `weak_spots(min_attempts=5, limit=3)` drops groups below `min_attempts` and groups without a miss, then ranks by accuracy ascending and average correct time descending. Difficulty groups and the `tricks` topic row (covered by its strategies) are not ranked.
- Averages use correct answers only, and are `None` when a group has none. Accuracy is `correct / attempts`.
- `attempts(training_id)` returns each example of one training in stage and example order. The `results` sparkline uses `history()` scores and needs no query of its own.

## Streak

`streak(today)` counts distinct local dates (`datetime.fromtimestamp`) with a completed training. The current run stays alive through the end of the day after the last training. Tests pass `today` explicitly.

## Where rules live

The recommendation thresholds live in `build_report` (`core/report.py`), while the product rule is in `AGENTS.md`. Change both together, and cover the change in `tests/test_report.py`. The CLI only renders the report.

Done when the focused stats tests pass against `tmp_path` databases, and an old-layout database opens and reads back.
