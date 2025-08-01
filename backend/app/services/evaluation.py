"""
PRD v2.0 Module 7 evaluation engine.
"""
from __future__ import annotations

import json
import logging
import math
import os
import shutil
import uuid
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity

from app.services.confidence import (
    build_session_confidence_profile,
    governed_confidence_label,
    parse_timestamp,
    score_generated_sequence,
)
from app.services.interpolation import FALLBACK_METHOD, generate_intermediate_frames, interpolator


logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
EVALUATION_SETS_DIR = os.path.join(DATA_DIR, "evaluation_sets")
EVALUATIONS_DIR = os.path.join(DATA_DIR, "evaluations")
LATEST_EVALUATION_PATH = os.path.join(EVALUATIONS_DIR, "latest_evaluation.json")
LATEST_EVALUATION_HTML_PATH = os.path.join(EVALUATIONS_DIR, "latest_evaluation.html")
LATEST_EVALUATION_ASSETS_DIR = os.path.join(EVALUATIONS_DIR, "latest_assets")

PRD_TARGETS = {"psnr": 28.0, "ssim": 0.80}
PRD_BASELINE_TARGETS = {"psnr": 24.0, "ssim": 0.70, "lpips": 0.25, "tof_ratio": 2.0}
PHASE0_TARGETS = {"psnr": 28.0, "ssim": 0.80, "lpips": 0.15, "catastrophic_ssim": 0.40, "min_samples": 50}
DATASET_FRAME_COUNT = 37
DATASET_CADENCE_MINUTES = 10
FRAME_WIDTH = 96
FRAME_HEIGHT = 96
EVALUATION_VERSION = "PRD-v2.0-Module-7"
EVALUATION_SET_VERSION = "2.1"

DATASET_SPECS = [
    {
        "id": "clear_sky_low_motion",
        "name": "Clear Sky (Low Motion)",
        "regime": "clear_sky",
        "description": "Mostly clear scene with a thin, slowly drifting cloud veil.",
        "base_time": "2026-03-20T04:00:00+00:00",
    },
    {
        "id": "moderate_cloud_movement",
        "name": "Moderate Cloud Movement",
        "regime": "moderate_clouds",
        "description": "Organized cloud deck translating eastward across the scene.",
        "base_time": "2026-03-20T06:00:00+00:00",
    },
    {
        "id": "dynamic_storm_system",
        "name": "High Dynamic Storm System",
        "regime": "storm",
        "description": "Rotating storm-like cloud structure with stronger local deformation.",
        "base_time": "2026-03-20T08:00:00+00:00",
    },
    {
        "id": "coastal_ocean_mix",
        "name": "Coastal + Ocean Mix",
        "regime": "coastal",
        "description": "Coastline, ocean gradients, and advection over mixed surface types.",
        "base_time": "2026-03-20T10:00:00+00:00",
    },
    {
        "id": "day_night_transition",
        "name": "Day/Night Transition Case",
        "regime": "terminator",
        "description": "Scene with a visible day-night transition crossing the Earth disk.",
        "base_time": "2026-03-20T12:00:00+00:00",
    },
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value)


def _to_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"


