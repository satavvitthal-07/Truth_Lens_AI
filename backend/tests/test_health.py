from pathlib import Path

from backend.app import create_app


def test_health_reports_backend_and_detector_status(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["detector"]["configured"] is False
    assert body["detector"]["available"] is False


def test_root_serves_frontend_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.mimetype == "text/html"
    assert b"TruthLens AI" in response.data


def test_frontend_assets_and_api_remain_available(client):
    css_response = client.get("/css/base.css")
    js_response = client.get("/js/app.js")
    api_response = client.get("/api/health")

    assert css_response.status_code == 200
    assert css_response.mimetype == "text/css"
    assert js_response.status_code == 200
    assert js_response.mimetype == "text/javascript"
    assert api_response.status_code == 200


def test_backend_origin_can_load_frontend_module_scripts(tmp_path):
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": Path(tmp_path) / "same-origin.sqlite3",
        }
    )

    response = app.test_client().get(
        "/js/upload.js",
        headers={"Origin": "http://127.0.0.1:5000"},
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:5000"


def test_configured_detector_is_loaded_during_application_startup(monkeypatch, tmp_path):
    initialized = []
    monkeypatch.setattr("backend.app.initialize_detector", lambda: initialized.append(True))

    create_app(
        {
            "DATABASE_PATH": Path(tmp_path) / "startup.sqlite3",
            "MODEL_ID": "Organika/sdxl-detector",
            "MODEL_REVISION": "b37fede8562cb72b89ec201c0987f96ba21b518a",
            "MODEL_VERIFIED": True,
            "AI_LABELS": ("artificial",),
        }
    )

    assert initialized == [True]


def test_detector_startup_failure_keeps_api_available_and_reports_status(
    monkeypatch, tmp_path, caplog
):
    from backend.utils.errors import DetectorUnavailable

    def fail_initialization():
        raise DetectorUnavailable("Optional model packages are unavailable.")

    monkeypatch.setattr("backend.app.initialize_detector", fail_initialization)
    app = create_app(
        {
            "DATABASE_PATH": Path(tmp_path) / "failed-startup.sqlite3",
            "MODEL_ID": "Organika/sdxl-detector",
            "MODEL_REVISION": "b37fede8562cb72b89ec201c0987f96ba21b518a",
            "MODEL_VERIFIED": True,
            "AI_LABELS": ("artificial",),
        }
    )

    response = app.test_client().get("/api/health")
    detector = response.get_json()["detector"]

    assert response.status_code == 200
    assert detector["configured"] is True
    assert detector["available"] is False
    assert "has not loaded" in detector["message"]
    assert "failed to load during startup" in caplog.text
