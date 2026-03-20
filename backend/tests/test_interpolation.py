"""Tests for the governed interpolation engine."""
import os

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def test_frames(tmpdir):
    """Create two synthetic test frames."""
    f1 = os.path.join(tmpdir, "frame1.png")
    f2 = os.path.join(tmpdir, "frame2.png")

    img1 = np.zeros((128, 128, 3), dtype=np.uint8)
    img1[:, :] = (255, 0, 0)
    cv2.circle(img1, (32, 64), 20, (255, 255, 255), -1)

    img2 = np.zeros((128, 128, 3), dtype=np.uint8)
    img2[:, :] = (0, 0, 255)
    cv2.circle(img2, (96, 64), 20, (255, 255, 255), -1)

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)

    return f1, f2, str(tmpdir)


def test_interpolator_rejects_missing_weights_without_silent_fallback(test_frames):
    from app.services.interpolation import InterpolationGovernanceError, RIFEInterpolator

    interp = RIFEInterpolator(weights_dir="/nonexistent/path", expected_sha256="deadbeef")
    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "blocked.png")

    assert interp.model_loaded is False
    assert interp.startup_validated is False
    with pytest.raises(InterpolationGovernanceError):
        interp.interpolate(f1, f2, out, ratio=0.5)


def test_interpolator_flags_hash_mismatch_before_model_load(tmpdir):
    from app.services.interpolation import RIFEInterpolator

    weights_dir = os.path.join(tmpdir, "weights")
    os.makedirs(weights_dir, exist_ok=True)
    with open(os.path.join(weights_dir, "flownet.pkl"), "wb") as handle:
        handle.write(b"tampered-weights")

    interp = RIFEInterpolator(weights_dir=weights_dir, expected_sha256="not-the-real-hash")

    assert interp.startup_validated is False
    assert interp.model_loaded is False
    assert "integrity check failed" in (interp.load_error or "").lower()


def test_interpolate_creates_output_and_runtime_metadata(test_frames):
    from app.services.interpolation import interpolator

    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "output.png")
    result = interpolator.interpolate(f1, f2, out, ratio=0.5)

    assert result is True
    assert os.path.exists(out)

    img = cv2.imread(out, cv2.IMREAD_UNCHANGED)
    assert img is not None
    assert img.shape[:2] == (128, 128)
    assert img.dtype == np.uint8

    run = interpolator.last_run
    assert run["executionMode"] == "rife"
    assert run["fallbackUsed"] is False
    assert run["model"]["integrityVerified"] is True
    assert os.path.exists(run["outputMasks"]["nodata"]["path"])
    assert os.path.exists(run["outputMasks"]["limb"]["path"])
    assert os.path.exists(run["outputMasks"]["terminator"]["path"])


