from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from .challenge import CompletedTraining
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

    @property
    def score_percent(self) -> float:
        return self.score / self.max_score if self.max_score else 0.0


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


class Stats:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(SCHEMA)
            self._migrate(connection)

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version >= 1:
            return
        training_columns = {row[1] for row in connection.execute("PRAGMA table_info(trainings)")}
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

    def save(self, training: CompletedTraining) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO trainings (started_at, status, difficulty, seed, operations, "
                "target_seconds, actual_seconds, stages, total_examples, correct_answers, "
                "timeouts, average_response, strict_mode, cooldown_seconds, score, max_score) "
                "VALUES (?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("SQLite did not return a training id")
            training_id = cursor.lastrowid
            for stage in training.stages:
                stage_attempts = [
                    item for item in training.attempts if item.stage_number == stage.number
                ]
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
                        "overtime, score) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                "SELECT * FROM trainings WHERE status = 'completed' "
                "ORDER BY started_at DESC LIMIT ?",
                (max(0, limit),),
            ).fetchall()
        return [
            TrainingRecord(
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
            )
            for row in rows
        ]

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
                "SELECT a.operations, a.is_correct FROM attempts a JOIN stages s ON s.id = a.stage_id "
                "JOIN trainings t ON t.id = s.training_id WHERE t.status = 'completed'"
            ).fetchall()
            difficulty_rows = connection.execute(
                "SELECT difficulty, COALESCE(SUM(total_examples), 0) AS total, "
                "COALESCE(SUM(correct_answers), 0) AS correct FROM trainings "
                "WHERE status = 'completed' GROUP BY difficulty"
            ).fetchall()
        accuracy = row["correct"] / row["examples"] if row["examples"] else 0.0
        operation_totals: dict[str, list[int]] = {}
        for item in operation_rows:
            for operation in json.loads(item["operations"]):
                values = operation_totals.setdefault(operation, [0, 0])
                values[0] += 1
                values[1] += int(item["is_correct"])
        by_operation = {
            operation: (values[0], values[1]) for operation, values in operation_totals.items()
        }
        by_difficulty = {
            item["difficulty"]: (item["total"], item["correct"]) for item in difficulty_rows
        }
        return AggregateStats(
            row["trainings"],
            row["examples"],
            row["correct"],
            accuracy,
            average_row["average"],
            row["timeouts"],
            by_operation,
            by_difficulty,
        )

    def comparable_history(
        self, training: CompletedTraining, limit: int = 2
    ) -> list[TrainingRecord]:
        operations = tuple(sorted(operation.value for operation in training.operations))
        return [
            row
            for row in self.history(max(limit * 4, 10))
            if tuple(sorted(row.operations)) == operations
            and row.difficulty == training.difficulty.value
            and row.stages == len(training.stages)
            and row.strict == training.strict
            and row.target_duration_seconds == training.duration_target_seconds
        ][:limit]
