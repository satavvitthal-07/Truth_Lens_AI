from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, send_file

from backend.database.repository import (
    dashboard_stats,
    delete_analysis,
    get_analysis,
    list_analyses,
)
from backend.services.media_storage import public_analysis, resolve_media_path
from backend.utils.security import safe_display_name

history = Blueprint("history", __name__, url_prefix="/api")


@history.get("/dashboard/stats")
def get_dashboard_stats():
    stats = dashboard_stats()
    stats["recent"] = [public_analysis(analysis) for analysis in stats["recent"]]
    return jsonify(stats)


@history.get("/history")
def get_history():
    try:
        limit = int(request.args.get("limit", "100"))
    except ValueError:
        return jsonify({"error": {"code": "invalid_limit", "message": "Limit must be an integer."}}), 400
    if limit < 1 or limit > 200:
        return jsonify({"error": {"code": "invalid_limit", "message": "Limit must be between 1 and 200."}}), 400
    analyses = [public_analysis(analysis) for analysis in list_analyses(limit)]
    return jsonify({"analyses": analyses})


@history.get("/history/<analysis_id>")
def get_history_item(analysis_id: str):
    analysis = get_analysis(analysis_id)
    if analysis is None:
        return jsonify({"error": {"code": "not_found", "message": "Analysis record was not found."}}), 404
    return jsonify(public_analysis(analysis))


@history.get("/media/<analysis_id>")
def get_analysis_media(analysis_id: str):
    analysis = get_analysis(analysis_id)
    if analysis is None:
        return jsonify({"error": {"code": "not_found", "message": "Analysis record was not found."}}), 404
    filename = analysis.get("media_filename")
    if not filename:
        return jsonify({"error": {"code": "media_unavailable", "message": "This analysis has no retained media."}}), 404

    try:
        media_path = resolve_media_path(
            filename,
            analysis["media_type"],
            Path(current_app.config["UPLOAD_DIR"]),
        )
    except FileNotFoundError:
        return jsonify({"error": {"code": "media_missing", "message": "The stored media file is missing."}}), 404
    except (OSError, ValueError):
        current_app.logger.warning("Rejected invalid stored media reference for analysis %s", analysis_id)
        return jsonify({"error": {"code": "media_unavailable", "message": "Stored media is unavailable."}}), 404

    mimetype = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".mp4": "video/mp4",
    }[media_path.suffix.lower()]
    response = send_file(
        media_path,
        mimetype=mimetype,
        as_attachment=False,
        download_name=safe_display_name(analysis["display_name"]),
        conditional=True,
        etag=False,
        max_age=0,
    )
    response.headers["Cache-Control"] = "private, no-store"
    return response


@history.delete("/history/<analysis_id>")
def delete_history_item(analysis_id: str):
    try:
        deleted = delete_analysis(analysis_id)
    except OSError:
        current_app.logger.exception("Could not delete analysis media; the file may be in use")
        return jsonify(
            {
                "error": {
                    "code": "media_delete_failed",
                    "message": "The stored media could not be removed. Close any open preview and retry.",
                }
            }
        ), 503
    if not deleted:
        return jsonify({"error": {"code": "not_found", "message": "Analysis record was not found."}}), 404
    return jsonify({"deleted": True, "analysis_id": analysis_id})
