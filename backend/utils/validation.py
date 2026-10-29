from pathlib import Path
from tempfile import NamedTemporaryFile

from flask import current_app, request

from backend.utils.errors import ApiError


def save_uploaded_file(media_type: str):
    upload = request.files.get("file")
    if upload is None:
        raise ApiError("A file is required in the 'file' form field.", 400, "missing_file")
    if not upload.filename:
        raise ApiError("Choose a file with a filename.", 400, "missing_filename")

    extension = Path(upload.filename).suffix.lower()
    if media_type == "image":
        allowed = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
        max_bytes = min(
            current_app.config["IMAGE_MAX_BYTES"],
            current_app.config["MAX_UPLOAD_BYTES"],
        )
    else:
        allowed = {".mp4": "video/mp4"}
        max_bytes = min(
            current_app.config["VIDEO_MAX_BYTES"],
            current_app.config["MAX_UPLOAD_BYTES"],
        )

    if extension not in allowed:
        raise ApiError(f"Unsupported {media_type} file extension.", 415, "unsupported_format")
    expected_mime = allowed[extension]
    if upload.mimetype != expected_mime:
        raise ApiError("The uploaded MIME type does not match the file extension.", 415, "mime_mismatch")

    temp_path = None
    try:
        with NamedTemporaryFile(prefix="truthlens_", suffix=extension, delete=False) as temporary:
            temp_path = Path(temporary.name)
            total = 0
            while True:
                chunk = upload.stream.read(64 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ApiError(f"File exceeds the {max_bytes // (1024 * 1024)} MB size limit.", 413, "file_too_large")
                temporary.write(chunk)
    except Exception:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise

    if total == 0:
        temp_path.unlink(missing_ok=True)
        raise ApiError("The uploaded file is empty.", 400, "empty_file")
    return temp_path, total, upload.filename, expected_mime
