from threading import Lock

from flask import current_app

from backend.utils.errors import DetectorUnavailable


_pipeline = None
_pipeline_lock = Lock()


def _configured_pipeline():
    global _pipeline
    config = current_app.config
    if not config["MODEL_ID"] or not config["MODEL_VERIFIED"] or not config["AI_LABELS"]:
        raise DetectorUnavailable(
            "Image detection is unavailable. Configure a model only after reviewing its task, labels, license, model card and inference interface."
        )
    if _pipeline is None:
        with _pipeline_lock:
            if _pipeline is None:
                try:
                    from transformers import pipeline
                except ImportError as error:
                    raise DetectorUnavailable(
                        "The configured detector needs the optional 'transformers' and 'torch' packages. Install the optional AI dependencies and restart the backend."
                    ) from error
                try:
                    options = {"model": config["MODEL_ID"]}
                    if config["MODEL_REVISION"]:
                        options["revision"] = config["MODEL_REVISION"]
                    _pipeline = pipeline("image-classification", **options)
                except Exception as error:
                    current_app.logger.exception("Could not load configured detector %s", config["MODEL_ID"])
                    raise DetectorUnavailable(
                        f"Could not load the configured model '{config['MODEL_ID']}'. Check backend logs and model configuration."
                    ) from error
    return _pipeline


def detector_status() -> dict:
    config = current_app.config
    configured = bool(config["MODEL_ID"] and config["MODEL_VERIFIED"] and config["AI_LABELS"])
    return {
        "available": configured and _pipeline is not None,
        "configured": configured,
        "model_id": config["MODEL_ID"] if configured else None,
        "revision": config["MODEL_REVISION"] if configured else None,
        "message": (
            None
            if configured and _pipeline is not None
            else (
                "The configured detector has not loaded. Check backend logs and AI dependencies."
                if configured
                else "No verified detector is configured."
            )
        ),
    }


def initialize_detector() -> None:
    config = current_app.config
    if config["MODEL_ID"] and config["MODEL_VERIFIED"] and config["AI_LABELS"]:
        _configured_pipeline()


def classify_image(image) -> dict:
    detector = _configured_pipeline()
    try:
        outputs = detector(image.convert("RGB"), top_k=None)
    except Exception as error:
        current_app.logger.exception(
            "Configured detector failed during inference for model %s",
            current_app.config["MODEL_ID"],
        )
        raise DetectorUnavailable(
            "The configured model failed during inference. Check the backend log for details."
        ) from error

    if not isinstance(outputs, list) or not outputs:
        raise DetectorUnavailable("The model returned no classification scores.")
    normalized = []
    for output in outputs:
        label = output.get("label")
        score = output.get("score")
        if not isinstance(label, str) or not isinstance(score, (int, float)):
            raise DetectorUnavailable("The configured model returned an unsupported output format.")
        if not 0 <= float(score) <= 1:
            raise DetectorUnavailable("The configured model returned an invalid score.")
        normalized.append({"label": label, "score": float(score)})

    ai_labels = set(current_app.config["AI_LABELS"])
    recognized_ai_labels = ai_labels.intersection(item["label"] for item in normalized)
    if not recognized_ai_labels:
        raise DetectorUnavailable(
            "Configured AI labels do not match the model's output labels. Review the model card and exact class labels."
        )

    normalized.sort(key=lambda result: result["score"], reverse=True)
    top_prediction = normalized[0]
    ai_score = sum(item["score"] for item in normalized if item["label"] in ai_labels)
    relevant_scores = normalized[:5]
    included_labels = {item["label"] for item in relevant_scores}
    relevant_scores.extend(
        item
        for item in normalized[5:]
        if item["label"] in ai_labels and item["label"] not in included_labels
    )
    return {
        "prediction": (
            "AI-generated indicators detected"
            if top_prediction["label"] in ai_labels
            else "No AI-generated indicators detected by this model"
        ),
        "score": ai_score,
        "model_id": current_app.config["MODEL_ID"],
        "model_revision": current_app.config["MODEL_REVISION"],
        "top_label": top_prediction["label"],
        "scores": relevant_scores,
    }
