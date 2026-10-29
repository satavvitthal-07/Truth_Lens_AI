import os
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parent
DEFAULT_MAX_UPLOAD_BYTES = 50 * 1024 * 1024

DEFAULT_MODEL_ID = "Organika/sdxl-detector"
DEFAULT_MODEL_REVISION = "b37fede8562cb72b89ec201c0987f96ba21b518a"


class Config:
    SECRET_KEY = os.getenv("TRUTHLENS_SECRET_KEY", "local-development-only")
    DATABASE_PATH = Path(os.getenv("TRUTHLENS_DATABASE", BACKEND_DIR / "truthlens.sqlite3"))
    UPLOAD_DIR = Path(os.getenv("TRUTHLENS_UPLOAD_DIR", BACKEND_DIR / "uploads"))
    MAX_UPLOAD_BYTES = int(os.getenv("TRUTHLENS_MAX_UPLOAD_BYTES", str(DEFAULT_MAX_UPLOAD_BYTES)))
    MAX_CONTENT_LENGTH = MAX_UPLOAD_BYTES + 1024 * 1024
    IMAGE_MAX_BYTES = min(
        int(os.getenv("TRUTHLENS_IMAGE_MAX_BYTES", str(10 * 1024 * 1024))),
        MAX_UPLOAD_BYTES,
    )
    VIDEO_MAX_BYTES = min(
        int(os.getenv("TRUTHLENS_VIDEO_MAX_BYTES", str(50 * 1024 * 1024))),
        MAX_UPLOAD_BYTES,
    )
    IMAGE_MAX_PIXELS = 40_000_000
    IMAGE_MAX_DIMENSION = 12_000
    VIDEO_MAX_SECONDS = 60
    VIDEO_MAX_FRAMES = 8
    VIDEO_MAX_DECODE_FRAMES = 2_000
    VIDEO_SAMPLE_COUNT = 8
    VIDEO_MAX_DIMENSION = 3_840
    MODEL_ID = os.getenv("TRUTHLENS_MODEL_ID", DEFAULT_MODEL_ID).strip()
    MODEL_REVISION = (
        os.getenv("TRUTHLENS_MODEL_REVISION", DEFAULT_MODEL_REVISION).strip() or None
    )
    DEFAULT_MODEL_CONFIGURED = (
        MODEL_ID == DEFAULT_MODEL_ID and MODEL_REVISION == DEFAULT_MODEL_REVISION
    )
    MODEL_VERIFIED = os.getenv(
        "TRUTHLENS_MODEL_VERIFIED", str(DEFAULT_MODEL_CONFIGURED)
    ).strip().lower() == "true"
    AI_LABELS = tuple(
        label.strip()
        for label in os.getenv(
            "TRUTHLENS_AI_LABELS",
            "artificial" if DEFAULT_MODEL_CONFIGURED else "",
        ).split(",")
        if label.strip()
    )
    CORS_ORIGINS = tuple(
        origin.strip()
        for origin in os.getenv(
            "TRUTHLENS_CORS_ORIGINS",
            "http://127.0.0.1:5000,http://localhost:5000,"
            "http://127.0.0.1:5500,http://localhost:5500,"
            "http://127.0.0.1:8000,http://localhost:8000",
        ).split(",")
        if origin.strip()
    )
