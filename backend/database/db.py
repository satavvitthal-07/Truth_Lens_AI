import sqlite3
from pathlib import Path

from flask import current_app, g


SCHEMA = """
CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    media_type TEXT NOT NULL CHECK (media_type IN ('image', 'video')),
    file_size INTEGER NOT NULL CHECK (file_size >= 0),
    model_id TEXT,
    model_revision TEXT,
    top_label TEXT,
    scores_json TEXT,
    prediction TEXT NOT NULL,
    score REAL,
    status TEXT NOT NULL CHECK (status IN ('completed', 'unavailable', 'failed')),
    error_message TEXT,
    processing_ms INTEGER NOT NULL CHECK (processing_ms >= 0),
    created_at TEXT NOT NULL,
    frames_json TEXT,
    media_filename TEXT
);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses(created_at DESC);
"""


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        db_path = Path(current_app.config["DATABASE_PATH"])
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        g.db = connection
    return g.db


def close_db(_error=None) -> None:
    connection = g.pop("db", None)
    if connection is not None:
        connection.close()


def init_db(app) -> None:
    database_path = Path(app.config["DATABASE_PATH"])
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(SCHEMA)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(analyses)").fetchall()
        }
        if "model_revision" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN model_revision TEXT")
        if "top_label" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN top_label TEXT")
        if "scores_json" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN scores_json TEXT")
        if "error_message" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN error_message TEXT")
        if "media_filename" not in columns:
            connection.execute("ALTER TABLE analyses ADD COLUMN media_filename TEXT")
        connection.commit()
    finally:
        connection.close()
    app.teardown_appcontext(close_db)
