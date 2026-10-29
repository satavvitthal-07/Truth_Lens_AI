import os
import re
import shutil
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from flask import current_app


_MEDIA_EXTENSIONS = {
    "image": {".jpg", ".jpeg", ".png"},
    "video": {".mp4"},
}
_STORED_FILENAME = re.compile(r"[0-9a-f]{32}\.(?:jpg|jpeg|png|mp4)\Z")


def store_media_file(source: Path, extension: str) -> str:
    if extension not in {".jpg", ".jpeg", ".png", ".mp4"}:
        raise ValueError("Unsupported media extension for permanent storage.")

    upload_dir = Path(current_app.config["UPLOAD_DIR"]).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}{extension}"
    destination = upload_dir / filename
    staging_path: Path | None = None
    try:
        with NamedTemporaryFile(
            prefix=".truthlens-", suffix=".part", dir=upload_dir, delete=False
        ) as staging_file:
            staging_path = Path(staging_file.name)
            with source.open("rb") as source_file:
                shutil.copyfileobj(source_file, staging_file)
            staging_file.flush()
            os.fsync(staging_file.fileno())
        staging_path.replace(destination)
        return filename
    except Exception:
        if staging_path is not None:
            staging_path.unlink(missing_ok=True)
        raise


def resolve_media_path(filename: str, media_type: str, upload_dir: Path) -> Path:
    if (
        not isinstance(filename, str)
        or not _STORED_FILENAME.fullmatch(filename)
        or media_type not in _MEDIA_EXTENSIONS
        or Path(filename).suffix.lower() not in _MEDIA_EXTENSIONS[media_type]
    ):
        raise ValueError("Stored media reference is invalid.")

    root = upload_dir.resolve()
    candidate = root / filename
    if candidate.is_symlink():
        raise ValueError("Stored media reference is invalid.")
    resolved = candidate.resolve(strict=True)
    if resolved.parent != root or not resolved.is_file():
        raise ValueError("Stored media reference is invalid.")
    return resolved


def remove_stored_media(filename: str, media_type: str) -> None:
    path = resolve_media_path(
        filename,
        media_type,
        Path(current_app.config["UPLOAD_DIR"]),
    )
    path.unlink(missing_ok=True)


def public_analysis(analysis: dict) -> dict:
    result = dict(analysis)
    filename = result.pop("media_filename", None)
    result["media_url"] = (
        f"/media/{result['analysis_id']}" if filename else None
    )
    result["media_available"] = False
    if filename:
        try:
            resolve_media_path(
                filename,
                result["media_type"],
                Path(current_app.config["UPLOAD_DIR"]),
            )
        except (FileNotFoundError, OSError, ValueError):
            pass
        else:
            result["media_available"] = True
    return result
