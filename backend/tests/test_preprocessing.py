"""Tests for PRD v2.0 preprocessing validation and masking."""
import os

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.preprocessing import (
    _detect_calibration_shifts,
    _detect_limb_mask,
    _detect_terminator_mask,
    _build_timeline_report,
    detect_nodata_mask,
    preprocess_observed_session,
)


def _write_rgba_frame(path, width=64, height=64, offset=0):
    x_gradient = np.tile(np.linspace(3 + offset, 11 + offset, width, dtype=np.uint8), (height, 1))
    img = np.dstack([x_gradient, x_gradient, x_gradient, np.full((height, width), 255, dtype=np.uint8)])
    cv2.imwrite(path, img)


def test_detect_nodata_mask_uses_alpha_and_border_connected_black():
    image = np.zeros((32, 32, 4), dtype=np.uint8)
    image[:, :, :3] = 4
    image[:, :, 3] = 255

    image[:8, :8, :3] = 0
    image[12:16, 12:16, :3] = 0
    image[20:24, 20:24, 3] = 0

    mask = detect_nodata_mask(image)

    assert mask[:8, :8].all()
    assert not mask[12:16, 12:16].any()
    assert mask[20:24, 20:24].all()
    assert not mask[8:12, 8:12].any()


def test_timeline_report_marks_missing_native_cadence_frames():
    report = _build_timeline_report(
        [
            "2026-03-20 10:00",
            "2026-03-20 10:10",
            "2026-03-20 10:30",
        ]
    )

    assert report["timestamps"] == [
        "2026-03-20 10:00",
        "2026-03-20 10:10",
        "2026-03-20 10:30",
    ]
    assert report["missing"] == ["2026-03-20 10:20"]
    assert report["interval_stats"]["sorted"] is True
    assert report["interval_stats"]["evenly_spaced"] is False
    assert report["interval_stats"]["expected_interval_minutes"] == 10.0


def test_limb_detection_marks_earth_disk_boundary():
    image = np.zeros((128, 128, 4), dtype=np.uint8)
    cv2.circle(image, (64, 64), 48, (90, 90, 90, 255), thickness=-1)

    nodata_mask = detect_nodata_mask(image)
    limb_mask, detected, ratio = _detect_limb_mask(image, nodata_mask)

    assert detected is True
    assert ratio > 0.1
    assert limb_mask[0, 0]
    assert not limb_mask[64, 64]


def test_terminator_detection_flags_sharp_day_night_transition():
    image = np.zeros((128, 128, 4), dtype=np.uint8)
    image[:, :, 3] = 255

    for col in range(128):
        if col < 52:
            value = 215
        elif col > 76:
            value = 20
        else:
            value = int(np.interp(col, [52, 76], [215, 20]))
        image[:, col, :3] = value

    nodata_mask = np.zeros((128, 128), dtype=bool)
    limb_mask = np.zeros((128, 128), dtype=bool)

    terminator_mask, detected, ratio = _detect_terminator_mask(image, nodata_mask, limb_mask)

    assert detected is True
    assert ratio >= 0.04
    assert terminator_mask[:, 52:76].any()


def test_calibration_shift_detection_flags_histogram_jump():
    def frame(timestamp, value):
        rgba = np.full((64, 64, 4), value, dtype=np.uint8)
        rgba[:, :, 3] = 255
        return {
            "timestamp": timestamp,
            "rgba": rgba,
            "nodataMask": np.zeros((64, 64), dtype=bool),
            "limbMask": np.zeros((64, 64), dtype=bool),
        }

    frames = [
        frame("2026-03-20 10:00", 30),
        frame("2026-03-20 10:10", 31),
        frame("2026-03-20 10:20", 32),
        frame("2026-03-20 10:30", 33),
        frame("2026-03-20 10:40", 180),
    ]

    issues = _detect_calibration_shifts(frames)

    assert len(issues) == 1
    assert issues[0]["issue"] == "CALIBRATION_SHIFT"
    assert issues[0]["to"] == "2026-03-20 10:40"


