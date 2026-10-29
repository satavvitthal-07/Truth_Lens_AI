import math
from pathlib import Path

import cv2
from PIL import Image
from flask import current_app

from backend.ai.model_adapter import classify_image
from backend.utils.errors import ApiError


def _validate_video_signature(path: Path) -> None:
    with path.open("rb") as video_file:
        header = video_file.read(12)
    if len(header) < 12 or header[4:8] != b"ftyp":
        raise ApiError("The file does not have a supported MP4 container signature.", 415, "signature_mismatch")


def _read_video_metadata(capture) -> tuple[float, float]:
    fps = capture.get(cv2.CAP_PROP_FPS)
    frame_count = capture.get(cv2.CAP_PROP_FRAME_COUNT)
    raw_width = capture.get(cv2.CAP_PROP_FRAME_WIDTH)
    raw_height = capture.get(cv2.CAP_PROP_FRAME_HEIGHT)
    if (
        not math.isfinite(fps)
        or fps <= 0
        or not math.isfinite(frame_count)
        or frame_count < 1
        or not math.isfinite(raw_width)
        or not math.isfinite(raw_height)
        or raw_width <= 0
        or raw_height <= 0
    ):
        raise ApiError("Video metadata is unreadable or invalid.", 422, "invalid_video_metadata")
    width = int(raw_width)
    height = int(raw_height)
    duration = frame_count / fps
    if duration > current_app.config["VIDEO_MAX_SECONDS"]:
        raise ApiError("Video duration exceeds the 60-second limit.", 413, "video_too_long")
    if max(width, height) > current_app.config["VIDEO_MAX_DIMENSION"]:
        raise ApiError("Video dimensions exceed the supported processing limit.", 413, "video_too_large")
    if frame_count > current_app.config["VIDEO_MAX_DECODE_FRAMES"]:
        raise ApiError("Video contains too many frames for the configured processing limit.", 413, "too_many_frames")
    return fps, frame_count


def validate_video(path: Path) -> None:
    _validate_video_signature(path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ApiError("OpenCV could not open this MP4 video.", 422, "invalid_video")
        _read_video_metadata(capture)
    finally:
        capture.release()


def analyze_video(path: Path) -> dict:
    _validate_video_signature(path)
    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            raise ApiError("OpenCV could not open this MP4 video.", 422, "invalid_video")
        fps, frame_count = _read_video_metadata(capture)

        sample_count = min(
            int(frame_count),
            current_app.config["VIDEO_SAMPLE_COUNT"],
            current_app.config["VIDEO_MAX_FRAMES"],
        )
        frame_indexes = sorted(
            {round(position * (frame_count - 1) / max(sample_count - 1, 1)) for position in range(sample_count)}
        )
        frame_results = []
        for frame_index in frame_indexes:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            success, frame = capture.read()
            if not success or frame is None:
                raise ApiError("The video could not be decoded at a sampled frame.", 422, "video_decode_failed")
            frame_height, frame_width = frame.shape[:2]
            if (
                frame_width <= 0
                or frame_height <= 0
                or max(frame_width, frame_height) > current_app.config["VIDEO_MAX_DIMENSION"]
            ):
                raise ApiError("A decoded video frame exceeds the supported dimensions.", 413, "video_too_large")
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            with Image.fromarray(rgb_frame) as image:
                result = classify_image(image)
            frame_results.append(
                {
                    "index": int(frame_index),
                    "timestamp_seconds": float(frame_index / fps),
                    "prediction": result["prediction"],
                    "score": result["score"],
                    "top_label": result["top_label"],
                }
            )
        scores = [frame["score"] for frame in frame_results]
        mean_score = sum(scores) / len(scores)
        ai_flags = [
            frame["prediction"] == "AI-generated indicators detected"
            for frame in frame_results
        ]
        ai_majority = sum(ai_flags) > len(ai_flags) / 2
        return {
            "prediction": (
                "AI-generated indicators detected in sampled frames"
                if ai_majority
                else "No AI-generated indicators detected in the majority of sampled frames"
            ),
            "score": mean_score,
            "model_id": result["model_id"],
            "model_revision": result["model_revision"],
            "frames": frame_results,
            "status": "completed",
        }
    finally:
        capture.release()
