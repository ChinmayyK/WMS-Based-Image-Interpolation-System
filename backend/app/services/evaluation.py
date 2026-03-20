"""
Evaluation engine for interpolation quality reporting.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

import cv2
import numpy as np
from skimage.metrics import peak_signal_noise_ratio, structural_similarity

from app.services.interpolation import interpolator

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
EVALUATIONS_DIR = os.path.join(DATA_DIR, "evaluations")
LATEST_EVALUATION_PATH = os.path.join(EVALUATIONS_DIR, "latest_evaluation.json")


def run_evaluation_suite() -> dict:
    """
    Evaluate interpolation quality on available triplets plus a synthetic fallback.
    """
    os.makedirs(EVALUATIONS_DIR, exist_ok=True)
    datasets = _collect_datasets()
    results = []

    for dataset in datasets:
        logger.info("Running evaluation dataset | name=%s", dataset["name"])
        result = _evaluate_triplet(dataset)
        results.append(result)

    summary = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "model": interpolator.get_diagnostics()["model"],
        "datasetCount": len(results),
        "results": results,
        "averages": {
            "psnr": round(float(np.mean([item["psnr"] for item in results])), 4),
            "ssim": round(float(np.mean([item["ssim"] for item in results])), 4),
            "lpips": _mean_optional([item["lpips"] for item in results]),
        },
    }

    with open(LATEST_EVALUATION_PATH, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
    return summary


def get_latest_evaluation() -> Optional[dict]:
    """Return the latest evaluation report if present."""
    if not os.path.exists(LATEST_EVALUATION_PATH):
        return None
    with open(LATEST_EVALUATION_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _evaluate_triplet(dataset: dict) -> dict:
    with tempfile.TemporaryDirectory() as td:
        output_path = os.path.join(td, f"{dataset['name']}_interp.png")
        interpolator.interpolate(dataset["frame0"], dataset["frame2"], output_path, ratio=0.5)
        generated = _load_rgb(output_path)
        target = _load_rgb(dataset["target"])
        if target.shape[:2] != generated.shape[:2]:
            target = cv2.resize(target, (generated.shape[1], generated.shape[0]))

        win_size = min(7, min(target.shape[0], target.shape[1]))
        if win_size % 2 == 0:
            win_size -= 1
        ssim_value = structural_similarity(
            target,
            generated,
            channel_axis=2,
            data_range=255,
            win_size=max(win_size, 3),
        )
        psnr_value = peak_signal_noise_ratio(target, generated, data_range=255)
        lpips_value = _compute_lpips(dataset["target"], output_path)
        return {
            "name": dataset["name"],
            "type": dataset["type"],
            "inputFrames": [dataset["frame0"], dataset["frame2"]],
            "targetFrame": dataset["target"],
            "psnr": round(float(psnr_value), 4),
            "ssim": round(float(ssim_value), 4),
            "lpips": round(float(lpips_value), 4) if lpips_value is not None else None,
        }


def _collect_datasets() -> list:
    datasets = [_synthetic_dataset()]
    clean_dir = os.path.join(DATA_DIR, "clean_frames")
    if os.path.isdir(clean_dir):
        clean_paths = sorted(
            os.path.join(clean_dir, name)
            for name in os.listdir(clean_dir)
            if name.lower().endswith(".png")
        )
        if len(clean_paths) >= 3:
            datasets.append({
                "name": "observed_triplet",
                "type": "observed_midpoint_holdout",
                "frame0": clean_paths[0],
                "target": clean_paths[1],
                "frame2": clean_paths[2],
            })
    return datasets


def _synthetic_dataset() -> dict:
    dataset_dir = os.path.join(DATA_DIR, "evaluation_synthetic")
    os.makedirs(dataset_dir, exist_ok=True)
    frame0 = os.path.join(dataset_dir, "synthetic_00.png")
    target = os.path.join(dataset_dir, "synthetic_05.png")
    frame2 = os.path.join(dataset_dir, "synthetic_10.png")

    if not all(os.path.exists(path) for path in (frame0, target, frame2)):
        start = np.zeros((256, 256, 3), dtype=np.uint8)
        mid = np.zeros((256, 256, 3), dtype=np.uint8)
        end = np.zeros((256, 256, 3), dtype=np.uint8)
        cv2.circle(start, (56, 128), 32, (60, 190, 255), -1)
        cv2.circle(mid, (128, 128), 32, (60, 190, 255), -1)
        cv2.circle(end, (200, 128), 32, (60, 190, 255), -1)
        cv2.imwrite(frame0, start)
        cv2.imwrite(target, mid)
        cv2.imwrite(frame2, end)

    return {
        "name": "synthetic_linear_motion",
        "type": "synthetic_holdout",
        "frame0": frame0,
        "target": target,
        "frame2": frame2,
    }


def _compute_lpips(target_path: str, generated_path: str) -> Optional[float]:
    try:
        import lpips
        import torch
    except ImportError:
        return None

    model = lpips.LPIPS(net="alex")
    target = _load_rgb(target_path)
    generated = _load_rgb(generated_path)
    if target.shape[:2] != generated.shape[:2]:
        generated = cv2.resize(generated, (target.shape[1], target.shape[0]))

    def _to_tensor(img: np.ndarray):
        tensor = torch.from_numpy(img.astype(np.float32) / 127.5 - 1.0)
        return tensor.permute(2, 0, 1).unsqueeze(0)

    with torch.no_grad():
        value = model(_to_tensor(target), _to_tensor(generated))
    return float(value.item())


def _load_rgb(path: str) -> np.ndarray:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    if img.shape[2] == 4:
        return cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2RGB)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)


def _mean_optional(values: list) -> Optional[float]:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return round(float(np.mean(numeric)), 4)