def test_preprocess_observed_session_rejects_dimension_mismatch_and_normalizes_valid_frames(tmpdir, monkeypatch):
    import app.services.preprocessing as preprocessing

    preprocessed_dir = os.path.join(tmpdir, "preprocessed")
    nodata_dir = os.path.join(tmpdir, "nodata")
    limb_dir = os.path.join(tmpdir, "limb")
    terminator_dir = os.path.join(tmpdir, "terminator")
    report_path = os.path.join(tmpdir, "preprocessing_report.json")

    monkeypatch.setattr(preprocessing, "PREPROCESSED_FRAMES_DIR", preprocessed_dir)
    monkeypatch.setattr(preprocessing, "NODATA_MASKS_DIR", nodata_dir)
    monkeypatch.setattr(preprocessing, "LIMB_MASKS_DIR", limb_dir)
    monkeypatch.setattr(preprocessing, "TERMINATOR_MASKS_DIR", terminator_dir)
    monkeypatch.setattr(preprocessing, "PREPROCESSING_REPORT_PATH", report_path)

    frame0 = os.path.join(tmpdir, "frame0.png")
    frame1 = os.path.join(tmpdir, "frame1.png")
    frame2 = os.path.join(tmpdir, "frame2.png")
    _write_rgba_frame(frame0, width=64, height=64, offset=0)
    _write_rgba_frame(frame1, width=64, height=64, offset=1)
    _write_rgba_frame(frame2, width=48, height=64, offset=2)

    session = {
        "session_id": "test-session",
        "createdAt": "2026-03-20T10:00:00Z",
        "source": "GOES-East ABI",
        "layer": "GOES-East_ABI_Band2_Red_Visible_1km",
        "bbox": [-10.0, -5.0, 10.0, 5.0],
        "crs": "EPSG:3857",
        "frames": [
            {"timestamp": "2026-03-20 10:00", "path": frame0, "filename": "frame0.png", "bbox": [-10.0, -5.0, 10.0, 5.0], "crs": "EPSG:3857"},
            {"timestamp": "2026-03-20 10:10", "path": frame1, "filename": "frame1.png", "bbox": [-10.0, -5.0, 10.0, 5.0], "crs": "EPSG:3857"},
            {"timestamp": "2026-03-20 10:20", "path": frame2, "filename": "frame2.png", "bbox": [-10.0, -5.0, 10.0, 5.0], "crs": "EPSG:3857"},
        ],
    }

    processed = preprocess_observed_session(session)

    assert processed["preprocessing"]["validFrameCount"] == 2
    assert processed["preprocessing"]["missingFrameCount"] == 0
    assert processed["preprocessing"]["flaggedFrameCount"] == 0

    valid_frames = [frame for frame in processed["frames"] if frame["validation"]["valid"]]
    invalid_frames = [frame for frame in processed["frames"] if not frame["validation"]["valid"]]

    assert len(valid_frames) == 2
    assert len(invalid_frames) == 1
    assert invalid_frames[0]["validation"]["issues"] == ["DIMENSION_MISMATCH"]
    assert all(frame["nodataRatio"] == 0.0 for frame in valid_frames)
    assert all(os.path.exists(frame["normalizedPath"]) for frame in valid_frames)
    assert all(os.path.exists(frame["nodataMaskPath"]) for frame in processed["frames"])
    assert os.path.exists(report_path)


def test_preprocessing_report_route_returns_report(monkeypatch):
    fake_session = {
        "session_id": "session-123",
        "source": "GOES-East ABI",
        "layer": "GOES-East_ABI_Band2_Red_Visible_1km",
        "title": "Synthetic GOES session",
        "bbox": [-10.0, -5.0, 10.0, 5.0],
        "extent3857": [-10.0, -5.0, 10.0, 5.0],
        "crs": "EPSG:3857",
        "wmsUrl": "https://example.test/wms",
        "requestedStartTime": "2026-03-20T10:00:00Z",
        "requestedEndTime": "2026-03-20T10:30:00Z",
        "availableStartTime": "2026-03-20T10:00:00Z",
        "availableEndTime": "2026-03-20T10:30:00Z",
        "availableFrameCount": 3,
        "downloadedFrameCount": 3,
        "failedTimestamps": [],
        "cadenceMinutes": {"minGapMinutes": 10.0, "medianGapMinutes": 10.0, "maxGapMinutes": 10.0},
        "validation": {"continuousFrames": True},
        "preprocessing": {
            "version": "2.0",
            "reportUrl": "/data/metadata/preprocessing_report.json",
            "validFrameCount": 2,
            "missingFrameCount": 1,
            "calibrationIssueCount": 0,
            "flaggedFrameCount": 1,
        },
    }
    fake_report = {
        "total_frames": 3,
        "valid_frames": 2,
        "missing_frames": 1,
        "missing_timestamps": ["2026-03-20 10:20"],
        "nodata_ratio": 0.0123,
        "limb_detected": True,
        "terminator_detected": False,
        "calibration_issues": [],
    }

    monkeypatch.setattr("app.api.routes._load_session", lambda: fake_session)
    monkeypatch.setattr("app.api.routes.load_preprocessing_report", lambda: fake_report)

    client = TestClient(app)
    response = client.get("/api/preprocessing/report")

    assert response.status_code == 200
    payload = response.json()
    assert payload["report"]["missing_timestamps"] == ["2026-03-20 10:20"]
    assert payload["session"]["preprocessing"]["flaggedFrameCount"] == 1


def test_interpolation_route_blocks_invalid_observed_frames(monkeypatch):
    fake_catalog = [
        {
            "timestamp": "2026-03-20 10:00",
            "isOriginal": True,
            "isValid": False,
            "imageUrl": "/data/raw_frames/a.png",
            "cleanImageUrl": "/data/raw_frames/a.png",
        },
        {
            "timestamp": "2026-03-20 10:10",
            "isOriginal": True,
            "isValid": True,
            "imageUrl": "/data/raw_frames/b.png",
            "cleanImageUrl": "/data/raw_frames/b.png",
        },
    ]

    monkeypatch.setattr("app.api.routes.build_frame_catalog", lambda: fake_catalog)
    monkeypatch.setattr("app.api.routes.FRAME_CATALOG", fake_catalog)

    client = TestClient(app)
    response = client.post(
        "/api/frames/interpolate",
        json={"frame1_id": "2026-03-20 10:00", "frame2_id": "2026-03-20 10:10", "steps": 1},
    )

    assert response.status_code == 422
    assert "preprocessing-valid" in response.json()["detail"]
