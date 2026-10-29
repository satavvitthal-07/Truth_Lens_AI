from pathlib import Path
from time import perf_counter

from flask import Blueprint, current_app, jsonify

from backend.database.repository import create_analysis
from backend.services.image_service import analyze_image, validate_image
from backend.services.media_storage import (
    public_analysis,
    remove_stored_media,
    resolve_media_path,
    store_media_file,
)
from backend.services.video_service import analyze_video, validate_video
from backend.utils.errors import ApiError, DetectorUnavailable
from backend.utils.security import safe_display_name
from backend.utils.validation import save_uploaded_file

detection = Blueprint("detection", __name__, url_prefix="/api/detect")


def _process(media_type: str):
    started = perf_counter()
    temp_path: Path | None = None
    media_filename: str | None = None
    analysis_saved = False
    try:
        temp_path, file_size, original_name, expected_mime = save_uploaded_file(media_type)
        display_name = safe_display_name(original_name)
        if media_type == "image":
            validate_image(temp_path, expected_mime)
        else:
            validate_video(temp_path)
        media_filename = store_media_file(
            temp_path,
            Path(original_name).suffix.lower(),
        )
        stored_path = resolve_media_path(
            media_filename,
            media_type,
            Path(current_app.config["UPLOAD_DIR"]),
        )
        result = (
            analyze_image(stored_path, expected_mime)
            if media_type == "image"
            else analyze_video(stored_path)
        )
        processing_ms = max(0, round((perf_counter() - started) * 1000))
        record = create_analysis(
            display_name=display_name,
            media_type=media_type,
            file_size=file_size,
            model_id=result["model_id"],
            model_revision=result.get("model_revision"),
            top_label=result.get("top_label"),
            scores=result.get("scores"),
            prediction=result["prediction"],
            score=result["score"],
            status="completed",
            processing_ms=processing_ms,
            frames=result.get("frames"),
            media_filename=media_filename,
        )
        analysis_saved = True
        record.update(
            {
                key: value
                for key, value in result.items()
                if key not in {"prediction", "score", "model_id", "frames", "status", "scores"}
            }
        )
        return jsonify(public_analysis(record)), 200
    except DetectorUnavailable as error:
        processing_ms = max(0, round((perf_counter() - started) * 1000))
        record = create_analysis(
            display_name=safe_display_name(original_name),
            media_type=media_type,
            file_size=file_size,
            model_id=current_app.config["MODEL_ID"] or None,
            model_revision=current_app.config["MODEL_REVISION"],
            top_label=None,
            scores=None,
            prediction="Detection unavailable",
            score=None,
            status="unavailable",
            processing_ms=processing_ms,
            error_message=str(error),
        )
        response = {
            **public_analysis(record),
            "error": {"code": "detector_unavailable", "message": str(error)},
        }
        return jsonify(response), 503
    except ApiError as error:
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code
    except Exception:
        current_app.logger.exception("Unexpected error while processing uploaded %s", media_type)
        if temp_path is not None and "file_size" in locals() and "display_name" in locals():
            processing_ms = max(0, round((perf_counter() - started) * 1000))
            record = create_analysis(
                display_name=display_name,
                media_type=media_type,
                file_size=file_size,
                model_id=None,
                model_revision=None,
                top_label=None,
                scores=None,
                prediction="Analysis failed",
                score=None,
                status="failed",
                processing_ms=processing_ms,
                error_message="Media processing failed unexpectedly. Check the backend log and retry.",
            )
            return jsonify(
                {
                    **public_analysis(record),
                    "error": {
                        "code": "processing_failed",
                        "message": "Media processing failed unexpectedly. Check the backend log and retry.",
                    },
                }
            ), 500
        return jsonify({"error": {"code": "processing_failed", "message": "Media processing failed unexpectedly."}}), 500
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        if media_filename is not None and not analysis_saved:
            try:
                remove_stored_media(media_filename, media_type)
            except FileNotFoundError:
                pass
            except OSError:
                current_app.logger.exception("Could not remove media after unsuccessful analysis")


@detection.post("/image")
def detect_image():
    return _process("image")


@detection.post("/video")
def detect_video():
    return _process("video")
