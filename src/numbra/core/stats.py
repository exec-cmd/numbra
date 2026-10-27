from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from .challenge import AnswerAttempt, CompletedTraining
from .db.schema import SCHEMA


@dataclass(frozen=True, slots=True)
class TrainingRecord:
    identifier: int
    started_at: float
    difficulty: str
    stages: int
    total_examples: int
    correct_answers: int
    accuracy: float
    average_response_seconds: float
    timeouts: int
    actual_duration_seconds: float
    target_duration_seconds: float
    operations: tuple[str, ...]
    strict: bool
    cooldown_seconds: float
    score: float
    max_score: float
    topics: tuple[str, ...] = ()
    generation_version: int = 1
    scoring_version: int = 1
    settings_fingerprint: str = ""
    average_correct_seconds: float | None = None

    @property
    def score_percent(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


@dataclass(frozen=True, slots=True)
class PersonalRecord:
    difficulty: str
    strict: bool
    operations: tuple[str, ...]
    topics: tuple[str, ...]
    sessions: int
    best_score_percent: float
    best_average_correct_seconds: float | None


# Completed trainings with the mean time of their correct answers (NULL when none).
# One grouped pass over attempts; a correlated subquery rescans them per training.
_COMPLETED = (
    "SELECT t.*, c.average_correct FROM trainings t LEFT JOIN ("
    "SELECT s.training_id, AVG(a.elapsed) AS average_correct FROM attempts a "
    "JOIN stages s ON s.id = a.stage_id WHERE a.is_correct = 1 GROUP BY s.training_id"
    ") c ON c.training_id = t.id WHERE t.status = 'completed' "
)


@dataclass(frozen=True, slots=True)
class AggregateStats:
    completed_trainings: int
    total_examples: int
    correct_answers: int
    accuracy: float
    average_response_seconds: float
    timeouts: int
    by_operation: dict[str, tuple[int, int]]
    by_difficulty: dict[str, tuple[int, int]]
    by_topic: dict[str, tuple[int, int]] = field(default_factory=dict)


class Stats:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.database_path)) as connection, connection:
            connection.row_factory = sqlite3.Row
            yield connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version == 0:
            training_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(trainings)")
            }
            for name, definition in (
                ("strict_mode", "INTEGER NOT NULL DEFAULT 0"),
                ("cooldown_seconds", "REAL NOT NULL DEFAULT 2"),
                ("score", "REAL NOT NULL DEFAULT 0"),
                ("max_score", "REAL NOT NULL DEFAULT 0"),
            ):
                if name not in training_columns:
                    connection.execute(f"ALTER TABLE trainings ADD COLUMN {name} {definition}")
            attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
            for name, definition in (
                ("operations", "TEXT NOT NULL DEFAULT '[]'"),
                ("overtime", "REAL NOT NULL DEFAULT 0"),
                ("score", "REAL NOT NULL DEFAULT 0"),
            ):
                if name not in attempt_columns:
                    connection.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
            connection.execute(
                "UPDATE trainings SET score = correct_answers, max_score = total_examples "
                "WHERE max_score = 0"
            )
            rows = connection.execute(
                "SELECT id, operation FROM attempts WHERE operations = '[]'"
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE attempts SET operations = ? WHERE id = ?",
                    (json.dumps([row["operation"]]), row["id"]),
                )
            connection.execute("PRAGMA user_version = 1")
            version = 1

        if version == 1:
            training_columns = {
                row[1] for row in connection.execute("PRAGMA table_info(trainings)")
            }
            for name, definition in (
                ("topics", "TEXT NOT NULL DEFAULT '[]'"),
                ("generation_version", "INTEGER NOT NULL DEFAULT 1"),
                ("scoring_version", "INTEGER NOT NULL DEFAULT 1"),
                ("settings_fingerprint", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in training_columns:
                    connection.execute(f"ALTER TABLE trainings ADD COLUMN {name} {definition}")
            attempt_columns = {row[1] for row in connection.execute("PRAGMA table_info(attempts)")}
            for name, definition in (
                ("topics", "TEXT NOT NULL DEFAULT '[]'"),
                ("work_units", "INTEGER NOT NULL DEFAULT 0"),
                ("strategy", "TEXT NOT NULL DEFAULT ''"),
            ):
                if name not in attempt_columns:
                    connection.execute(f"ALTER TABLE attempts ADD COLUMN {name} {definition}")
            connection.execute("PRAGMA user_version = 2")

    def save(self, training: CompletedTraining) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO trainings (started_at, status, difficulty, seed, operations, "
                "target_seconds, actual_seconds, stages, total_examples, correct_answers, "
                "timeouts, average_response, strict_mode, cooldown_seconds, score, max_score, "
                "topics, generation_version, scoring_version, settings_fingerprint) "
                "VALUES (?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    training.started_at,
                    training.difficulty.value,
                    training.seed,
                    json.dumps([op.value for op in training.operations]),
                    training.duration_target_seconds,
                    training.actual_duration_seconds,
                    len(training.stages),
                    training.total_examples,
                    training.correct_answers,
                    training.timeouts,
                    training.average_response_seconds,
                    int(training.strict),
                    training.cooldown_seconds,
                    float(training.score),
                    float(training.max_score),
                    json.dumps([topic.value for topic in training.topics]),
                    training.generation_version,
                    training.scoring_version,
                    training.settings_fingerprint,
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a training id")
            training_id = cursor.lastrowid
            attempts_by_stage: dict[int, list[AnswerAttempt]] = {}
            for attempt in training.attempts:
                attempts_by_stage.setdefault(attempt.stage_number, []).append(attempt)
            for stage in training.stages:
                stage_attempts = attempts_by_stage.get(stage.number, [])
                stage_cursor = connection.execute(
                    "INSERT INTO stages(training_id, number, kind, examples, duration) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        training_id,
                        stage.number,
                        stage.kind.value,
                        len(stage.problems),
                        sum(item.elapsed_seconds for item in stage_attempts),
                    ),
                )
                if stage_cursor.lastrowid is None:
                    raise RuntimeError("SQLite did not return a stage id")
                stage_id = stage_cursor.lastrowid
                for attempt in stage_attempts:
                    problem = stage.problems[attempt.problem_number - 1]
                    connection.execute(
                        "INSERT INTO attempts(stage_id, number, expression, correct_answer, "
                        "user_answer, is_correct, elapsed, timed_out, operation, operations, "
                        "overtime, score, topics, work_units, strategy) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            stage_id,
                            attempt.problem_number,
                            attempt.expression,
                            str(attempt.correct_answer),
                            attempt.user_answer,
                            int(attempt.is_correct),
                            attempt.elapsed_seconds,
                            int(attempt.timed_out),
                            attempt.operation.value,
                            json.dumps([operation.value for operation in problem.operations]),
                            attempt.overtime_seconds,
                            float(attempt.score),
                            json.dumps([topic.value for topic in problem.topics]),
                            problem.work_units if problem.work_units is not None else 0,
                            problem.strategy,
                        ),
                    )
            return training_id

    def reset(self) -> None:
        """Delete all saved training data while retaining the database schema."""
        with self._connect() as connection:
            connection.execute("DELETE FROM attempts")
            connection.execute("DELETE FROM stages")
            connection.execute("DELETE FROM trainings")

    def history(self, limit: int = 10) -> list[TrainingRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                _COMPLETED + "ORDER BY started_at DESC LIMIT ?",
                (max(0, limit),),
            ).fetchall()
        return [_training_record(row) for row in rows]

    def aggregate(self) -> AggregateStats:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS trainings, COALESCE(SUM(total_examples), 0) AS examples, "
                "COALESCE(SUM(correct_answers), 0) AS correct, COALESCE(SUM(timeouts), 0) "
                "AS timeouts FROM trainings WHERE status = 'completed'"
            ).fetchone()
            average_row = connection.execute(
                "SELECT COALESCE(AVG(a.elapsed), 0) AS average FROM attempts a "
                "JOIN stages s ON s.id = a.stage_id JOIN trainings t ON t.id = s.training_id "
                "WHERE t.status = 'completed' AND a.timed_out = 0"
            ).fetchone()
            operation_rows = connection.execute(
                "SELECT a.operations, a.topics, a.is_correct, COUNT(*) AS total FROM attempts a "
                "JOIN stages s ON s.id = a.stage_id "
                "JOIN trainings t ON t.id = s.training_id WHERE t.status = 'completed' "
                "GROUP BY a.operations, a.topics, a.is_correct"
            ).fetchall()
            difficulty_rows = connection.execute(
                "SELECT difficulty, COALESCE(SUM(total_examples), 0) AS total, "
                "COALESCE(SUM(correct_answers), 0) AS correct FROM trainings "
                "WHERE status = 'completed' GROUP BY difficulty"
            ).fetchall()
        accuracy = row["correct"] / row["examples"] if row["examples"] else 0.0
        operation_totals: dict[str, list[int]] = {}
        topic_totals: dict[str, list[int]] = {}
        for item in operation_rows:
            for operation in json.loads(item["operations"]):
                values = operation_totals.setdefault(operation, [0, 0])
                values[0] += item["total"]
                values[1] += item["total"] * int(item["is_correct"])
            for topic in json.loads(item["topics"]):
                values = topic_totals.setdefault(topic, [0, 0])
                values[0] += item["total"]
                values[1] += item["total"] * int(item["is_correct"])
        by_operation = {
            operation: (values[0], values[1]) for operation, values in operation_totals.items()
        }
        by_difficulty = {
            item["difficulty"]: (item["total"], item["correct"]) for item in difficulty_rows
        }
        by_topic = {topic: (values[0], values[1]) for topic, values in topic_totals.items()}
        return AggregateStats(
            row["trainings"],
            row["examples"],
            row["correct"],
            accuracy,
            average_row["average"],
            row["timeouts"],
            by_operation,
            by_difficulty,
            by_topic,
        )

    def comparable_history(
        self, training: CompletedTraining, limit: int = 2
    ) -> list[TrainingRecord]:
        operations = tuple(sorted(operation.value for operation in training.operations))
        if limit <= 0:
            return []
        topics = json.dumps([topic.value for topic in training.topics])
        with self._connect() as connection:
            rows = connection.execute(
                _COMPLETED + "AND difficulty = ? "
                "AND stages = ? AND strict_mode = ? AND target_seconds = ? AND topics = ? "
                "AND generation_version = ? AND scoring_version = ? "
                "AND settings_fingerprint = ? ORDER BY started_at DESC",
                (
                    training.difficulty.value,
                    len(training.stages),
                    int(training.strict),
                    training.duration_target_seconds,
                    topics,
                    training.generation_version,
                    training.scoring_version,
                    training.settings_fingerprint,
                ),
            )
            records = []
            for row in rows:
                if tuple(sorted(json.loads(row["operations"]))) == operations:
                    records.append(_training_record(row))
                    if len(records) == limit:
                        break
        return records

    def progress_history(
        self, training: CompletedTraining, limit: int | None = None
    ) -> list[TrainingRecord]:
        """Completed trainings in the same progress group, newest first."""
        if limit is not None and limit <= 0:
            return []
        key = (
            training.difficulty.value,
            training.strict,
            tuple(sorted(operation.value for operation in training.operations)),
            tuple(sorted(topic.value for topic in training.topics)),
        )
        with self._connect() as connection:
            rows = connection.execute(
                _COMPLETED + "AND difficulty = ? AND strict_mode = ? ORDER BY started_at DESC",
                (training.difficulty.value, int(training.strict)),
            ).fetchall()
        records = [record for record in map(_training_record, rows) if _group(record) == key]
        return records if limit is None else records[:limit]

    def records(self) -> list[PersonalRecord]:
        with self._connect() as connection:
            rows = connection.execute(_COMPLETED + "ORDER BY started_at").fetchall()
        groups: dict[tuple[str, bool, tuple[str, ...], tuple[str, ...]], list[TrainingRecord]] = {}
        for record in map(_training_record, rows):
            groups.setdefault(_group(record), []).append(record)
        result = []
        for (difficulty, strict, operations, topics), items in groups.items():
            times = [
                r.average_correct_seconds for r in items if r.average_correct_seconds is not None
            ]
            result.append(
                PersonalRecord(
                    difficulty,
                    strict,
                    operations,
                    topics,
                    len(items),
                    max(r.score_percent for r in items),
                    min(times, default=None),
                )
            )
        return sorted(result, key=lambda record: -record.sessions)

    def streak(self, today: date) -> tuple[int, int]:
        """Current and best runs of consecutive local days with a completed training."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT started_at FROM trainings WHERE status = 'completed'"
            ).fetchall()
        days = {datetime.fromtimestamp(row["started_at"]).date() for row in rows}
        best = run = 0
        previous: date | None = None
        for day in sorted(days):
            run = run + 1 if previous is not None and day - previous == timedelta(days=1) else 1
            best = max(best, run)
            previous = day
        # A streak survives until the end of the day after the last training.
        cursor = today if today in days else today - timedelta(days=1)
        current = 0
        while cursor in days:
            current += 1
            cursor -= timedelta(days=1)
        return current, best


def _group(record: TrainingRecord) -> tuple[str, bool, tuple[str, ...], tuple[str, ...]]:
    """Progress group: survives generator updates and duration changes."""
    return (
        record.difficulty,
        record.strict,
        tuple(sorted(record.operations)),
        tuple(sorted(record.topics)),
    )


def _training_record(row: sqlite3.Row) -> TrainingRecord:
    return TrainingRecord(
        row["id"],
        row["started_at"],
        row["difficulty"],
        row["stages"],
        row["total_examples"],
        row["correct_answers"],
        row["correct_answers"] / row["total_examples"] if row["total_examples"] else 0.0,
        row["average_response"],
        row["timeouts"],
        row["actual_seconds"],
        row["target_seconds"],
        tuple(json.loads(row["operations"])),
        bool(row["strict_mode"]),
        row["cooldown_seconds"],
        row["score"],
        row["max_score"],
        tuple(json.loads(row["topics"])),
        row["generation_version"],
        row["scoring_version"],
        row["settings_fingerprint"],
        row["average_correct"] if "average_correct" in row.keys() else None,
    )
