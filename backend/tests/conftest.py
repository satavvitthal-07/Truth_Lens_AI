import pytest

from backend.app import create_app


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": tmp_path / "test.sqlite3",
            "UPLOAD_DIR": tmp_path / "uploads",
            "CORS_ORIGINS": ("http://127.0.0.1:5500",),
            "MODEL_ID": "",
            "MODEL_REVISION": None,
            "MODEL_VERIFIED": False,
            "AI_LABELS": (),
            "IMAGE_MAX_BYTES": 10 * 1024 * 1024,
            "MAX_UPLOAD_BYTES": 50 * 1024 * 1024,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()
