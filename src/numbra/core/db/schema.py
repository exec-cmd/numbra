SCHEMA = """
CREATE TABLE IF NOT EXISTS trainings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, started_at REAL NOT NULL,
    status TEXT NOT NULL, difficulty TEXT NOT NULL, seed INTEGER NOT NULL,
    operations TEXT NOT NULL, target_seconds REAL NOT NULL, actual_seconds REAL NOT NULL,
    stages INTEGER NOT NULL, total_examples INTEGER NOT NULL, correct_answers INTEGER NOT NULL,
    timeouts INTEGER NOT NULL, average_response REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, training_id INTEGER NOT NULL,
    number INTEGER NOT NULL, kind TEXT NOT NULL, examples INTEGER NOT NULL,
    duration REAL NOT NULL, FOREIGN KEY(training_id) REFERENCES trainings(id)
);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, stage_id INTEGER NOT NULL,
    number INTEGER NOT NULL, expression TEXT NOT NULL, correct_answer TEXT NOT NULL,
    user_answer TEXT, is_correct INTEGER NOT NULL, elapsed REAL NOT NULL,
    timed_out INTEGER NOT NULL, operation TEXT NOT NULL,
    FOREIGN KEY(stage_id) REFERENCES stages(id)
);
"""
