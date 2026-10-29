import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flask import current_app

from backend.database.db import get_db
from backend.services.media_storage import resolve_media_path


logger = logging.getLogger(__name__)


def create_analysis(
    *,
    display_name: str,
    media_type: str,
    file_size: int,
    model_id: str | None,
    model_revision: str | None,
    top_label: str | None,
    scores: list[dict] | None,
    prediction: str,
    score: float | None,
    status: str,
    processing_ms: int,
    frames: list[dict] | None = None,
    error_message: str | None = None,
    media_filename: str | None = None,
) -> dict:
    analysis = {
        "analysis_id": str(uuid4()),
        "display_name": display_name,
        "media_type": media_type,
        "file_size": file_size,
        "model_id": model_id,
        "prediction": prediction,
        "score": score,
        "status": status,
        "error_message": error_message,
        "processing_ms": processing_ms,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frames": frames,
        "media_filename": media_filename,
    }
    db = get_db()
    db.execute(
        """
        INSERT INTO analyses (
            analysis_id, display_name, media_type, file_size, model_id, model_revision,
            top_label, scores_json,
            prediction, score, status, error_message, processing_ms, created_at, frames_json,
            media_filename
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            analysis["analysis_id"],
            analysis["display_name"],
            analysis["media_type"],
            analysis["file_size"],
            analysis["model_id"],
            model_revision,
            top_label,
            json.dumps(scores) if scores is not None else None,
            analysis["prediction"],
            analysis["score"],
            analysis["status"],
            analysis["error_message"],
            analysis["processing_ms"],
            analysis["created_at"],
            json.dumps(frames) if frames is not None else None,
            media_filename,
        ),
    )
    db.commit()
    analysis["model_revision"] = model_revision
    analysis["top_label"] = top_label
    analysis["scores"] = scores
    return analysis


def _row_to_analysis(row: sqlite3.Row) -> dict:
    result = dict(row)
    result["frames"] = json.loads(result.pop("frames_json")) if result.get("frames_json") else None
    result["scores"] = json.loads(result.pop("scores_json")) if result.get("scores_json") else None
    return result


def list_analyses(limit: int = 100) -> list[dict]:
    rows = get_db().execute(
        "SELECT * FROM analyses ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [_row_to_analysis(row) for row in rows]


def get_analysis(analysis_id: str) -> dict | None:
    row = get_db().execute(
        "SELECT * FROM analyses WHERE analysis_id = ?", (analysis_id,)
    ).fetchone()
    return _row_to_analysis(row) if row else None


def delete_analysis(analysis_id: str) -> bool:
    db = get_db()
    tombstone: Path | None = None
    original_path: Path | None = None
    db.execute("BEGIN IMMEDIATE")
    try:
        row = db.execute(
            "SELECT media_filename, media_type FROM analyses WHERE analysis_id = ?",
            (analysis_id,),
        ).fetchone()
        if row is None:
            db.rollback()
            return False

        filename = row["media_filename"]
        if filename:
            reference = db.execute(
                "SELECT COUNT(*) FROM analyses WHERE media_filename = ?",
                (filename,),
            ).fetchone()[0]
            if reference == 1:
                try:
                    original_path = resolve_media_path(
                        filename,
                        row["media_type"],
                        Path(current_app.config["UPLOAD_DIR"]),
                    )
                except (FileNotFoundError, ValueError):
                    original_path = None
                if original_path is not None:
                    tombstone = original_path.with_name(f".{uuid4().hex}.deleting")
                    original_path.replace(tombstone)

        db.execute("DELETE FROM analyses WHERE analysis_id = ?", (analysis_id,))
        db.commit()
    except Exception:
        db.rollback()
        if tombstone is not None and original_path is not None and tombstone.exists():
            try:
                tombstone.replace(original_path)
            except OSError:
                logger.exception("Could not restore media after analysis deletion failed")
        raise

    if tombstone is not None:
        try:
            tombstone.unlink(missing_ok=True)
        except OSError:
            logger.exception("Analysis was deleted but its media cleanup failed")
    return True


def dashboard_stats() -> dict:
    db = get_db()
    counts = db.execute(
        """
        SELECT COUNT(*) AS total,
               SUM(CASE WHEN media_type = 'image' THEN 1 ELSE 0 END) AS images,
               SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) AS videos
        FROM analyses
        """
    ).fetchone()
    recent = list_analyses(limit=8)
    distribution_rows = db.execute(
        """
        SELECT prediction, COUNT(*) AS count
        FROM analyses
        WHERE status = 'completed'
          AND datetime(created_at) >= datetime('now', '-30 days')
        GROUP BY prediction
        ORDER BY count DESC
        """
    ).fetchall()
    return {
        "total_analyses": counts["total"] or 0,
        "image_analyses": counts["images"] or 0,
        "video_analyses": counts["videos"] or 0,
        "recent": recent,
        "result_distribution": [
            {"prediction": row["prediction"], "count": row["count"]}
            for row in distribution_rows
        ],
    }
