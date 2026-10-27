from __future__ import annotations

import sqlite3
from pathlib import Path

from numbra.core.stats import Stats


def _create_v0_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE trainings (
                id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL NOT NULL,
                status TEXT NOT NULL, difficulty TEXT NOT NULL, seed INTEGER NOT NULL,
                operations TEXT NOT NULL, target_seconds REAL NOT NULL,
                actual_seconds REAL NOT NULL, stages INTEGER NOT NULL,
                total_examples INTEGER NOT NULL, correct_answers INTEGER NOT NULL,
                timeouts INTEGER NOT NULL, average_response REAL NOT NULL
            );
            CREATE TABLE stages (
                id INTEGER PRIMARY KEY AUTOINCREMENT, training_id INTEGER NOT NULL,
                number INTEGER NOT NULL, kind TEXT NOT NULL, examples INTEGER NOT NULL,
                duration REAL NOT NULL
            );
            CREATE TABLE attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT, stage_id INTEGER NOT NULL,
                number INTEGER NOT NULL, expression TEXT NOT NULL,
                correct_answer TEXT NOT NULL, user_answer TEXT,
                is_correct INTEGER NOT NULL, elapsed REAL NOT NULL,
                timed_out INTEGER NOT NULL, operation TEXT NOT NULL
            );
            INSERT INTO trainings VALUES
                (1, 1700000000, 'completed', 'normal', 1, '["+"]', 60, 2,
                 1, 1, 1, 0, 1);
            INSERT INTO stages VALUES (1, 1, 1, 'normal', 1, 1);
            INSERT INTO attempts VALUES
                (1, 1, 1, '1 + 1', '2', '2', 1, 1, 0, '+');
            """
        )


def test_v0_migration_preserves_rows_and_adds_v2_defaults(tmp_path: Path) -> None:
    database = tmp_path / "v0.sqlite3"
    _create_v0_database(database)

    stats = Stats(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        training = connection.execute(
            "SELECT score, max_score, topics, generation_version, scoring_version, "
            "settings_fingerprint FROM trainings WHERE id = 1"
        ).fetchone()
        attempt = connection.execute(
            "SELECT operations, topics, work_units, strategy FROM attempts WHERE id = 1"
        ).fetchone()
    assert version == 2
    assert training == (1.0, 1.0, "[]", 1, 1, "")
    assert attempt == ('["+"]', "[]", 0, "")
    assert len(stats.history()) == 1


def test_v1_migration_does_not_rewrite_legacy_scores_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "v1.sqlite3"
    _create_v0_database(database)
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            ALTER TABLE trainings ADD COLUMN strict_mode INTEGER NOT NULL DEFAULT 0;
            ALTER TABLE trainings ADD COLUMN cooldown_seconds REAL NOT NULL DEFAULT 2;
            ALTER TABLE trainings ADD COLUMN score REAL NOT NULL DEFAULT 0;
            ALTER TABLE trainings ADD COLUMN max_score REAL NOT NULL DEFAULT 0;
            ALTER TABLE attempts ADD COLUMN operations TEXT NOT NULL DEFAULT '[]';
            ALTER TABLE attempts ADD COLUMN overtime REAL NOT NULL DEFAULT 0;
            ALTER TABLE attempts ADD COLUMN score REAL NOT NULL DEFAULT 0;
            UPDATE trainings SET score = 0.375, max_score = 4.5 WHERE id = 1;
            PRAGMA user_version = 1;
            """
        )

    stats = Stats(database)
    Stats(database)

    with sqlite3.connect(database) as connection:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        score = connection.execute("SELECT score, max_score FROM trainings WHERE id = 1").fetchone()
    assert version == 2
    assert score == (0.375, 4.5)
    assert len(stats.history()) == 1
