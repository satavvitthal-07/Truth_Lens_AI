from pathlib import Path

from flask import Flask, jsonify, request

from backend.ai.model_adapter import initialize_detector
from backend.config import Config
from backend.database.db import init_db
from backend.routes.detection import detection
from backend.routes.health import health
from backend.routes.history import history
from backend.utils.errors import ApiError, DetectorUnavailable


def create_app(test_config: dict | None = None) -> Flask:
    frontend_dir = Path(__file__).resolve().parent.parent / "frontend"
    app = Flask(__name__, static_folder=str(frontend_dir), static_url_path="")
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    app.config["MAX_CONTENT_LENGTH"] = app.config["MAX_UPLOAD_BYTES"] + 1024 * 1024
    init_db(app)

    if not app.config.get("TESTING"):
        with app.app_context():
            try:
                initialize_detector()
            except DetectorUnavailable as error:
                app.logger.error("Configured detector failed to load during startup: %s", error)

    app.register_blueprint(health)
    app.register_blueprint(detection)
    app.register_blueprint(history)

    @app.get("/")
    def frontend_index():
        return app.send_static_file("index.html")

    @app.before_request
    def reject_untrusted_origins():
        origin = request.headers.get("Origin")
        if origin and origin not in app.config["CORS_ORIGINS"]:
            return jsonify({"error": {"code": "origin_not_allowed", "message": "This browser origin is not allowed."}}), 403

    @app.after_request
    def set_cors_headers(response):
        origin = request.headers.get("Origin")
        if origin and origin in app.config["CORS_ORIGINS"]:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": {"code": "request_too_large", "message": "Request exceeds the configured upload limit."}}), 413

    @app.errorhandler(ApiError)
    def handle_api_error(error: ApiError):
        return jsonify({"error": {"code": error.code, "message": error.message}}), error.status_code

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": {"code": "not_found", "message": "API endpoint was not found."}}), 404

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
