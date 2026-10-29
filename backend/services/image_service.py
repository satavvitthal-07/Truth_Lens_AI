import warnings
from pathlib import Path

from PIL import Image, UnidentifiedImageError
from flask import current_app

from backend.ai.model_adapter import classify_image
from backend.utils.errors import ApiError, DetectorUnavailable


def _open_valid_image(path: Path, expected_mime: str) -> Image.Image:
    signatures = {
        "image/jpeg": (b"\xff\xd8\xff",),
        "image/png": (b"\x89PNG\r\n\x1a\n",),
    }
    with path.open("rb") as media_file:
        header = media_file.read(16)
    if not any(header.startswith(signature) for signature in signatures[expected_mime]):
        raise ApiError("The file signature does not match the declared image format.", 415, "signature_mismatch")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(path) as image:
                if image.format not in ("JPEG", "PNG"):
                    raise ApiError("The decoded image format is not supported.", 415, "unsupported_image")
                width, height = image.size
                if (
                    width <= 0
                    or height <= 0
                    or width > current_app.config["IMAGE_MAX_DIMENSION"]
                    or height > current_app.config["IMAGE_MAX_DIMENSION"]
                    or width * height > current_app.config["IMAGE_MAX_PIXELS"]
                ):
                    raise ApiError("Image dimensions exceed the supported processing limits.", 413, "image_too_large")
                image.verify()
            image = Image.open(path)
            image.load()
            return image.convert("RGB")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as error:
        raise ApiError("The image is malformed or cannot be decoded safely.", 422, "invalid_image") from error


def validate_image(path: Path, expected_mime: str) -> None:
    image = _open_valid_image(path, expected_mime)
    image.close()


def analyze_image(path: Path, expected_mime: str) -> dict:
    image = _open_valid_image(path, expected_mime)
    try:
        result = classify_image(image)
        result["status"] = "completed"
        return result
    except DetectorUnavailable:
        raise
    finally:
        image.close()
