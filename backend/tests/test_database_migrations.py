import sqlite3
from pathlib import Path

from backend.app import create_app


def test_additive_migration_preserves_existing_analysis(tmp_path):
    database_path = Path(tmp_path) / "legacy.sqlite3"
    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        CREATE TABLE analyses (
            analysis_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL,
            media_type TEXT NOT NULL,
            file_size INTEGER NOT NULL,
            model_id TEXT,
            model_revision TEXT,
            top_label TEXT,
            scores_json TEXT,
            prediction TEXT NOT NULL,
            score REAL,
            status TEXT NOT NULL,
            processing_ms INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            frames_json TEXT
        )
        """
    )
    connection.execute(
        """
        INSERT INTO analyses (
            analysis_id, display_name, media_type, file_size, model_id,
            model_revision, top_label, scores_json, prediction, score,
            status, processing_ms, created_at, frames_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "existing-analysis",
            "older.png",
            "image",
            512,
            None,
            None,
            None,
            None,
            "Detection unavailable",
            None,
            "unavailable",
            12,
            "2026-10-27T00:00:00+00:00",
            None,
        ),
    )
    connection.commit()
    connection.close()

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": database_path,
            "CORS_ORIGINS": (),
            "MODEL_ID": "",
            "MODEL_REVISION": None,
            "MODEL_VERIFIED": False,
            "AI_LABELS": (),
        }
    )

    response = app.test_client().get("/api/history/existing-analysis")

    assert response.status_code == 200
    result = response.get_json()
    assert result["analysis_id"] == "existing-analysis"
    assert result["prediction"] == "Detection unavailable"
    assert result["error_message"] is None
    assert result["media_url"] is None
    assert result["media_available"] is False

    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(analyses)")
        }
    assert "media_filename" in columns
