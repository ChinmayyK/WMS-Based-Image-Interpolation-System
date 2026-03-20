"""Tests for adaptive confidence scoring and interpolation guardrails."""
import os

import cv2
import numpy as np
from fastapi.testclient import TestClient

from app.main import app
from app.services.confidence import (
    build_session_confidence_profile,
    gap_minutes_between,
    provenance_label_for,
    recommended_interpolation_frames,
    score_generated_frame,
    score_generated_sequence,
)


def _write_frame(path, color):
    img = np.zeros((64, 64, 3), dtype=np.uint8)
    img[:, :] = color
    cv2.imwrite(path, img)


def test_gap_minutes_and_recommended_frame_caps():
    assert gap_minutes_between("2024-06-01 10:00", "2024-06-01 10:20") == 20
    assert recommended_interpolation_frames(4) == 15
    assert recommended_interpolation_frames(12) == 5
    assert recommended_interpolation_frames(25) == 2
    assert recommended_interpolation_frames(45) == 0


def test_score_generated_frame_uses_session_profile(tmpdir):
    frame0 = os.path.join(tmpdir, "frame0.png")
    frame1 = os.path.join(tmpdir, "frame1.png")
    frame2 = os.path.join(tmpdir, "frame2.png")

    _write_frame(frame0, (20, 80, 120))
    _write_frame(frame1, (24, 84, 124))
    _write_frame(frame2, (28, 88, 128))

    profile = build_session_confidence_profile([
        {"timestamp": "2024-06-01 10:00", "path": frame0},
        {"timestamp": "2024-06-01 10:10", "path": frame1},
        {"timestamp": "2024-06-01 10:20", "path": frame2},
        {"timestamp": "2024-06-01 10:30", "path": frame1},
        {"timestamp": "2024-06-01 10:40", "path": frame2},
    ])
    score = score_generated_frame(frame1, frame0, frame2, 10, profile)

    assert 0.0 <= score["confidence"] <= 1.0
    assert score["confidenceLabel"] in {"HIGH", "MEDIUM", "LOW", "REJECTED"}
    assert "avgSSIM" in score["metrics"]
    assert "sequentialMAD" in score["metrics"]
    assert score["provenanceLabel"] == provenance_label_for(score["confidenceLabel"])


def test_sequence_scoring_applies_domain_caps(tmpdir):
    frame0 = os.path.join(tmpdir, "frame0.png")
    frame1 = os.path.join(tmpdir, "frame1.png")
    frame_mid = os.path.join(tmpdir, "frame_mid.png")

    _write_frame(frame0, (20, 80, 120))
    _write_frame(frame_mid, (24, 84, 124))
    _write_frame(frame1, (28, 88, 128))

    profile = build_session_confidence_profile([
        {"timestamp": "2024-06-01 10:00", "path": frame0},
        {"timestamp": "2024-06-01 10:10", "path": frame_mid},
        {"timestamp": "2024-06-01 10:20", "path": frame1},
        {"timestamp": "2024-06-01 10:30", "path": frame_mid},
        {"timestamp": "2024-06-01 10:40", "path": frame1},
    ])

    scores = score_generated_sequence(
        [{"path": frame_mid, "ratio": 0.5}],
        frame0,
        frame1,
        10,
        profile,
        source_frame0={"path": frame0, "flags": ["TERMINATOR"]},
        source_frame1={"path": frame1, "flags": []},
    )

    assert len(scores) == 1
    assert scores[0]["confidenceLabel"] in {"MEDIUM", "LOW", "REJECTED"}
    assert "TERMINATOR" in scores[0]["metrics"]["domainFlags"]


def test_interpolation_route_blocks_large_gap(monkeypatch):
    fake_catalog = [
        {
            "timestamp": "2024-06-01",
            "isOriginal": True,
            "imageUrl": "/data/raw_frames/a.png",
            "cleanImageUrl": "/data/raw_frames/a.png",
        },
        {
            "timestamp": "2024-06-02",
            "isOriginal": True,
            "imageUrl": "/data/raw_frames/b.png",
            "cleanImageUrl": "/data/raw_frames/b.png",
        },
    ]

    monkeypatch.setattr("app.api.routes.build_frame_catalog", lambda: fake_catalog)
    monkeypatch.setattr("app.api.routes.FRAME_CATALOG", fake_catalog)

    client = TestClient(app)
    response = client.post(
        "/api/frames/interpolate",
        json={"frame1_id": "2024-06-01", "frame2_id": "2024-06-02", "steps": 1},
    )

    assert response.status_code == 422
    assert "gap exceeds 30 minutes" in response.json()["detail"]
