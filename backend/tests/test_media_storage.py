import sqlite3
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from backend.app import create_app
from backend.database.repository import create_analysis
from backend.services import image_service, video_service


def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (8, 6), color=(40, 80, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def classify(_image):
    return {
        "prediction": "No AI-generated indicators detected by this model",
        "score": 0.12,
        "model_id": "test/model",
        "model_revision": "test-revision",
        "top_label": "human",
        "scores": [
            {"label": "human", "score": 0.88},
            {"label": "artificial", "score": 0.12},
        ],
    }


def upload_png(client):
    return client.post(
        "/api/detect/image",
        data={"file": (BytesIO(png_bytes()), "original photo.png", "image/png")},
        content_type="multipart/form-data",
    )


def test_image_is_persisted_and_available_after_app_restart(app, client, monkeypatch):
    monkeypatch.setattr(image_service, "classify_image", classify)
    response = upload_png(client)

    assert response.status_code == 200
    result = response.get_json()
    assert result["display_name"] == "original photo.png"
    assert result["media_url"] == f"/media/{result['analysis_id']}"
    assert result["media_available"] is True

    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        filename = connection.execute(
            "SELECT media_filename FROM analyses WHERE analysis_id = ?",
            (result["analysis_id"],),
        ).fetchone()[0]
    assert filename.endswith(".png")
    assert Path(filename).name == filename
    stored_path = app.config["UPLOAD_DIR"] / filename
    assert stored_path.read_bytes() == png_bytes()

    restarted_app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": app.config["DATABASE_PATH"],
            "UPLOAD_DIR": app.config["UPLOAD_DIR"],
            "CORS_ORIGINS": (),
            "MODEL_ID": "",
            "MODEL_REVISION": None,
            "MODEL_VERIFIED": False,
            "AI_LABELS": (),
        }
    )
    restart_client = restarted_app.test_client()
    history = restart_client.get("/api/history").get_json()["analyses"]
    assert history[0]["analysis_id"] == result["analysis_id"]
    assert history[0]["media_available"] is True
    media_response = restart_client.get(f"/api{history[0]['media_url']}")
    assert media_response.status_code == 200
    assert media_response.mimetype == "image/png"
    assert media_response.data == png_bytes()
    assert media_response.headers["Content-Disposition"].startswith("inline;")
    assert media_response.headers["X-Content-Type-Options"] == "nosniff"
    assert media_response.headers["Cache-Control"] == "private, no-store"


def make_mp4(path: Path) -> bytes:
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        5.0,
        (64, 48),
    )
    if not writer.isOpened():
        raise RuntimeError("OpenCV could not create the MP4 test clip.")
    for frame_index in range(5):
        frame = np.full((48, 64, 3), (frame_index * 20, 80, 150), dtype=np.uint8)
        writer.write(frame)
    writer.release()
    return path.read_bytes()


