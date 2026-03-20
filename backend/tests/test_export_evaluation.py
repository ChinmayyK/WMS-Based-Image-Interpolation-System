"""Tests for FFmpeg export and evaluation reporting."""
import os

import cv2
import numpy as np


def _write_frame(path, color):
    img = np.zeros((96, 128, 3), dtype=np.uint8)
    img[:, :] = color
    cv2.imwrite(path, img)


def test_export_video_sequence_generates_outputs(tmpdir, monkeypatch):
    from app.services import video_export

    data_dir = os.path.join(tmpdir, "data")
    frames_dir = os.path.join(data_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)

    frame0 = os.path.join(frames_dir, "frame0.png")
    frame1 = os.path.join(frames_dir, "frame1.png")
    _write_frame(frame0, (40, 80, 120))
    _write_frame(frame1, (70, 110, 150))

    monkeypatch.setattr(video_export, "DATA_DIR", data_dir)
    monkeypatch.setattr(video_export, "EXPORTS_DIR", os.path.join(data_dir, "exports"))
    monkeypatch.setattr(video_export, "LATEST_EXPORT_SUMMARY_PATH", os.path.join(data_dir, "exports", "latest_export.json"))

    result = video_export.export_video_sequence(
        [
            {
                "timestamp": "2024-06-01 10:00",
                "imageUrl": "/data/frames/frame0.png",
                "isOriginal": True,
                "confidence": 1.0,
                "confidenceLabel": "OBSERVED",
            },
            {
                "timestamp": "2024-06-01 10:10",
                "imageUrl": "/data/frames/frame1.png",
                "isOriginal": False,
                "confidence": 0.88,
                "confidenceLabel": "HIGH",
            },
        ],
        fps=12,
        job_name="test_export",
    )

    mp4_path = os.path.join(data_dir, result["mp4Url"].replace("/data/", "", 1))
    webm_path = os.path.join(data_dir, result["webmUrl"].replace("/data/", "", 1))
    metadata_path = os.path.join(data_dir, result["metadataUrl"].replace("/data/", "", 1))

    assert os.path.exists(mp4_path)
    assert os.path.exists(webm_path)
    assert os.path.exists(metadata_path)


def test_run_evaluation_suite_writes_json(tmpdir, monkeypatch):
    from app.services import evaluation

    data_dir = os.path.join(tmpdir, "data")
    monkeypatch.setattr(evaluation, "DATA_DIR", data_dir)
    monkeypatch.setattr(evaluation, "EVALUATIONS_DIR", os.path.join(data_dir, "evaluations"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_PATH", os.path.join(data_dir, "evaluations", "latest_evaluation.json"))

    report = evaluation.run_evaluation_suite()

    assert report["datasetCount"] >= 1
    assert "psnr" in report["averages"]
    assert "ssim" in report["averages"]
    assert os.path.exists(evaluation.LATEST_EVALUATION_PATH)
