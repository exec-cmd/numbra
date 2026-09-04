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

    def save(self, training: CompletedTraining) -> int:
        with self._connect() as connection:
            cursor = connection.execute(
                "INSERT INTO trainings VALUES (NULL, ?, 'completed', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                ),
            )
            training_id = int(cursor.lastrowid)
            for stage in training.stages:
                stage_attempts = [
                    item for item in training.attempts if item.stage_number == stage.number
                ]
                stage_cursor = connection.execute(
                    "INSERT INTO stages(training_id, number, kind, examples, duration) VALUES (?, ?, ?, ?, ?)",
                    (
                        training_id,
                        stage.number,
                        stage.kind.value,
                        len(stage.problems),
                        sum(item.elapsed_seconds for item in stage_attempts),
                    ),
                )
                stage_id = int(stage_cursor.lastrowid)
                for attempt in stage_attempts:
                    connection.execute(
                        "INSERT INTO attempts(stage_id, number, expression, correct_answer, user_answer, is_correct, elapsed, timed_out, operation) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                        ),
                    )
            return training_id

    def history(self, limit: int = 10) -> list[TrainingRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM trainings WHERE status = 'completed' ORDER BY started_at DESC LIMIT ?",
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
            )
            for row in rows
        ]

    def aggregate(self) -> AggregateStats:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS trainings, COALESCE(SUM(total_examples), 0) AS examples, COALESCE(SUM(correct_answers), 0) AS correct, COALESCE(SUM(timeouts), 0) AS timeouts FROM trainings WHERE status = 'completed'"
            ).fetchone()
            average_row = connection.execute(
                "SELECT COALESCE(AVG(a.elapsed), 0) AS average FROM attempts a JOIN stages s ON s.id = a.stage_id JOIN trainings t ON t.id = s.training_id WHERE t.status = 'completed' AND a.timed_out = 0"
            ).fetchone()
            operation_rows = connection.execute(
                "SELECT a.operation, COUNT(*) AS total, COALESCE(SUM(a.is_correct), 0) AS correct FROM attempts a JOIN stages s ON s.id = a.stage_id JOIN trainings t ON t.id = s.training_id WHERE t.status = 'completed' GROUP BY a.operation"
            ).fetchall()
            difficulty_rows = connection.execute(
                "SELECT difficulty, COUNT(*) AS total, COALESCE(SUM(correct_answers), 0) AS correct FROM trainings WHERE status = 'completed' GROUP BY difficulty"
            ).fetchall()
        accuracy = row["correct"] / row["examples"] if row["examples"] else 0.0
        by_operation = {
            item["operation"]: (item["total"], item["correct"]) for item in operation_rows
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
