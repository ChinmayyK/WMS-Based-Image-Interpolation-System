"""Tests for clean observed-frame visualization assets."""
import os

import cv2
import numpy as np

from app.services.visualization import detect_nodata_mask, prepare_visualization_assets


def test_detect_nodata_mask_uses_alpha_and_near_black():
    img = np.zeros((4, 4, 4), dtype=np.uint8)
    img[:, :, :3] = 100
    img[:, :, 3] = 255
    img[0, 0, :3] = 0
    img[1, 1, 3] = 0

    mask = detect_nodata_mask(img)

    assert mask[0, 0]
    assert mask[1, 1]
    assert not mask[2, 2]


def test_prepare_visualization_assets_generates_clean_and_gap_mask(tmpdir):
    raw_dir = os.path.join(tmpdir, "raw")
    clean_dir = os.path.join(tmpdir, "clean")
    gap_dir = os.path.join(tmpdir, "gaps")
    os.makedirs(raw_dir, exist_ok=True)

    # Frame A has a gap on the left, Frame B has valid coverage there.
    img_a = np.zeros((32, 32, 4), dtype=np.uint8)
    img_a[:, :, :3] = (10, 120, 200)
    img_a[:, :, 3] = 255
    img_a[:, :8, :3] = 0
    img_a[:, :8, 3] = 0

    img_b = np.zeros((32, 32, 4), dtype=np.uint8)
    img_b[:, :, :3] = (200, 80, 20)
    img_b[:, :, 3] = 255

    path_a = os.path.join(raw_dir, "frame_a_20240601.png")
    path_b = os.path.join(raw_dir, "frame_b_20240602.png")
    cv2.imwrite(path_a, img_a)
    cv2.imwrite(path_b, img_b)

    assets = prepare_visualization_assets(
        [
            {"path": path_a, "timestamp": "2024-06-01"},
            {"path": path_b, "timestamp": "2024-06-02"},
        ],
        clean_dir=clean_dir,
        gap_mask_dir=gap_dir,
    )

    assert path_a in assets
    clean = cv2.imread(assets[path_a]["cleanPath"], cv2.IMREAD_UNCHANGED)
    gap_mask = cv2.imread(assets[path_a]["gapMaskPath"], cv2.IMREAD_UNCHANGED)

    assert clean is not None
    assert gap_mask is not None
    assert clean.shape[2] == 4
    assert np.all(clean[:, :, 3] == 255)
    assert np.any(clean[:, :8, :3] != 0)
    assert assets[path_a]["hasSensorGap"] is True
    assert assets[path_a]["gapCoveragePct"] > 0
