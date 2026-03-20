"""
Adaptive confidence scoring and temporal guardrails for interpolation jobs.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as structural_similarity

logger = logging.getLogger(__name__)

MAX_INTERPOLATION_GAP_MINUTES = 30
CONFIDENCE_WEIGHTS = {"ssim": 0.65, "mad": 0.35}
FALLBACK_SSIM_RANGE = (0.55, 0.90)
FALLBACK_MAD_RANGE = (6.0, 32.0)


def parse_timestamp(value: str) -> Optional[datetime]:
    """Best-effort parser for catalog timestamps."""
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(normalized)
        return _normalize_timezone(dt)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y%m%d", "%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%S"):
        try:
            return _normalize_timezone(datetime.strptime(normalized, fmt))
        except ValueError:
            continue
    return None


def format_timestamp(value: datetime) -> str:
    """Serialize timestamps consistently for API/UI use."""
    if value.hour == 0 and value.minute == 0 and value.second == 0:
        return value.strftime("%Y-%m-%d")
    return value.strftime("%Y-%m-%d %H:%M")


def midpoint_timestamp(left: str, right: str) -> Optional[str]:
    """Return the midpoint timestamp between two catalog timestamps."""
    left_dt = parse_timestamp(left)
    right_dt = parse_timestamp(right)
    if left_dt is None or right_dt is None:
        return None
    mid = left_dt + (right_dt - left_dt) / 2
    return format_timestamp(mid)


def gap_minutes_between(left: str, right: str) -> Optional[float]:
    """Return the gap duration in minutes between two timestamps."""
    left_dt = parse_timestamp(left)
    right_dt = parse_timestamp(right)
    if left_dt is None or right_dt is None:
        return None
    return abs((right_dt - left_dt).total_seconds()) / 60.0


def recommended_interpolation_frames(gap_minutes: Optional[float]) -> int:
    """Return the PRD-compliant frame cap for a temporal gap."""
    if gap_minutes is None:
        return 0
    if gap_minutes <= 5:
        return 15
    if gap_minutes <= 10:
        return 9
    if gap_minutes <= 15:
        return 5
    if gap_minutes <= MAX_INTERPOLATION_GAP_MINUTES:
        return 2
    return 0


def classify_confidence(value: float) -> str:
    """Map confidence values to UI labels."""
    if value >= 0.85:
        return "HIGH"
    if value >= 0.65:
        return "MEDIUM"
    if value >= 0.45:
        return "LOW"
    return "REJECTED"


def build_session_confidence_profile(original_frames: List[dict]) -> dict:
    """
    Build session-specific normalization statistics from observed frames.
    """
    sorted_frames = [
        frame for frame in sorted(
            original_frames,
            key=lambda item: parse_timestamp(item["timestamp"]) or datetime.min
        )
        if os.path.exists(frame["path"])
    ]

    baseline_ssim: List[float] = []
    baseline_mad: List[float] = []
    for left, right in zip(sorted_frames[:10], sorted_frames[1:10]):
        try:
            metrics = _compute_pair_metrics(left["path"], right["path"])
        except Exception:
            logger.exception("Failed to compute baseline confidence metrics")
            continue
        baseline_ssim.append(metrics["ssim"])
        baseline_mad.append(metrics["mad"])

    used_fallback = len(baseline_ssim) < 1 or len(sorted_frames) < 5
    if used_fallback:
        ssim_floor, ssim_ceiling = FALLBACK_SSIM_RANGE
        mad_floor, mad_ceiling = FALLBACK_MAD_RANGE
    else:
        ssim_floor = float(np.percentile(baseline_ssim, 10))
        ssim_ceiling = float(np.percentile(baseline_ssim, 90))
        mad_floor = float(np.percentile(baseline_mad, 10))
        mad_ceiling = float(np.percentile(baseline_mad, 90))

    profile = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sampleCount": len(sorted_frames),
        "baselinePairs": len(baseline_ssim),
        "usedFallbackDefaults": used_fallback,
        "weights": CONFIDENCE_WEIGHTS,
        "ssimFloor": round(ssim_floor, 4),
        "ssimCeiling": round(max(ssim_ceiling, ssim_floor + 1e-6), 4),
        "madFloor": round(mad_floor, 4),
        "madCeiling": round(max(mad_ceiling, mad_floor + 1e-6), 4),
        "meanBaselineSSIM": round(float(np.mean(baseline_ssim)), 4) if baseline_ssim else None,
        "meanBaselineMAD": round(float(np.mean(baseline_mad)), 4) if baseline_mad else None,
        "labelThresholds": {
            "HIGH": 0.85,
            "MEDIUM": 0.65,
            "LOW": 0.45,
            "REJECTED": 0.0,
        },
    }
    return profile


def persist_session_confidence_profile(profile: dict, metadata_dir: str) -> str:
    """Persist the active confidence profile for diagnostics/auditability."""
    os.makedirs(metadata_dir, exist_ok=True)
    output_path = os.path.join(metadata_dir, "session_confidence_profile.json")
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(profile, handle, indent=2)
    return output_path


def score_generated_frame(
    generated_path: str,
    source_frame0_path: str,
    source_frame1_path: str,
    gap_minutes: Optional[float],
    session_profile: dict,
) -> dict:
    """
    Score a generated frame against its two observed bounding frames.
    """
    metrics0 = _compute_pair_metrics(generated_path, source_frame0_path)
    metrics1 = _compute_pair_metrics(generated_path, source_frame1_path)

    avg_ssim = (metrics0["ssim"] + metrics1["ssim"]) / 2.0
    avg_mad = (metrics0["mad"] + metrics1["mad"]) / 2.0

    ssim_score = _normalize_high(
        avg_ssim,
        session_profile["ssimFloor"],
        session_profile["ssimCeiling"],
    )
    mad_score = _normalize_low(
        avg_mad,
        session_profile["madFloor"],
        session_profile["madCeiling"],
    )

    confidence = (
        CONFIDENCE_WEIGHTS["ssim"] * ssim_score
        + CONFIDENCE_WEIGHTS["mad"] * mad_score
    )

    # Conservative PRD-style cap for longer accepted gaps.
    if gap_minutes is not None:
        if gap_minutes > 20:
            confidence = min(confidence, 0.84)
        elif gap_minutes > 15:
            confidence = min(confidence, 0.64)

    conservative_confidence = min(confidence, ssim_score, mad_score)
    conservative_confidence = float(np.clip(conservative_confidence, 0.0, 1.0))
    label = classify_confidence(conservative_confidence)

    return {
        "confidence": round(conservative_confidence, 4),
        "confidenceLabel": label,
        "metrics": {
            "ssimToFrame0": round(metrics0["ssim"], 4),
            "ssimToFrame1": round(metrics1["ssim"], 4),
            "madToFrame0": round(metrics0["mad"], 4),
            "madToFrame1": round(metrics1["mad"], 4),
            "avgSSIM": round(avg_ssim, 4),
            "avgMAD": round(avg_mad, 4),
            "normalizedSSIM": round(ssim_score, 4),
            "normalizedMAD": round(mad_score, 4),
        },
        "gapMinutes": round(gap_minutes, 2) if gap_minutes is not None else None,
        "confidenceMethod": "Adaptive weighted SSIM/MAD",
    }


def _compute_pair_metrics(image_a_path: str, image_b_path: str) -> dict:
    """Compute SSIM and MAD between two image files."""
    img_a = _load_bgr(image_a_path)
    img_b = _load_bgr(image_b_path)
    if img_a.shape[:2] != img_b.shape[:2]:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))

    min_dim = min(img_a.shape[0], img_a.shape[1])
    win_size = min(7, min_dim)
    if win_size % 2 == 0:
        win_size -= 1
    ssim_value = structural_similarity(
        img_a,
        img_b,
        channel_axis=2,
        data_range=255,
        win_size=max(win_size, 3),
    )
    mad_value = float(np.mean(np.abs(img_a.astype(np.float32) - img_b.astype(np.float32))))
    return {"ssim": float(ssim_value), "mad": mad_value}


def _load_bgr(path: str) -> np.ndarray:
    """Load an image as BGR with alpha stripped if present."""
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.shape[2] == 4:
        return img[:, :, :3]
    return img


def _normalize_high(value: float, floor: float, ceiling: float) -> float:
    """Normalize a larger-is-better metric into [0, 1]."""
    span = max(ceiling - floor, 1e-6)
    return float(np.clip((value - floor) / span, 0.0, 1.0))


def _normalize_low(value: float, floor: float, ceiling: float) -> float:
    """Normalize a smaller-is-better metric into [0, 1]."""
    span = max(ceiling - floor, 1e-6)
    return float(np.clip(1.0 - ((value - floor) / span), 0.0, 1.0))


def _normalize_timezone(value: datetime) -> datetime:
    """Return naive UTC-like datetimes for consistent arithmetic."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
