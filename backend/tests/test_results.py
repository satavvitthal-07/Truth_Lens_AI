from io import BytesIO

from PIL import Image

def png_bytes():
    buffer = BytesIO()
    Image.new("RGB", (3, 3), color=(40, 80, 120)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_prediction_response_history_and_delete(app, client, monkeypatch):
    temp_paths = []
    from backend.services import image_service

    original_analyze = image_service.analyze_image

    def track_and_analyze(path, mime):
        temp_paths.append(path)
        return original_analyze(path, mime)

    monkeypatch.setattr(image_service, "classify_image", lambda _image: {
        "prediction": "AI-generated indicators detected",
        "score": 0.81,
        "model_id": "test/model",
        "model_revision": "a1b2c3",
        "top_label": "AI-generated",
        "scores": [{"label": "AI-generated", "score": 0.81}],
    })
    monkeypatch.setattr("backend.routes.detection.analyze_image", track_and_analyze)

    response = client.post(
        "/api/detect/image",
        data={"file": (BytesIO(png_bytes()), "../../sample.png", "image/png")},
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    analysis = response.get_json()
    assert analysis["prediction"] == "AI-generated indicators detected"
    assert analysis["score"] == 0.81
    assert analysis["model_revision"] == "a1b2c3"
    assert analysis["display_name"] == "sample.png"
    assert len(temp_paths) == 1
    assert temp_paths[0].exists()
    assert temp_paths[0].parent == app.config["UPLOAD_DIR"]
    assert analysis["media_available"] is True
    saved_media = client.get(f"/api{analysis['media_url']}")
    assert saved_media.status_code == 200
    assert saved_media.data == png_bytes()
    saved_media.close()

    history = client.get("/api/history").get_json()["analyses"]
    assert len(history) == 1
    assert history[0]["analysis_id"] == analysis["analysis_id"]
    assert history[0]["model_revision"] == "a1b2c3"

    stats = client.get("/api/dashboard/stats").get_json()
    assert stats["total_analyses"] == 1
    assert stats["image_analyses"] == 1
    assert stats["video_analyses"] == 0
    assert stats["result_distribution"] == [{"prediction": "AI-generated indicators detected", "count": 1}]

    deleted = client.delete(f"/api/history/{analysis['analysis_id']}")
    assert deleted.status_code == 200
    assert client.get("/api/history").get_json()["analyses"] == []