def test_runtime_fallback_uses_optical_flow(monkeypatch, test_frames):
    from app.services.interpolation import FALLBACK_METHOD, interpolator

    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "fallback.png")

    monkeypatch.setattr(interpolator, "_rife_interpolate_core", lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    result = interpolator.interpolate(f1, f2, out, ratio=0.5)

    assert result is True
    assert os.path.exists(out)
    assert interpolator.last_run["fallbackUsed"] is True
    assert interpolator.last_run["fallbackMethod"] == FALLBACK_METHOD
    assert interpolator.last_run["executionMode"] == FALLBACK_METHOD


def test_phase0_gate_failure_uses_governed_optical_flow(monkeypatch, test_frames):
    from app.services.interpolation import FALLBACK_METHOD, interpolator

    f1, f2, tmpdir = test_frames
    out = os.path.join(tmpdir, "phase0.png")

    monkeypatch.setattr(
        "app.services.interpolation._load_phase0_gate",
        lambda: {"productionAllowed": False, "passed": False},
    )

    result = interpolator.interpolate(f1, f2, out, ratio=0.5)

    assert result is True
    assert interpolator.last_run["fallbackUsed"] is True
    assert interpolator.last_run["fallbackMethod"] == FALLBACK_METHOD
    assert interpolator.last_run["fallbackReason"] == "phase0_gate_failed"


def test_generate_intermediate_frames_records_recursive_audit_log(test_frames):
    from app.services.interpolation import generate_intermediate_frames, interpolator
    from app.services.metadata import load_interpolation_log

    f1, f2, tmpdir = test_frames
    out_dir = os.path.join(tmpdir, "interp_out")

    records = generate_intermediate_frames(f1, f2, out_dir, num_frames=3, file_prefix="test")

    assert len(records) == 3
    assert [record["ratio"] for record in records] == [0.25, 0.5, 0.75]
    assert interpolator.last_batch["strategy"] == "recursive_bisection"
    assert interpolator.last_batch["recursionDepth"] >= 2
    assert interpolator.last_batch["jobId"]
    assert os.path.exists(interpolator.last_batch["auditLogPath"])

    log = load_interpolation_log()
    assert log["latest"]["job_id"] == interpolator.last_batch["jobId"]
    assert log["latest"]["recursion_depth"] == interpolator.last_batch["recursionDepth"]
    assert log["latest"]["output_frames"] == [record["path"] for record in records]


def test_interpolate_with_alpha_preserves_rgba_and_generates_masks(tmpdir):
    from app.services.interpolation import interpolator

    f1 = os.path.join(tmpdir, "alpha1.png")
    f2 = os.path.join(tmpdir, "alpha2.png")
    out = os.path.join(tmpdir, "alpha_out.png")

    img1 = np.zeros((128, 128, 4), dtype=np.uint8)
    img1[:, :, :3] = (100, 150, 200)
    img1[:, :, 3] = 255
    img1[50:80, 50:80, 3] = 0

    img2 = np.zeros((128, 128, 4), dtype=np.uint8)
    img2[:, :, :3] = (200, 100, 50)
    img2[:, :, 3] = 255

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)

    result = interpolator.interpolate(f1, f2, out, ratio=0.5)
    assert result is True

    img_out = cv2.imread(out, cv2.IMREAD_UNCHANGED)
    assert img_out is not None
    assert img_out.shape[2] == 4
    assert np.all(img_out[:, :, 3] == 255)
    assert os.path.exists(interpolator.last_run["outputMasks"]["nodata"]["path"])


def test_large_image_interpolation_uses_tiling(monkeypatch, tmpdir):
    from app.services.interpolation import interpolator

    f1 = os.path.join(tmpdir, "large1.png")
    f2 = os.path.join(tmpdir, "large2.png")
    out = os.path.join(tmpdir, "large_out.png")

    img1 = np.zeros((1100, 1200, 3), dtype=np.uint8)
    img1[:, :] = (30, 90, 150)
    img2 = np.zeros((1100, 1200, 3), dtype=np.uint8)
    img2[:, :] = (150, 90, 30)

    cv2.imwrite(f1, img1)
    cv2.imwrite(f2, img2)

    monkeypatch.setattr(
        interpolator,
        "_rife_interpolate_core",
        lambda left, right, ratio: cv2.addWeighted(left, 1.0 - ratio, right, ratio, 0),
    )

    result = interpolator.interpolate(f1, f2, out, ratio=0.5)

    assert result is True
    assert os.path.exists(out)
    assert interpolator.last_run["tileInfo"]["used"] is True
    assert interpolator.last_run["tileInfo"]["tileCount"] > 1


def test_interpolator_exposes_governed_runtime_diagnostics():
    from app.services.interpolation import FALLBACK_METHOD, interpolator

    diagnostics = interpolator.get_diagnostics()

    assert diagnostics["model"]["name"] == "RIFE HDv3"
    assert diagnostics["model"]["version"] == "HDv3"
    assert diagnostics["model"]["preferredModel"] == "RIFE 4.6"
    assert diagnostics["model"]["benchmarkCompliant"] is False
    assert diagnostics["model"]["integrityVerified"] is True
    assert diagnostics["model"]["framework"].startswith("PyTorch")
    assert diagnostics["execution"]["fallbackMethod"] == FALLBACK_METHOD
    assert "Startup validation failures block interpolation" in diagnostics["execution"]["fallbackBehavior"]


def test_interpolation_log_api_exposes_audit_payload(monkeypatch):
    from app.main import app

    monkeypatch.setattr(
        "app.api.routes.load_interpolation_log",
        lambda: {"jobs": [{"job_id": "job-123", "fallback": False}], "latest": {"job_id": "job-123"}},
    )
    monkeypatch.setattr(
        "app.api.routes.get_interpolation_log_path",
        lambda: "/tmp/interpolation_log.json",
    )

    client = TestClient(app)
    response = client.get("/api/interpolation/log")

    assert response.status_code == 200
    payload = response.json()
    assert payload["log"]["latest"]["job_id"] == "job-123"
    assert payload["path"] == "/tmp/interpolation_log.json"