def test_video_is_persisted_and_served_with_range_support(app, client, tmp_path, monkeypatch):
    clip_path = tmp_path / "test-clip.mp4"
    original_bytes = make_mp4(clip_path)
    monkeypatch.setattr(video_service, "classify_image", classify)

    response = client.post(
        "/api/detect/video",
        data={"file": (BytesIO(original_bytes), "sample.mp4", "video/mp4")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    result = response.get_json()
    assert result["media_available"] is True
    assert result["frames"]
    media_response = client.get(
        f"/api{result['media_url']}",
        headers={"Range": "bytes=0-31"},
    )
    assert media_response.status_code == 206
    assert media_response.mimetype == "video/mp4"
    assert media_response.data == original_bytes[:32]
    assert media_response.headers["Content-Range"].startswith("bytes 0-31/")

    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        filename = connection.execute(
            "SELECT media_filename FROM analyses WHERE analysis_id = ?",
            (result["analysis_id"],),
        ).fetchone()[0]
    capture = cv2.VideoCapture(str(app.config["UPLOAD_DIR"] / filename))
    try:
        assert capture.isOpened()
        success, frame = capture.read()
        assert success and frame is not None
    finally:
        capture.release()


def test_invalid_and_oversized_uploads_are_not_stored(app, client):
    invalid = client.post(
        "/api/detect/image",
        data={"file": (BytesIO(b"not an image"), "invalid.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert invalid.status_code == 415
    assert not app.config["UPLOAD_DIR"].exists()

    app.config["MAX_UPLOAD_BYTES"] = len(png_bytes()) - 1
    oversized = client.post(
        "/api/detect/image",
        data={"file": (BytesIO(png_bytes()), "large.png", "image/png")},
        content_type="multipart/form-data",
    )
    assert oversized.status_code == 413
    assert not app.config["UPLOAD_DIR"].exists()

    invalid_video = client.post(
        "/api/detect/video",
        data={"file": (BytesIO(b"not an mp4 container"), "invalid.mp4", "video/mp4")},
        content_type="multipart/form-data",
    )
    assert invalid_video.status_code == 415
    assert not app.config["UPLOAD_DIR"].exists()


def test_missing_media_and_unknown_analysis_are_not_served(app, client, monkeypatch):
    monkeypatch.setattr(image_service, "classify_image", classify)
    result = upload_png(client).get_json()
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        filename = connection.execute(
            "SELECT media_filename FROM analyses WHERE analysis_id = ?",
            (result["analysis_id"],),
        ).fetchone()[0]
    (app.config["UPLOAD_DIR"] / filename).unlink()

    history = client.get(f"/api/history/{result['analysis_id']}").get_json()
    assert history["media_available"] is False
    missing = client.get(f"/api{history['media_url']}")
    assert missing.status_code == 404
    assert missing.get_json()["error"]["code"] == "media_missing"
    assert client.get("/api/media/not-a-valid-analysis").status_code == 404


def test_path_traversal_media_reference_is_rejected(app, client, monkeypatch, tmp_path):
    monkeypatch.setattr(image_service, "classify_image", classify)
    result = upload_png(client).get_json()
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"private")
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        connection.execute(
            "UPDATE analyses SET media_filename = ? WHERE analysis_id = ?",
            ("../secret.png", result["analysis_id"]),
        )
        connection.commit()

    response = client.get(f"/api{result['media_url']}")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "media_unavailable"
    assert outside.read_bytes() == b"private"
    assert client.get(f"/uploads/{outside.name}").status_code == 404


def test_analysis_failure_keeps_metadata_but_does_not_retain_media(
    app, client, monkeypatch
):
    def fail(_path, _mime):
        raise RuntimeError("controlled inference failure")

    monkeypatch.setattr("backend.routes.detection.analyze_image", fail)
    response = upload_png(client)

    assert response.status_code == 500
    result = response.get_json()
    assert result["status"] == "failed"
    assert result["media_url"] is None
    assert result["media_available"] is False
    assert list(app.config["UPLOAD_DIR"].iterdir()) == []
    assert client.get(f"/api/media/{result['analysis_id']}").status_code == 404


def test_deleting_analysis_removes_media_but_preserves_shared_media(
    app, client, monkeypatch
):
    monkeypatch.setattr(image_service, "classify_image", classify)
    result = upload_png(client).get_json()
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        filename = connection.execute(
            "SELECT media_filename FROM analyses WHERE analysis_id = ?",
            (result["analysis_id"],),
        ).fetchone()[0]
    media_path = app.config["UPLOAD_DIR"] / filename

    with app.app_context():
        create_analysis(
            display_name="shared record.png",
            media_type="image",
            file_size=media_path.stat().st_size,
            model_id="test/model",
            model_revision="test-revision",
            top_label="human",
            scores=None,
            prediction="shared test record",
            score=0.1,
            status="completed",
            processing_ms=1,
            media_filename=filename,
        )

    deleted = client.delete(f"/api/history/{result['analysis_id']}")
    assert deleted.status_code == 200
    assert media_path.exists()

    remaining = client.get("/api/history").get_json()["analyses"][0]
    final_delete = client.delete(f"/api/history/{remaining['analysis_id']}")
    assert final_delete.status_code == 200
    assert not media_path.exists()
    assert client.get("/api/history").get_json()["analyses"] == []


def test_deleting_record_with_missing_media_succeeds(app, client, monkeypatch):
    monkeypatch.setattr(image_service, "classify_image", classify)
    result = upload_png(client).get_json()
    with sqlite3.connect(app.config["DATABASE_PATH"]) as connection:
        filename = connection.execute(
            "SELECT media_filename FROM analyses WHERE analysis_id = ?",
            (result["analysis_id"],),
        ).fetchone()[0]
    (app.config["UPLOAD_DIR"] / filename).unlink()

    response = client.delete(f"/api/history/{result['analysis_id']}")
    assert response.status_code == 200
    assert response.get_json()["deleted"] is True