def _write_json(path: str, payload: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def _write_image(path: str, image: np.ndarray) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    root, ext = os.path.splitext(path)
    temp_path = f"{root}.tmp{ext}"
    if not cv2.imwrite(temp_path, image):
        raise RuntimeError(f"Failed to write image: {temp_path}")
    os.replace(temp_path, path)


def _iso_timestamp(base_time: str, offset_minutes: int) -> str:
    base = datetime.fromisoformat(base_time.replace("Z", "+00:00"))
    current = base + timedelta(minutes=offset_minutes)
    return current.isoformat().replace("+00:00", "Z")


def _frame_stem(index: int) -> str:
    return f"frame_{index:02d}"


def _grid(height: int, width: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    x = np.linspace(-1.0, 1.0, width, dtype=np.float32)
    y = np.linspace(-1.0, 1.0, height, dtype=np.float32)
    xx, yy = np.meshgrid(x, y)
    radius = np.sqrt((xx / 0.96) ** 2 + (yy / 1.03) ** 2)
    theta = np.arctan2(yy, xx)
    return xx, yy, radius, theta


def _gaussian(xx: np.ndarray, yy: np.ndarray, cx: float, cy: float, sx: float, sy: float) -> np.ndarray:
    return np.exp(-(((xx - cx) ** 2) / (2.0 * sx ** 2) + ((yy - cy) ** 2) / (2.0 * sy ** 2)))


def _normalize01(layer: np.ndarray) -> np.ndarray:
    min_val = float(layer.min())
    max_val = float(layer.max())
    if max_val - min_val < 1e-6:
        return np.zeros_like(layer)
    return (layer - min_val) / (max_val - min_val)


def _render_regime(regime: str, index: int, total_frames: int, *, width: int, height: int) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    xx, yy, _radius, theta = _grid(height, width)
    nodata_mask = np.zeros((height, width), dtype=bool)
    limb_mask = np.zeros((height, width), dtype=bool)

    t = float(index) / float(max(total_frames - 1, 1))
    ocean = np.dstack(
        [
            60 + 30 * (1.0 - yy),
            95 + 38 * (1.0 - yy) + 10 * np.sin(xx * math.pi * 2.0),
            130 + 45 * (1.0 - yy),
        ]
    )
    land_mask = xx + 0.1 * np.sin(yy * 5.0 + t * 2.0) > 0.15
    land = np.dstack(
        [
            58 + 18 * np.cos(yy * 4.0),
            108 + 18 * np.sin(xx * 3.0),
            82 + 12 * np.cos((xx - yy) * 4.0),
        ]
    )
    background = np.where(land_mask[:, :, None], land, ocean)
    terminator_mask = np.zeros((height, width), dtype=bool)

    if regime == "clear_sky":
        cloud = (
            0.10 * _gaussian(xx, yy, -0.45 + 0.18 * t, -0.05, 0.22, 0.08)
            + 0.05 * _gaussian(xx, yy, 0.15 + 0.05 * t, 0.25, 0.18, 0.06)
        )
    elif regime == "moderate_clouds":
        band = 0.35 * (np.sin((xx * 3.2 - yy * 1.4) * math.pi + t * 3.4) + 1.0)
        vort = 0.18 * (np.cos((xx + yy) * math.pi * 2.1 - t * 2.3) + 1.0)
        cloud = 0.28 * _normalize01(band + vort)
        cloud += 0.22 * _gaussian(xx, yy, -0.35 + 0.45 * t, 0.18 - 0.1 * t, 0.26, 0.18)
    elif regime == "storm":
        cx = -0.18 + 0.16 * t
        cy = 0.15 - 0.12 * t
        dx = xx - cx
        dy = yy - cy
        radial = np.sqrt(dx ** 2 + dy ** 2)
        swirl = np.sin(theta * 4.5 + radial * 15.0 - t * 6.0)
        cloud = 0.38 * _normalize01(swirl)
        cloud += 0.38 * _gaussian(xx, yy, cx, cy, 0.22, 0.22)
        cloud += 0.14 * _gaussian(xx, yy, cx - 0.24, cy + 0.12, 0.17, 0.12)
    elif regime == "coastal":
        coastal_band = _normalize01(np.sin((xx * 2.8 + yy * 2.1) * math.pi - t * 2.8))
        cloud = 0.22 * coastal_band
        cloud += 0.26 * _gaussian(xx, yy, -0.42 + 0.40 * t, -0.12 + 0.08 * t, 0.25, 0.15)
        cloud += 0.16 * _gaussian(xx, yy, 0.15 + 0.12 * t, 0.20, 0.14, 0.10)
        background = np.where(
            land_mask[:, :, None],
            background * np.array([1.05, 0.98, 0.92], dtype=np.float32),
            background,
        )
    elif regime == "terminator":
        day_pos = -0.45 + 0.9 * t
        day_factor = 0.15 + 0.85 * (1.0 / (1.0 + np.exp(-(xx - day_pos) / 0.08)))
        transition = np.abs(xx - day_pos) <= 0.12
        terminator_mask = transition
        cloud = 0.25 * _normalize01(np.sin((xx * 2.2 - yy * 1.1) * math.pi + t * 3.8) + 1.0)
        cloud += 0.18 * _gaussian(xx, yy, -0.20 + 0.18 * t, -0.15, 0.22, 0.18)
        background = background * day_factor[:, :, None]
    else:
        raise ValueError(f"Unsupported evaluation regime: {regime}")

    cloud = np.clip(cloud, 0.0, 1.0)
    cloud_rgb = np.dstack(
        [
            180 + 70 * cloud,
            192 + 60 * cloud,
            205 + 50 * cloud,
        ]
    )
    image = background * (1.0 - 0.65 * cloud[:, :, None]) + cloud_rgb * (0.65 * cloud[:, :, None])
    image = np.clip(image, 0, 255).astype(np.uint8)

    rgba = np.dstack([image, np.where(nodata_mask, 0, 255).astype(np.uint8)])
    return rgba, nodata_mask.astype(bool), limb_mask.astype(bool), terminator_mask.astype(bool)


def _dataset_dirs(dataset_dir: str) -> dict:
    return {
        "frames": os.path.join(dataset_dir, "frames"),
        "nodata": os.path.join(dataset_dir, "masks", "nodata"),
        "limb": os.path.join(dataset_dir, "masks", "limb"),
        "terminator": os.path.join(dataset_dir, "masks", "terminator"),
    }


def _generate_dataset(spec: dict) -> dict:
    dataset_dir = os.path.join(EVALUATION_SETS_DIR, spec["id"])
    if os.path.isdir(dataset_dir):
        shutil.rmtree(dataset_dir)

    dirs = _dataset_dirs(dataset_dir)
    for path in dirs.values():
        os.makedirs(path, exist_ok=True)

    frames = []
    for index in range(DATASET_FRAME_COUNT):
        timestamp = _iso_timestamp(spec["base_time"], index * DATASET_CADENCE_MINUTES)
        stem = _frame_stem(index)

        frame_path = os.path.join(dirs["frames"], f"{stem}.png")
        nodata_path = os.path.join(dirs["nodata"], f"{stem}_nodata.png")
        limb_path = os.path.join(dirs["limb"], f"{stem}_limb.png")
        terminator_path = os.path.join(dirs["terminator"], f"{stem}_terminator.png")

        rgba, nodata_mask, limb_mask, terminator_mask = _render_regime(
            spec["regime"],
            index,
            DATASET_FRAME_COUNT,
            width=FRAME_WIDTH,
            height=FRAME_HEIGHT,
        )
        _write_image(frame_path, rgba)
        _write_image(nodata_path, nodata_mask.astype(np.uint8) * 255)
        _write_image(limb_path, limb_mask.astype(np.uint8) * 255)
        _write_image(terminator_path, terminator_mask.astype(np.uint8) * 255)

        frames.append(
            {
                "index": index,
                "timestamp": timestamp,
                "path": frame_path,
                "url": _to_data_url(frame_path),
                "nodataMaskPath": nodata_path,
                "nodataMaskUrl": _to_data_url(nodata_path),
                "limbMaskPath": limb_path,
                "limbMaskUrl": _to_data_url(limb_path),
                "terminatorMaskPath": terminator_path,
                "terminatorMaskUrl": _to_data_url(terminator_path),
                "type": "OBSERVED",
                "source": "Synthetic GOES-style benchmark",
            }
        )

    held_out_indices = [index for index in range(2, DATASET_FRAME_COUNT - 1, 3)]
    manifest = {
        "version": EVALUATION_SET_VERSION,
        "datasetId": spec["id"],
        "name": spec["name"],
        "type": "synthetic_geostationary",
        "regime": spec["regime"],
        "description": spec["description"],
        "createdAt": _utc_now(),
        "crs": "EPSG:3857",
        "bbox": [-10575351.63, 1345708.41, -6679169.45, 4865942.28],
        "frameSize": {"width": FRAME_WIDTH, "height": FRAME_HEIGHT},
        "cadenceMinutes": DATASET_CADENCE_MINUTES,
        "heldOutStrategy": "remove_every_3rd_frame",
        "heldOutIndices": held_out_indices,
        "frames": frames,
    }
    _write_json(os.path.join(dataset_dir, "manifest.json"), manifest)
    return manifest


def _load_manifest(dataset_dir: str) -> Optional[dict]:
    manifest_path = os.path.join(dataset_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        return None
    with open(manifest_path, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("version") != EVALUATION_SET_VERSION:
        return None
    if len(payload.get("frames") or []) != DATASET_FRAME_COUNT:
        return None
    return payload


def ensure_evaluation_sets() -> list[dict]:
    os.makedirs(EVALUATION_SETS_DIR, exist_ok=True)
    manifests = []
    for spec in DATASET_SPECS:
        dataset_dir = os.path.join(EVALUATION_SETS_DIR, spec["id"])
        manifest = _load_manifest(dataset_dir)
        if manifest is None:
            logger.info("Generating evaluation dataset %s", spec["id"])
            manifest = _generate_dataset(spec)
        manifests.append(manifest)
    return manifests


def _read_rgba(path: str) -> np.ndarray:
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        raise FileNotFoundError(path)
    if image.ndim == 2:
        image = cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    if image.shape[2] == 3:
        alpha = np.full(image.shape[:2], 255, dtype=np.uint8)
        image = np.dstack([image, alpha])
    return image


def _mask_from_path(path: str, shape: tuple[int, int]) -> np.ndarray:
    mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if mask is None:
        return np.zeros(shape, dtype=bool)
    if mask.shape != shape:
        mask = cv2.resize(mask, (shape[1], shape[0]), interpolation=cv2.INTER_NEAREST)
    return mask >= 127


def _combined_exclusion_mask(target_frame: dict, generated_masks: Optional[dict] = None) -> np.ndarray:
    shape = _read_rgba(target_frame["path"]).shape[:2]
    target_mask = (
        _mask_from_path(target_frame["nodataMaskPath"], shape)
        | _mask_from_path(target_frame["limbMaskPath"], shape)
        | _mask_from_path(target_frame["terminatorMaskPath"], shape)
    )
    if not generated_masks:
        return target_mask

    generated_mask = np.zeros(shape, dtype=bool)
    for key in ("nodata", "limb", "terminator"):
        path = ((generated_masks.get(key) or {}).get("path"))
        if path:
            generated_mask |= _mask_from_path(path, shape)
    return target_mask | generated_mask


def _valid_bbox(mask: np.ndarray) -> tuple[int, int, int, int]:
    ys, xs = np.where(mask)
    if ys.size == 0 or xs.size == 0:
        return 0, mask.shape[0], 0, mask.shape[1]
    return int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1


def _masked_rgb(image_path: str, valid_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    rgba = _read_rgba(image_path)
    rgb = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_BGR2RGB)
    alpha_valid = rgba[:, :, 3] >= 64
    final_mask = valid_mask & alpha_valid
    y0, y1, x0, x1 = _valid_bbox(final_mask)
    crop = rgb[y0:y1, x0:x1].copy()
    crop_mask = final_mask[y0:y1, x0:x1]
    return crop, crop_mask


def _masked_psnr(image_a_path: str, image_b_path: str, valid_mask: np.ndarray) -> float:
    a_crop, mask = _masked_rgb(image_a_path, valid_mask)
    b_crop, _ = _masked_rgb(image_b_path, valid_mask)
    if a_crop.shape[:2] != b_crop.shape[:2]:
        b_crop = cv2.resize(b_crop, (a_crop.shape[1], a_crop.shape[0]), interpolation=cv2.INTER_LINEAR)
    if not np.any(mask):
        return 0.0
    diff = a_crop.astype(np.float32) - b_crop.astype(np.float32)
    mse = float(np.mean(diff[mask] ** 2))
    if mse <= 1e-8:
        return 99.0
    return float(20.0 * math.log10(255.0 / math.sqrt(mse)))


def _masked_ssim(image_a_path: str, image_b_path: str, valid_mask: np.ndarray) -> float:
    a_crop, mask = _masked_rgb(image_a_path, valid_mask)
    b_crop, _ = _masked_rgb(image_b_path, valid_mask)
    if a_crop.shape[:2] != b_crop.shape[:2]:
        b_crop = cv2.resize(b_crop, (a_crop.shape[1], a_crop.shape[0]), interpolation=cv2.INTER_LINEAR)
    if not np.any(mask):
        return 0.0

    a_work = a_crop.copy()
    b_work = b_crop.copy()
    a_work[~mask] = 0
    b_work[~mask] = 0
    score = structural_similarity(
        a_work,
        b_work,
        channel_axis=2,
        data_range=255,
    )
    return float(score)


@lru_cache(maxsize=1)
def _load_lpips_model():
    try:
        import lpips
        import torch
    except Exception:
        return None

    model = lpips.LPIPS(net="alex")
    model.eval()
    for param in model.parameters():
        param.requires_grad = False
    model.to("cpu")
    return model


def _masked_lpips(image_a_path: str, image_b_path: str, valid_mask: np.ndarray) -> Optional[float]:
    model = _load_lpips_model()
    if model is None:
        return None

    import torch

    a_crop, mask = _masked_rgb(image_a_path, valid_mask)
    b_crop, _ = _masked_rgb(image_b_path, valid_mask)
    if a_crop.shape[:2] != b_crop.shape[:2]:
        b_crop = cv2.resize(b_crop, (a_crop.shape[1], a_crop.shape[0]), interpolation=cv2.INTER_LINEAR)
    if not np.any(mask):
        return None

    a_work = a_crop.copy()
    b_work = b_crop.copy()
    a_work[~mask] = 0
    b_work[~mask] = 0

    def _to_tensor(image: np.ndarray) -> torch.Tensor:
        tensor = torch.from_numpy(image.astype(np.float32) / 255.0)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0)
        return tensor * 2.0 - 1.0

    with torch.no_grad():
        score = model(_to_tensor(a_work), _to_tensor(b_work))
    return float(score.item())


def _grayscale_rgba(path: str, shape: Optional[tuple[int, int]] = None) -> tuple[np.ndarray, np.ndarray]:
    rgba = _read_rgba(path)
    if shape and rgba.shape[:2] != shape:
        rgba = cv2.resize(rgba, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
    gray = cv2.cvtColor(rgba[:, :, :3], cv2.COLOR_BGR2GRAY)
    alpha_valid = rgba[:, :, 3] >= 64
    return gray, alpha_valid


def _flow_error(prev_path: str, target_path: str, pred_path: str, next_path: str, valid_mask: np.ndarray) -> float:
    prev_gray, prev_valid = _grayscale_rgba(prev_path)
    target_gray, target_valid = _grayscale_rgba(target_path, prev_gray.shape)
    pred_gray, pred_valid = _grayscale_rgba(pred_path, prev_gray.shape)
    next_gray, next_valid = _grayscale_rgba(next_path, prev_gray.shape)

    mask = valid_mask & prev_valid & target_valid & pred_valid & next_valid
    if not np.any(mask):
        return 0.0

    flow_prev_target = interpolator._compute_farneback_flow(cv2.cvtColor(prev_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(target_gray, cv2.COLOR_GRAY2BGR))
    flow_prev_pred = interpolator._compute_farneback_flow(cv2.cvtColor(prev_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(pred_gray, cv2.COLOR_GRAY2BGR))
    flow_target_next = interpolator._compute_farneback_flow(cv2.cvtColor(target_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(next_gray, cv2.COLOR_GRAY2BGR))
    flow_pred_next = interpolator._compute_farneback_flow(cv2.cvtColor(pred_gray, cv2.COLOR_GRAY2BGR), cv2.cvtColor(next_gray, cv2.COLOR_GRAY2BGR))

    err0 = np.linalg.norm(flow_prev_target - flow_prev_pred, axis=2)
    err1 = np.linalg.norm(flow_target_next - flow_pred_next, axis=2)
    samples = np.concatenate([err0[mask], err1[mask]])
    return float(samples.mean()) if samples.size else 0.0


def _expected_quality_label(psnr: float, ssim: float) -> str:
    if psnr >= 32.0 and ssim >= 0.90:
        return "HIGH"
    if psnr >= PRD_TARGETS["psnr"] and ssim >= PRD_TARGETS["ssim"]:
        return "MEDIUM"
    if psnr >= 24.0 and ssim >= 0.70:
        return "LOW"
    return "REJECTED"


def _actual_high(psnr: float, ssim: float) -> bool:
    return psnr >= PRD_TARGETS["psnr"] and ssim >= 0.85


def _summarize_confidence(results: list[dict]) -> dict:
    labels = [item["confidence"]["predictedLabel"] for item in results]
    actual_high = [item["confidence"]["actualLabel"] == "HIGH" for item in results]
    predicted_high_indices = [idx for idx, label in enumerate(labels) if label == "HIGH"]
    rejected_indices = [idx for idx, label in enumerate(labels) if label == "REJECTED"]
    false_confidence_cases = [
        {
            "dataset": results[idx]["name"],
            "jobId": results[idx]["jobId"],
            "predicted": labels[idx],
            "actual": results[idx]["confidence"]["actualLabel"],
            "psnr": results[idx]["psnr"],
            "ssim": results[idx]["ssim"],
        }
        for idx in predicted_high_indices
        if not actual_high[idx]
    ]

    high_accuracy = (
        float(sum(actual_high[idx] for idx in predicted_high_indices)) / float(len(predicted_high_indices))
        if predicted_high_indices
        else 0.0
    )
    overall_match = (
        float(sum(result["confidence"]["predictedLabel"] == result["confidence"]["actualLabel"] for result in results))
        / float(len(results))
        if results
        else 0.0
    )
    rejection_rate = float(len(rejected_indices)) / float(len(results)) if results else 0.0
    return {
        "confidence_accuracy": round(high_accuracy, 4),
        "overall_label_accuracy": round(overall_match, 4),
        "rejection_rate": round(rejection_rate, 4),
        "misclassification": len(false_confidence_cases),
        "highPredictionCount": len(predicted_high_indices),
        "falseConfidenceCases": false_confidence_cases,
    }


def _average_metric(results: list[dict], key: str, *, nested: Optional[str] = None) -> Optional[float]:
    values = []
    for item in results:
        value = item[key] if nested is None else item[nested][key]
        if value is not None:
            values.append(float(value))
    if not values:
        return None
    return round(float(np.mean(values)), 4)


def _baseline_summary(results: list[dict]) -> dict:
    return {
        "psnr": _average_metric(results, "psnr", nested="baselineMetrics"),
        "ssim": _average_metric(results, "ssim", nested="baselineMetrics"),
        "lpips": _average_metric(results, "lpips", nested="baselineMetrics"),
        "tof": _average_metric(results, "tof", nested="baselineMetrics"),
    }


def _quality_summary(results: list[dict]) -> dict:
    return {
        "psnr": _average_metric(results, "psnr"),
        "ssim": _average_metric(results, "ssim"),
        "lpips": _average_metric(results, "lpips"),
        "tof": _average_metric(results, "tof"),
    }


def _metric_distribution(results: list[dict], key: str, *, nested: Optional[str] = None) -> Optional[dict]:
    values = []
    for item in results:
        value = item[key] if nested is None else item[nested][key]
        if value is not None:
            values.append(float(value))
    if not values:
        return None
    arr = np.array(values, dtype=np.float32)
    return {
        "mean": round(float(arr.mean()), 4),
        "median": round(float(np.median(arr)), 4),
        "std": round(float(arr.std()), 4),
        "min": round(float(arr.min()), 4),
        "max": round(float(arr.max()), 4),
    }


def _distribution_summary(results: list[dict]) -> dict:
    return {
        "psnr": _metric_distribution(results, "psnr"),
        "ssim": _metric_distribution(results, "ssim"),
        "lpips": _metric_distribution(results, "lpips"),
        "tof": _metric_distribution(results, "tof"),
    }


def _confidence_calibration_summary(results: list[dict]) -> dict:
    bins = []
    ece = 0.0
    total = float(len(results)) if results else 1.0
    for index in range(5):
        lower = index * 0.2
        upper = 1.0 if index == 4 else (index + 1) * 0.2
        bucket = [
            item for item in results
            if lower <= float(item["confidence"]["score"]) <= upper
            and (index == 4 or float(item["confidence"]["score"]) < upper)
        ]
        if not bucket:
            bins.append(
                {
                    "range": [round(lower, 2), round(upper, 2)],
                    "count": 0,
                    "meanScore": None,
                    "observedAccuracy": None,
                }
            )
            continue
        mean_score = float(np.mean([item["confidence"]["score"] for item in bucket]))
        observed_accuracy = float(
            np.mean([1.0 if item["confidence"]["actualLabel"] == item["confidence"]["predictedLabel"] else 0.0 for item in bucket])
        )
        ece += abs(mean_score - observed_accuracy) * (len(bucket) / total)
        bins.append(
            {
                "range": [round(lower, 2), round(upper, 2)],
                "count": len(bucket),
                "meanScore": round(mean_score, 4),
                "observedAccuracy": round(observed_accuracy, 4),
            }
        )
    return {
        "bins": bins,
        "expectedCalibrationError": round(ece, 4),
    }


def _phase0_qualification(results: list[dict], averages: dict) -> dict:
    lpips_values = [item["lpips"] for item in results if item.get("lpips") is not None]
    catastrophic_failures = [
        {"jobId": item["jobId"], "dataset": item["name"], "ssim": item["ssim"]}
        for item in results
        if item["ssim"] < PHASE0_TARGETS["catastrophic_ssim"]
    ]
    passes = {
        "sampleCount": len(results) >= PHASE0_TARGETS["min_samples"],
        "psnr": (averages["psnr"] or 0.0) >= PHASE0_TARGETS["psnr"],
        "ssim": (averages["ssim"] or 0.0) >= PHASE0_TARGETS["ssim"],
        "lpips": bool(lpips_values) and (averages["lpips"] or 1.0) <= PHASE0_TARGETS["lpips"],
        "catastrophicFailure": len(catastrophic_failures) == 0,
    }
    passed = all(passes.values())
    return {
        "sampleCount": len(results),
        "passed": passed,
        "productionAllowed": passed,
        "fallbackMode": None if passed else FALLBACK_METHOD,
        "thresholds": PHASE0_TARGETS,
        "checks": passes,
        "lpipsAvailable": bool(lpips_values),
        "catastrophicFailures": catastrophic_failures,
        "warning": None if passed else "Phase 0 qualification gate did not pass. Use optical-flow fallback for governed operation.",
    }


def _svg_confidence_calibration(calibration: dict) -> str:
    width = 720
    height = 260
    points = []
    bars = []
    usable_bins = [item for item in calibration.get("bins") or [] if item.get("count")]
    for index, item in enumerate(usable_bins):
        x = 80 + index * 120
        mean_score = float(item["meanScore"] or 0.0)
        observed = float(item["observedAccuracy"] or 0.0)
        y_score = 210 - int(mean_score * 150)
        y_observed = 210 - int(observed * 150)
        bars.append(f'<rect x="{x - 18}" y="{y_observed}" width="36" height="{210 - y_observed}" fill="#4cc9f0" rx="6" />')
        bars.append(f'<circle cx="{x}" cy="{y_score}" r="7" fill="#ffb703" />')
        bars.append(f'<text x="{x - 28}" y="232" font-size="10" fill="#9fb2c7">{item["range"][0]:.1f}-{item["range"][1]:.1f}</text>')
        points.append(f"{x},{y_score}")

    polyline = ""
    if len(points) > 1:
        polyline = f'<polyline fill="none" stroke="#ffb703" stroke-width="3" points="{" ".join(points)}" />'

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="100%" height="100%" fill="#0f1720" rx="14" />'
        '<text x="24" y="28" fill="#ffffff" font-size="16" font-weight="700">Confidence Calibration</text>'
        '<line x1="60" y1="210" x2="680" y2="210" stroke="#314557" />'
        '<line x1="60" y1="40" x2="60" y2="210" stroke="#314557" />'
        '<line x1="60" y1="60" x2="680" y2="60" stroke="#1d2e3d" stroke-dasharray="5 5" />'
        '<text x="24" y="64" fill="#9fb2c7" font-size="10">1.0</text>'
        '<text x="24" y="214" fill="#9fb2c7" font-size="10">0.0</text>'
        + "".join(bars)
        + polyline
        + '<text x="24" y="246" fill="#9fb2c7" font-size="10">Blue bars: observed label accuracy per score bin. Gold line: mean confidence score.</text>'
        + "</svg>"
    )


def _html_distribution_table(title: str, distributions: dict) -> str:
    rows = []
    for key, values in distributions.items():
        if not values:
            continue
        rows.append(
            "<tr>"
            f"<td>{key.upper()}</td>"
            f"<td>{values['mean']:.4f}</td>"
            f"<td>{values['median']:.4f}</td>"
            f"<td>{values['std']:.4f}</td>"
            f"<td>{values['min']:.4f}</td>"
            f"<td>{values['max']:.4f}</td>"
            "</tr>"
        )
    return (
        "<div class='tile'>"
        f"<h2>{title}</h2>"
        "<table><thead><tr><th>Metric</th><th>Mean</th><th>Median</th><th>Std Dev</th><th>Min</th><th>Max</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
        "</div>"
    )
    passed = all(passes.values())
    return {
        "sampleCount": len(results),
        "passed": passed,
        "productionAllowed": passed,
        "fallbackMode": None if passed else FALLBACK_METHOD,
        "thresholds": PHASE0_TARGETS,
        "checks": passes,
        "lpipsAvailable": bool(lpips_values),
        "catastrophicFailures": catastrophic_failures,
        "warning": None if passed else "Phase 0 qualification gate did not pass. Use optical-flow fallback for governed operation.",
    }


def _copy_example_asset(source_path: str, assets_dir: str, prefix: str) -> str:
    filename = f"{prefix}_{os.path.basename(source_path)}"
    output_path = os.path.join(assets_dir, filename)
    shutil.copy2(source_path, output_path)
    return output_path


def _build_baseline_frame(
    frame0: dict,
    frame1: dict,
    output_path: str,
) -> tuple[str, dict]:
    img0_raw = interpolator._read_image(frame0["path"])
    img1_raw = interpolator._read_image(frame1["path"])
    height, width = img0_raw.shape[:2]
    if img1_raw.shape[:2] != (height, width):
        img1_raw = cv2.resize(img1_raw, (width, height), interpolation=cv2.INTER_LINEAR)

    img0_bgr, alpha0 = interpolator._separate_alpha(img0_raw)
    img1_bgr, alpha1 = interpolator._separate_alpha(img1_raw)
    valid0 = interpolator._alpha_to_valid_mask(alpha0, (height, width))
    valid1 = interpolator._alpha_to_valid_mask(alpha1, (height, width))
    img0_prefill = interpolator._prefill_missing_regions(img0_bgr, valid0, img1_bgr, valid1)
    img1_prefill = interpolator._prefill_missing_regions(img1_bgr, valid1, img0_bgr, valid0)

    result_bgr = interpolator._optical_flow_interpolate_core(img0_prefill, img1_prefill, 0.5)
    result_bgr = interpolator._compose_full_frame(result_bgr, img0_bgr, img1_bgr, valid0, valid1)

    result_alpha = None
    if alpha0 is not None or alpha1 is not None:
        a0 = alpha0 if alpha0 is not None else np.full((height, width), 255, dtype=np.uint8)
        a1 = alpha1 if alpha1 is not None else np.full((height, width), 255, dtype=np.uint8)
        result_alpha = np.maximum(a0, a1)

    output = interpolator._merge_alpha(result_bgr, result_alpha)
    mask_bundle = interpolator._build_mask_bundle(
        {"frame0": frame0, "frame1": frame1},
        (height, width),
        alpha0,
        alpha1,
    )
    output_masks = interpolator._build_output_masks(mask_bundle, result_alpha)
    _write_image(output_path, output)

    masks_dir = os.path.join(os.path.dirname(output_path), "baseline_masks")
    os.makedirs(masks_dir, exist_ok=True)
    persisted_masks = {}
    stem = os.path.splitext(os.path.basename(output_path))[0]
    for key, mask in output_masks.items():
        mask_path = os.path.join(masks_dir, f"{stem}_{key}.png")
        _write_image(mask_path, mask.astype(np.uint8) * 255)
        persisted_masks[key] = {
            "path": mask_path,
            "url": _to_data_url(mask_path),
            "coveragePct": round(float(mask.mean() * 100.0), 4),
        }

    return output_path, persisted_masks


def _metric_block(
    predicted_path: str,
    target_frame: dict,
    prev_frame: dict,
    next_frame: dict,
    generated_masks: Optional[dict],
) -> dict:
    exclusion = _combined_exclusion_mask(target_frame, generated_masks)
    valid_mask = ~exclusion
    psnr = round(_masked_psnr(predicted_path, target_frame["path"], valid_mask), 4)
    ssim = round(_masked_ssim(predicted_path, target_frame["path"], valid_mask), 4)
    lpips_score = _masked_lpips(predicted_path, target_frame["path"], valid_mask)
    tof = round(_flow_error(prev_frame["path"], target_frame["path"], predicted_path, next_frame["path"], valid_mask), 4)
    return {
        "psnr": psnr,
        "ssim": ssim,
        "lpips": None if lpips_score is None else round(lpips_score, 4),
        "tof": tof,
        "validCoveragePct": round(float(valid_mask.mean() * 100.0), 4),
        "maskedPixelPct": round(float(exclusion.mean() * 100.0), 4),
    }


def _comparison_block(model_metrics: dict, baseline_metrics: dict) -> dict:
    return {
        "psnrDelta": round(model_metrics["psnr"] - baseline_metrics["psnr"], 4),
        "ssimDelta": round(model_metrics["ssim"] - baseline_metrics["ssim"], 4),
        "lpipsDelta": None
        if model_metrics["lpips"] is None or baseline_metrics["lpips"] is None
        else round(baseline_metrics["lpips"] - model_metrics["lpips"], 4),
        "tofDelta": round(baseline_metrics["tof"] - model_metrics["tof"], 4),
        "winner": "RIFE"
        if (model_metrics["psnr"], model_metrics["ssim"]) >= (baseline_metrics["psnr"], baseline_metrics["ssim"])
        else "optical_flow",
    }


def _dataset_summary(manifest: dict) -> dict:
    return {
        "id": manifest["datasetId"],
        "name": manifest["name"],
        "type": manifest["type"],
        "regime": manifest["regime"],
        "description": manifest["description"],
        "frameCount": len(manifest["frames"]),
        "cadenceMinutes": manifest["cadenceMinutes"],
        "heldOutIndices": manifest["heldOutIndices"],
        "path": os.path.join(EVALUATION_SETS_DIR, manifest["datasetId"]),
    }


def _svg_bar_chart(results: list[dict], metric_key: str, label: str) -> str:
    width = 720
    bar_width = 48
    gap = 22
    height = 220
    values = []
    for item in results:
        values.extend([item[metric_key], item["baselineMetrics"][metric_key]])
    max_val = max(max(values), PRD_TARGETS.get(metric_key, 1.0), 1.0)
    bars = []
    x = 36
    for item in results:
        model_height = int((item[metric_key] / max_val) * 150)
        base_height = int((item["baselineMetrics"][metric_key] / max_val) * 150)
        bars.append(f'<rect x="{x}" y="{190 - model_height}" width="{bar_width}" height="{model_height}" fill="#4cc9f0" rx="5" />')
        bars.append(f'<rect x="{x + bar_width + 6}" y="{190 - base_height}" width="{bar_width}" height="{base_height}" fill="#f4a261" rx="5" />')
        bars.append(f'<text x="{x}" y="208" font-size="9" fill="#dfe7ef">{item["name"][:12]}</text>')
        x += bar_width * 2 + gap

    target_line = ""
    if metric_key in PRD_TARGETS:
        y = 190 - int((PRD_TARGETS[metric_key] / max_val) * 150)
        target_line = f'<line x1="24" y1="{y}" x2="{width - 24}" y2="{y}" stroke="#ffb703" stroke-dasharray="6 4" stroke-width="2" />'

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">'
        '<rect width="100%" height="100%" fill="#0f1720" rx="14" />'
        f'<text x="24" y="24" fill="#ffffff" font-size="16" font-weight="700">{label}</text>'
        f"{target_line}"
        + "".join(bars)
        + '<text x="24" y="210" fill="#9fb2c7" font-size="10">Blue: RIFE / Orange: optical flow baseline</text>'
        + "</svg>"
    )


def _build_html_report(report: dict) -> str:
    psnr_chart = _svg_bar_chart(report["results"], "psnr", "PSNR Comparison")
    ssim_chart = _svg_bar_chart(report["results"], "ssim", "SSIM Comparison")
    calibration_chart = _svg_confidence_calibration(report["confidenceCalibration"])
    rows = []
    for item in report["results"]:
        rows.append(
            "<tr>"
            f"<td>{item['name']}</td>"
            f"<td>{item['timestamp']}</td>"
            f"<td>{item['psnr']:.2f}</td>"
            f"<td>{item['ssim']:.4f}</td>"
            f"<td>{item['tof']:.4f}</td>"
            f"<td>{item['baselineMetrics']['psnr']:.2f}</td>"
            f"<td>{item['baselineMetrics']['ssim']:.4f}</td>"
            f"<td>{item['comparison']['winner']}</td>"
            "</tr>"
        )

    example_cards = []
    for item in report["results"]:
        assets = item["reportAssets"]
        example_cards.append(
            "<div class='card'>"
            f"<h3>{item['name']} | held-out #{item['heldOutIndex']}</h3>"
            f"<p>{item['comparison']['winner']} won this sample.</p>"
            "<div class='grid'>"
            f"<figure><img src='{assets['target']}' alt='Ground truth'/><figcaption>Ground Truth</figcaption></figure>"
            f"<figure><img src='{assets['prediction']}' alt='RIFE prediction'/><figcaption>RIFE</figcaption></figure>"
            f"<figure><img src='{assets['baseline']}' alt='Baseline prediction'/><figcaption>Optical Flow</figcaption></figure>"
            "</div>"
            "</div>"
        )

    warning = ""
    if report["targetValidation"]["warning"]:
        warning = f"<div class='warning'>{report['targetValidation']['warning']}</div>"

    qualification = report.get("qualificationGate") or {"passed": False}
    qualification_text = "Passed" if qualification["passed"] else "Fallback Required"
    dataset_rows = [
        "<tr>"
        f"<td>{item['name']}</td>"
        f"<td>{item['regime']}</td>"
        f"<td>{item['frameCount']}</td>"
        f"<td>{item['cadenceMinutes']}</td>"
        f"<td>{len(item['heldOutIndices'])}</td>"
        "</tr>"
        for item in report["datasets"]
    ]
    confidence_validation = report["confidenceValidation"]
    model_distribution_table = _html_distribution_table("RIFE Metric Distribution", report["distributions"])
    baseline_distribution_table = _html_distribution_table("Baseline Metric Distribution", report["baselineDistributions"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Evaluation Report</title>
  <style>
    body {{ font-family: Helvetica, Arial, sans-serif; background: #091018; color: #e6edf3; margin: 0; padding: 32px; }}
    h1, h2, h3 {{ margin: 0 0 12px; }}
    p {{ color: #b6c4d3; }}
    .stack {{ display: grid; gap: 18px; }}
    .summary {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; }}
    .tile, .card {{ background: #101923; border: 1px solid #1c2b38; border-radius: 14px; padding: 16px; }}
    .warning {{ background: #351e1e; border: 1px solid #a44; color: #ffd5d5; border-radius: 12px; padding: 14px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #223342; text-align: left; font-size: 14px; }}
    th {{ color: #9fb2c7; text-transform: uppercase; font-size: 11px; letter-spacing: 0.08em; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
    figure {{ margin: 0; }}
    img {{ width: 100%; border-radius: 10px; border: 1px solid #243849; background: #02060a; }}
    figcaption {{ font-size: 12px; color: #9fb2c7; margin-top: 6px; }}
    .charts {{ display: grid; gap: 18px; }}
    @media (max-width: 960px) {{
      .summary, .grid {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="stack">
    <div>
      <h1>Evaluation Engine Report</h1>
      <p>Generated {report['generatedAt']} | {report['datasetCount']} datasets | {report['sampleCount']} held-out evaluations</p>
    </div>
    {warning}
    <div class="summary">
      <div class="tile"><h3>Average PSNR</h3><p>{report['averages']['psnr']:.2f} dB</p></div>
      <div class="tile"><h3>Average SSIM</h3><p>{report['averages']['ssim']:.4f}</p></div>
      <div class="tile"><h3>Baseline PSNR</h3><p>{report['baselineAverages']['psnr']:.2f} dB</p></div>
      <div class="tile"><h3>Qualification Gate</h3><p>{qualification_text}</p></div>
    </div>
    <div class="tile">
      <h2>Dataset Summary</h2>
      <table>
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Regime</th>
            <th>Frames</th>
            <th>Cadence (min)</th>
            <th>Held-out Samples</th>
          </tr>
        </thead>
        <tbody>
          {''.join(dataset_rows)}
        </tbody>
      </table>
    </div>
    <div class="summary">
      <div class="tile"><h3>Confidence Accuracy</h3><p>{confidence_validation['confidence_accuracy']:.2%}</p></div>
      <div class="tile"><h3>Overall Label Accuracy</h3><p>{confidence_validation['overall_label_accuracy']:.2%}</p></div>
      <div class="tile"><h3>Rejection Rate</h3><p>{confidence_validation['rejection_rate']:.2%}</p></div>
      <div class="tile"><h3>ECE</h3><p>{report['confidenceCalibration']['expectedCalibrationError']:.4f}</p></div>
    </div>
    <div class="charts">
      {psnr_chart}
      {ssim_chart}
      {calibration_chart}
    </div>
    {model_distribution_table}
    {baseline_distribution_table}
    <div class="tile">
      <h2>Metric Table</h2>
      <table>
        <thead>
          <tr>
            <th>Dataset</th>
            <th>Timestamp</th>
            <th>PSNR</th>
            <th>SSIM</th>
            <th>tOF</th>
            <th>Baseline PSNR</th>
            <th>Baseline SSIM</th>
            <th>Winner</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rows)}
        </tbody>
      </table>
    </div>
    <div class="stack">
      <h2>Example Frames</h2>
      {''.join(example_cards)}
    </div>
  </div>
</body>
</html>
"""


def _copy_latest_run(run_dir: str) -> None:
    latest_assets = os.path.join(run_dir, "assets")
    if os.path.isdir(LATEST_EVALUATION_ASSETS_DIR):
        shutil.rmtree(LATEST_EVALUATION_ASSETS_DIR)
    shutil.copytree(latest_assets, LATEST_EVALUATION_ASSETS_DIR)
    shutil.copy2(os.path.join(run_dir, "report.json"), LATEST_EVALUATION_PATH)
    shutil.copy2(os.path.join(run_dir, "report.html"), LATEST_EVALUATION_HTML_PATH)


def get_latest_evaluation() -> Optional[dict]:
    if not os.path.exists(LATEST_EVALUATION_PATH):
        return None
    with open(LATEST_EVALUATION_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def get_job_evaluation(job_id: str) -> Optional[dict]:
    report = get_latest_evaluation()
    if not report:
        return None
    for item in report.get("results") or []:
        if item.get("jobId") == job_id:
            return item
    return None


def get_latest_qualification_gate() -> Optional[dict]:
    report = get_latest_evaluation()
    if not report:
        return None
    return report.get("qualificationGate")


def _evaluate_manifest(manifest: dict, run_dir: str) -> list[dict]:
    dataset_id = manifest["datasetId"]
    dataset_dir = os.path.join(EVALUATION_SETS_DIR, dataset_id)
    outputs_dir = os.path.join(run_dir, "outputs", dataset_id)
    assets_dir = os.path.join(run_dir, "assets")
    os.makedirs(outputs_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)

    frames = manifest["frames"]
    held_out_indices = manifest["heldOutIndices"]
    confidence_profile = build_session_confidence_profile(frames)
    results = []

    for held_out in held_out_indices:
        prev_frame = frames[held_out - 1]
        target_frame = frames[held_out]
        next_frame = frames[held_out + 1]

        generated = generate_intermediate_frames(
            prev_frame["path"],
            next_frame["path"],
            outputs_dir,
            num_frames=1,
            file_prefix=f"{dataset_id}_{held_out}",
            frame0_context=prev_frame,
            frame1_context=next_frame,
        )
        generated_record = generated[0]
        predicted_path = generated_record["path"]
        generated_masks = generated_record.get("maskInfo") or {}
        model_metrics = _metric_block(predicted_path, target_frame, prev_frame, next_frame, generated_masks)

        baseline_path = os.path.join(outputs_dir, f"{dataset_id}_{held_out}_baseline.png")
        baseline_path, baseline_masks = _build_baseline_frame(prev_frame, next_frame, baseline_path)
        baseline_metrics = _metric_block(baseline_path, target_frame, prev_frame, next_frame, baseline_masks)

        gap_minutes = None
        prev_ts = parse_timestamp(prev_frame["timestamp"])
        next_ts = parse_timestamp(next_frame["timestamp"])
        if prev_ts and next_ts:
            gap_minutes = abs((next_ts - prev_ts).total_seconds()) / 60.0

        confidence = score_generated_sequence(
            [generated_record],
            prev_frame["path"],
            next_frame["path"],
            gap_minutes,
            confidence_profile,
            source_frame0=prev_frame,
            source_frame1=next_frame,
        )[0]
        actual_label = governed_confidence_label(
            _expected_quality_label(model_metrics["psnr"], model_metrics["ssim"]),
            gap_minutes,
        )
        confidence_block = {
            "score": confidence["confidence"],
            "predictedLabel": confidence["confidenceLabel"],
            "provenanceLabel": confidence.get("provenanceLabel"),
            "actualLabel": actual_label,
            "meetsTarget": actual_label in {"HIGH", "MEDIUM"},
            "method": confidence["confidenceMethod"],
            "details": confidence["metrics"],
        }

        job_id = ((interpolator.last_batch or {}).get("jobId")) or f"eval_{uuid.uuid4().hex[:12]}"
        example_target = _copy_example_asset(target_frame["path"], assets_dir, f"{dataset_id}_{held_out}_gt")
        example_pred = _copy_example_asset(predicted_path, assets_dir, f"{dataset_id}_{held_out}_pred")
        example_base = _copy_example_asset(baseline_path, assets_dir, f"{dataset_id}_{held_out}_base")

        result = {
            "jobId": job_id,
            "name": manifest["name"],
            "datasetId": dataset_id,
            "type": manifest["type"],
            "regime": manifest["regime"],
            "timestamp": target_frame["timestamp"],
            "heldOutIndex": held_out,
            "inputFrames": [prev_frame["path"], next_frame["path"]],
            "targetFrame": target_frame["path"],
            "outputFrames": [predicted_path, baseline_path],
            "model": "RIFE",
            "baseline": "optical_flow",
            "psnr": model_metrics["psnr"],
            "ssim": model_metrics["ssim"],
            "lpips": model_metrics["lpips"],
            "tof": model_metrics["tof"],
            "metrics": model_metrics,
            "baselineMetrics": baseline_metrics,
            "comparison": _comparison_block(model_metrics, baseline_metrics),
            "confidence": confidence_block,
            "modelRun": generated_record.get("interpolation") or {},
            "motion": generated_record.get("motion") or {},
            "masks": {
                "target": {
                    "nodata": target_frame["nodataMaskUrl"],
                    "limb": target_frame["limbMaskUrl"],
                    "terminator": target_frame["terminatorMaskUrl"],
                },
                "prediction": {key: value.get("url") for key, value in generated_masks.items()},
                "baseline": {key: value.get("url") for key, value in baseline_masks.items()},
            },
            "reportAssets": {
                "target": f"/data/evaluations/latest_assets/{os.path.basename(example_target)}",
                "prediction": f"/data/evaluations/latest_assets/{os.path.basename(example_pred)}",
                "baseline": f"/data/evaluations/latest_assets/{os.path.basename(example_base)}",
            },
            "passesTarget": _actual_high(model_metrics["psnr"], model_metrics["ssim"]),
        }
        results.append(result)

    return results


def run_evaluation_suite() -> dict:
    manifests = ensure_evaluation_sets()
    os.makedirs(EVALUATIONS_DIR, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    run_dir = os.path.join(EVALUATIONS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    all_results = []
    for manifest in manifests:
        all_results.extend(_evaluate_manifest(manifest, run_dir))

    averages = _quality_summary(all_results)
    distributions = _distribution_summary(all_results)
    baseline_averages = _baseline_summary(all_results)
    baseline_distributions = {
        "psnr": _metric_distribution(all_results, "psnr", nested="baselineMetrics"),
        "ssim": _metric_distribution(all_results, "ssim", nested="baselineMetrics"),
        "lpips": _metric_distribution(all_results, "lpips", nested="baselineMetrics"),
        "tof": _metric_distribution(all_results, "tof", nested="baselineMetrics"),
    }
    confidence_validation = _summarize_confidence(all_results)
    confidence_calibration = _confidence_calibration_summary(all_results)
    qualification_gate = _phase0_qualification(all_results, averages)
    meets_targets = bool(
        (averages["psnr"] or 0.0) >= PRD_TARGETS["psnr"]
        and (averages["ssim"] or 0.0) >= PRD_TARGETS["ssim"]
    )
    warning = None
    if not meets_targets:
        warning = (
            f"PRD targets not met: average PSNR={averages['psnr']:.2f} dB "
            f"and SSIM={averages['ssim']:.4f}."
        )
        logger.warning(warning)

    report = {
        "version": EVALUATION_VERSION,
        "generatedAt": _utc_now(),
        "datasetDirectory": EVALUATION_SETS_DIR,
        "datasetCount": len(manifests),
        "sampleCount": len(all_results),
        "datasets": [_dataset_summary(manifest) for manifest in manifests],
        "heldOutProtocol": "Every 3rd frame is removed and reconstructed from its immediate neighbors.",
        "results": all_results,
        "averages": averages,
        "distributions": distributions,
        "baselineAverages": baseline_averages,
        "baselineDistributions": baseline_distributions,
        "thresholds": PRD_TARGETS,
        "targetValidation": {
            "psnrTarget": PRD_TARGETS["psnr"],
            "ssimTarget": PRD_TARGETS["ssim"],
            "meetsPSNR": bool((averages["psnr"] or 0.0) >= PRD_TARGETS["psnr"]),
            "meetsSSIM": bool((averages["ssim"] or 0.0) >= PRD_TARGETS["ssim"]),
            "meetsAll": meets_targets,
            "warning": warning,
        },
        "confidenceValidation": confidence_validation,
        "confidenceCalibration": confidence_calibration,
        "qualificationGate": qualification_gate,
        "reportPaths": {
            "jsonPath": os.path.join(run_dir, "report.json"),
            "htmlPath": os.path.join(run_dir, "report.html"),
            "jsonUrl": "/data/evaluations/latest_evaluation.json",
            "htmlUrl": "/data/evaluations/latest_evaluation.html",
            "assetsUrl": "/data/evaluations/latest_assets",
        },
    }

    _write_json(os.path.join(run_dir, "report.json"), report)
    html = _build_html_report(report)
    with open(os.path.join(run_dir, "report.html"), "w", encoding="utf-8") as handle:
        handle.write(html)
    _copy_latest_run(run_dir)

    report["reportPaths"]["latestJsonPath"] = LATEST_EVALUATION_PATH
    report["reportPaths"]["latestHtmlPath"] = LATEST_EVALUATION_HTML_PATH
    return report

