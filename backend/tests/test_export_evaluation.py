"""Tests for FFmpeg export and evaluation reporting."""
import os
import json

import cv2
import numpy as np
from fastapi.testclient import TestClient


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
    monkeypatch.setattr(video_export, "_resolve_ffmpeg_executable", lambda: "ffmpeg")
    monkeypatch.setattr(video_export, "_generate_hls", lambda _ffmpeg_exe, _source, hls_dir: open(os.path.join(hls_dir, "stream.m3u8"), "w", encoding="utf-8").write("#EXTM3U\n"))

    def fake_run_ffmpeg(_ffmpeg_exe, _input_pattern, _fps, output_path, *, codec_args, metadata):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as handle:
            handle.write(b"fake-video")

    monkeypatch.setattr(video_export, "_run_ffmpeg", fake_run_ffmpeg)

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

    mp4_path = os.path.join(data_dir, result["outputs"]["interpolated_mp4"].replace("/data/", "", 1))
    webm_path = os.path.join(data_dir, result["outputs"]["interpolated_webm"].replace("/data/", "", 1))
    metadata_path = os.path.join(data_dir, result["outputs"]["metadata"].replace("/data/", "", 1))

    assert os.path.exists(mp4_path)
    assert os.path.exists(webm_path)
    assert os.path.exists(metadata_path)
    payload = json.loads(open(metadata_path, "r", encoding="utf-8").read())
    assert payload["frames"][0]["frame_index"] == 0
    assert payload["frames"][0]["is_observed"] is True
    assert payload["frames"][1]["is_observed"] is False


def test_run_evaluation_suite_writes_json(tmpdir, monkeypatch):
    from app.services import evaluation

    data_dir = os.path.join(tmpdir, "data")
    monkeypatch.setattr(evaluation, "DATA_DIR", data_dir)
    monkeypatch.setattr(evaluation, "EVALUATION_SETS_DIR", os.path.join(data_dir, "evaluation_sets"))
    monkeypatch.setattr(evaluation, "EVALUATIONS_DIR", os.path.join(data_dir, "evaluations"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_PATH", os.path.join(data_dir, "evaluations", "latest_evaluation.json"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_HTML_PATH", os.path.join(data_dir, "evaluations", "latest_evaluation.html"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_ASSETS_DIR", os.path.join(data_dir, "evaluations", "latest_assets"))
    monkeypatch.setattr(evaluation, "_masked_lpips", lambda *_args, **_kwargs: 0.05)

    report = evaluation.run_evaluation_suite()

    assert report["datasetCount"] >= 5
    assert report["sampleCount"] >= 50
    assert "psnr" in report["averages"]
    assert "ssim" in report["averages"]
    assert "tof" in report["averages"]
    assert "psnr" in report["baselineAverages"]
    assert "confidence_accuracy" in report["confidenceValidation"]
    assert report["qualificationGate"]["checks"]["sampleCount"] is True
    assert report["thresholds"]["psnr"] == 28.0
    assert report["thresholds"]["ssim"] == 0.80
    assert all(result["baseline"] == "optical_flow" for result in report["results"])
    assert all(len(result["inputFrames"]) == 2 for result in report["results"])
    assert os.path.exists(evaluation.LATEST_EVALUATION_PATH)
    assert os.path.exists(evaluation.LATEST_EVALUATION_HTML_PATH)
    assert os.path.isdir(evaluation.EVALUATION_SETS_DIR)


def test_job_evaluation_api_returns_metrics(tmpdir, monkeypatch):
    from app.main import app
    from app.services import evaluation

    data_dir = os.path.join(tmpdir, "data")
    monkeypatch.setattr(evaluation, "DATA_DIR", data_dir)
    monkeypatch.setattr(evaluation, "EVALUATION_SETS_DIR", os.path.join(data_dir, "evaluation_sets"))
    monkeypatch.setattr(evaluation, "EVALUATIONS_DIR", os.path.join(data_dir, "evaluations"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_PATH", os.path.join(data_dir, "evaluations", "latest_evaluation.json"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_HTML_PATH", os.path.join(data_dir, "evaluations", "latest_evaluation.html"))
    monkeypatch.setattr(evaluation, "LATEST_EVALUATION_ASSETS_DIR", os.path.join(data_dir, "evaluations", "latest_assets"))
    monkeypatch.setattr(evaluation, "_masked_lpips", lambda *_args, **_kwargs: 0.05)

    report = evaluation.run_evaluation_suite()
    job_id = report["results"][0]["jobId"]

    client = TestClient(app)
    response = client.get(f"/api/v1/jobs/{job_id}/evaluation")

    assert response.status_code == 200
    payload = response.json()
    assert payload["evaluation"]["jobId"] == job_id
    assert "psnr" in payload["evaluation"]["metrics"]
    assert "ssim" in payload["evaluation"]["metrics"]
    assert payload["summary"]["thresholds"]["psnr"] == 28.0

    report_response = client.get(f"/api/v1/evaluation/{job_id}/report")
    assert report_response.status_code == 200
    report_payload = report_response.json()
    assert report_payload["evaluation"]["jobId"] == job_id
    assert "distributions" in report_payload["report"]
    assert "confidenceCalibration" in report_payload["report"]
