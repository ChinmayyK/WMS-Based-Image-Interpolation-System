"""
PRD v2.0 statistical plausibility and adaptive confidence module.
"""
from __future__ import annotations

import json
import logging
import math
import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import cv2
import numpy as np
from skimage.metrics import structural_similarity as structural_similarity


logger = logging.getLogger(__name__)

MAX_INTERPOLATION_GAP_MINUTES = 30

LABEL_ORDER = {"REJECTED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
PROVENANCE_LABELS = {
    "OBSERVED": "OBSERVED",
    "HIGH": "INTERPOLATED_HIGH",
    "MEDIUM": "INTERPOLATED_MEDIUM",
    "LOW": "INTERPOLATED_LOW",
    "REJECTED": "REJECTED",
    "GAP": "GAP",
}

FALLBACK_THRESHOLDS = {
    "ssim_high": 0.85,
    "ssim_medium": 0.70,
    "ssim_low": 0.60,
    "epe_adaptive": 1.25,
    "mad_adaptive": 18.0,
    "intensity_high_pct": 5.0,
    "intensity_medium_pct": 10.0,
    "intensity_low_pct": 15.0,
}
SSIM_HIGH_MARGIN = 0.004
SSIM_MEDIUM_MARGIN = 0.008


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
    """Map scalar confidence values to UI labels."""
    if value >= 0.85:
        return "HIGH"
    if value >= 0.65:
        return "MEDIUM"
    if value >= 0.45:
        return "LOW"
    return "REJECTED"


def provenance_label_for(label: str) -> str:
    return PROVENANCE_LABELS.get(label, label)


def governed_confidence_label(label: str, gap_minutes: Optional[float], domain_flags: Optional[set[str]] = None) -> str:
    return _apply_runtime_caps(label, gap_minutes, domain_flags or set())


def build_session_confidence_profile(original_frames: List[dict]) -> dict:
    """
    Build adaptive baseline statistics from the first 10 original frames.
    """
    sorted_frames = [
        frame
        for frame in sorted(
            original_frames,
            key=lambda item: parse_timestamp(item["timestamp"]) or datetime.min,
        )
        if os.path.exists(frame["path"])
    ]

    baseline_ssim: List[float] = []
    baseline_mad: List[float] = []
    baseline_epe: List[float] = []
    baseline_flow: List[float] = []

    for left, right in zip(sorted_frames[:10], sorted_frames[1:10]):
        try:
            pair_metrics = _compute_pair_metrics(
                left["path"],
                right["path"],
                mask_paths_a=_extract_mask_paths(left),
                mask_paths_b=_extract_mask_paths(right),
            )
            flow_metrics = _compute_flow_inconsistency(
                left["path"],
                right["path"],
                mask_paths_a=_extract_mask_paths(left),
                mask_paths_b=_extract_mask_paths(right),
            )
        except Exception:
            logger.exception("Failed to compute baseline confidence metrics")
            continue

        baseline_ssim.append(pair_metrics["ssim"])
        baseline_mad.append(pair_metrics["mad"])
        baseline_epe.append(flow_metrics["meanEPE"])
        baseline_flow.append(flow_metrics["meanMagnitude"])

    used_fallback = len(sorted_frames) < 5 or len(baseline_ssim) < 1
    if used_fallback:
        thresholds = dict(FALLBACK_THRESHOLDS)
        ssim_floor = thresholds["ssim_low"]
        ssim_ceiling = thresholds["ssim_high"]
        mad_floor = 0.0
        mad_ceiling = thresholds["mad_adaptive"] * 2.0
    else:
        ssim_floor = max(float(np.percentile(baseline_ssim, 10)), FALLBACK_THRESHOLDS["ssim_low"])
        ssim_ceiling = max(float(np.percentile(baseline_ssim, 90)), FALLBACK_THRESHOLDS["ssim_high"])
        mad_floor = float(np.percentile(baseline_mad, 10))
        mad_ceiling = float(np.percentile(baseline_mad, 90))
        thresholds = {
            # Interpolated midpoints are expected to be slightly less similar to either endpoint
            # than two adjacent observed frames are to each other, so widen the adaptive SSIM gate.
            "ssim_high": max(0.85, float(np.percentile(baseline_ssim, 80)) - SSIM_HIGH_MARGIN),
            "ssim_medium": max(0.70, float(np.percentile(baseline_ssim, 55)) - SSIM_MEDIUM_MARGIN),
            "ssim_low": 0.60,
            "epe_adaptive": max(FALLBACK_THRESHOLDS["epe_adaptive"], float(np.percentile(baseline_epe, 90))) if baseline_epe else FALLBACK_THRESHOLDS["epe_adaptive"],
            "mad_adaptive": max(FALLBACK_THRESHOLDS["mad_adaptive"], float(np.percentile(baseline_mad, 95))),
            "intensity_high_pct": 5.0,
            "intensity_medium_pct": 10.0,
            "intensity_low_pct": 15.0,
        }
        thresholds["ssim_medium"] = min(thresholds["ssim_medium"], thresholds["ssim_high"] - 1e-4)

    profile = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sampleCount": len(sorted_frames),
        "baselinePairs": len(baseline_ssim),
        "usedFallbackDefaults": used_fallback,
        "ssimFloor": round(float(ssim_floor), 4),
        "ssimCeiling": round(float(max(ssim_ceiling, ssim_floor + 1e-6)), 4),
        "madFloor": round(float(mad_floor), 4),
        "madCeiling": round(float(max(mad_ceiling, mad_floor + 1e-6)), 4),
        "meanBaselineSSIM": round(float(np.mean(baseline_ssim)), 4) if baseline_ssim else None,
        "meanBaselineMAD": round(float(np.mean(baseline_mad)), 4) if baseline_mad else None,
        "meanBaselineEPE": round(float(np.mean(baseline_epe)), 4) if baseline_epe else None,
        "flowMagnitudeP90": round(float(np.percentile(baseline_flow, 90)), 4) if baseline_flow else None,
        "thresholds": {
            key: round(float(value), 4) for key, value in thresholds.items()
        },
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


def score_generated_sequence(
    generated_records: list[dict],
    source_frame0_path: str,
    source_frame1_path: str,
    gap_minutes: Optional[float],
    session_profile: dict,
    *,
    source_frame0: Optional[dict] = None,
    source_frame1: Optional[dict] = None,
) -> list[dict]:
    """
    Score a recursively generated sequence using PRD statistical-plausibility rules.
    """
    sorted_records = sorted(generated_records, key=lambda item: item.get("ratio", 0.5))
    if not sorted_records:
        return []

    source0_descriptor = {"path": source_frame0_path, **(source_frame0 or {})}
    source1_descriptor = {"path": source_frame1_path, **(source_frame1 or {})}
    sequence_nodes = [source0_descriptor] + sorted_records + [source1_descriptor]

    transition_mads: list[float] = []
    for left, right in zip(sequence_nodes, sequence_nodes[1:]):
        transition_mads.append(
            _compute_pair_metrics(
                left["path"],
                right["path"],
                mask_paths_a=_extract_mask_paths(left),
                mask_paths_b=_extract_mask_paths(right),
            )["mad"]
        )

    scores = []
    for index, record in enumerate(sorted_records):
        ratio = float(record.get("ratio", 0.5))
        mask_paths_generated = _extract_mask_paths(record)
        pair0 = _compute_pair_metrics(
            record["path"],
            source_frame0_path,
            mask_paths_a=mask_paths_generated,
            mask_paths_b=_extract_mask_paths(source0_descriptor),
        )
        pair1 = _compute_pair_metrics(
            record["path"],
            source_frame1_path,
            mask_paths_a=mask_paths_generated,
            mask_paths_b=_extract_mask_paths(source1_descriptor),
        )
        flow0 = _compute_flow_inconsistency(
            source_frame0_path,
            record["path"],
            mask_paths_a=_extract_mask_paths(source0_descriptor),
            mask_paths_b=mask_paths_generated,
        )
        flow1 = _compute_flow_inconsistency(
            record["path"],
            source_frame1_path,
            mask_paths_a=mask_paths_generated,
            mask_paths_b=_extract_mask_paths(source1_descriptor),
        )

        avg_ssim = (pair0["ssim"] + pair1["ssim"]) / 2.0
        source_mad = (pair0["mad"] + pair1["mad"]) / 2.0
        avg_epe = (flow0["meanEPE"] + flow1["meanEPE"]) / 2.0
        intensity_deviation_pct = _compute_intensity_deviation(
            record["path"],
            source_frame0_path,
            source_frame1_path,
            ratio,
            generated_mask_paths=mask_paths_generated,
            source_mask_paths_0=_extract_mask_paths(source0_descriptor),
            source_mask_paths_1=_extract_mask_paths(source1_descriptor),
        )
        sequential_mad = max(transition_mads[index], transition_mads[index + 1])
        thresholds = session_profile.get("thresholds") or FALLBACK_THRESHOLDS
        candidate_labels = {
            "ssim": _label_from_ssim(avg_ssim, thresholds),
            "epe": _label_from_epe(avg_epe, thresholds),
            "mad": _label_from_mad(sequential_mad, thresholds),
            "intensity": _label_from_intensity(intensity_deviation_pct, thresholds),
        }
        domain_flags = _collect_domain_flags(source_frame0, source_frame1)

        final_label = _most_conservative_label(candidate_labels.values())
        final_label = _apply_runtime_caps(final_label, gap_minutes, domain_flags)
        confidence_value = _confidence_from_metrics(
            avg_ssim,
            sequential_mad,
            avg_epe,
            intensity_deviation_pct,
            thresholds,
            final_label,
        )

        scores.append(
            {
                "confidence": round(confidence_value, 4),
                "confidenceLabel": final_label,
                "provenanceLabel": provenance_label_for(final_label),
                "metrics": {
                    "ssimToFrame0": round(pair0["ssim"], 4),
                    "ssimToFrame1": round(pair1["ssim"], 4),
                    "avgSSIM": round(avg_ssim, 4),
                    "madToFrame0": round(pair0["mad"], 4),
                    "madToFrame1": round(pair1["mad"], 4),
                    "avgMADToSources": round(source_mad, 4),
                    "sequentialMAD": round(sequential_mad, 4),
                    "epeToFrame0": round(flow0["meanEPE"], 4),
                    "epeToFrame1": round(flow1["meanEPE"], 4),
                    "avgEPE": round(avg_epe, 4),
                    "intensityDeviationPct": round(intensity_deviation_pct, 4),
                    "flowMagnitudeToFrame0": round(flow0["meanMagnitude"], 4),
                    "flowMagnitudeToFrame1": round(flow1["meanMagnitude"], 4),
                    "candidateLabels": candidate_labels,
                    "thresholds": {
                        key: round(float(value), 4) for key, value in thresholds.items()
                    },
                    "domainFlags": sorted(domain_flags),
                },
                "gapMinutes": round(gap_minutes, 2) if gap_minutes is not None else None,
                "confidenceMethod": "Statistical plausibility module (SSIM/EPE/MAD/Intensity)",
            }
        )

    return scores


def score_generated_frame(
    generated_path: str,
    source_frame0_path: str,
    source_frame1_path: str,
    gap_minutes: Optional[float],
    session_profile: dict,
    *,
    source_frame0: Optional[dict] = None,
    source_frame1: Optional[dict] = None,
    generated_frame: Optional[dict] = None,
) -> dict:
    """
    Backward-compatible single-frame scoring wrapper.
    """
    generated_descriptor = {"path": generated_path, "ratio": 0.5}
    if generated_frame:
        generated_descriptor.update(generated_frame)
    scores = score_generated_sequence(
        [generated_descriptor],
        source_frame0_path,
        source_frame1_path,
        gap_minutes,
        session_profile,
        source_frame0=source_frame0,
        source_frame1=source_frame1,
    )
    return scores[0]


def _compute_pair_metrics(
    image_a_path: str,
    image_b_path: str,
    *,
    mask_paths_a: Optional[dict] = None,
    mask_paths_b: Optional[dict] = None,
) -> dict:
    img_a, mask_a = _load_bgr_with_mask(image_a_path, mask_paths=mask_paths_a)
    img_b, mask_b = _load_bgr_with_mask(image_b_path, mask_paths=mask_paths_b)
    if img_a.shape[:2] != img_b.shape[:2]:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]), interpolation=cv2.INTER_LINEAR)
        mask_b = cv2.resize(mask_b.astype(np.uint8), (img_a.shape[1], img_a.shape[0]), interpolation=cv2.INTER_NEAREST) > 0

    common_mask = mask_a & mask_b
    if not np.any(common_mask):
        return {"ssim": 0.0, "mad": 255.0}

    rows, cols = np.where(common_mask)
    min_row, max_row = rows.min(), rows.max()
    min_col, max_col = cols.min(), cols.max()

    crop_a = img_a[min_row:max_row + 1, min_col:max_col + 1].copy()
    crop_b = img_b[min_row:max_row + 1, min_col:max_col + 1].copy()
    crop_mask = common_mask[min_row:max_row + 1, min_col:max_col + 1]
    crop_a[~crop_mask] = 0
    crop_b[~crop_mask] = 0

    min_dim = min(crop_a.shape[0], crop_a.shape[1])
    win_size = min(7, min_dim)
    if win_size % 2 == 0:
        win_size -= 1

    ssim_value = structural_similarity(
        crop_a,
        crop_b,
        channel_axis=2,
        data_range=255,
        win_size=max(win_size, 3),
    )
    mad_value = float(
        np.mean(
            np.abs(
                img_a[common_mask].astype(np.float32) - img_b[common_mask].astype(np.float32)
            )
        )
    )
    return {"ssim": float(ssim_value), "mad": mad_value}


def _compute_flow_inconsistency(
    image_a_path: str,
    image_b_path: str,
    *,
    mask_paths_a: Optional[dict] = None,
    mask_paths_b: Optional[dict] = None,
) -> dict:
    img_a, mask_a = _load_bgr_with_mask(image_a_path, mask_paths=mask_paths_a)
    img_b, mask_b = _load_bgr_with_mask(image_b_path, mask_paths=mask_paths_b)
    if img_a.shape[:2] != img_b.shape[:2]:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]), interpolation=cv2.INTER_LINEAR)
        mask_b = cv2.resize(mask_b.astype(np.uint8), (img_a.shape[1], img_a.shape[0]), interpolation=cv2.INTER_NEAREST) > 0

    common_mask = mask_a & mask_b
    if not np.any(common_mask):
        return {"meanEPE": 999.0, "p90EPE": 999.0, "meanMagnitude": 0.0}

    gray_a = cv2.cvtColor(img_a, cv2.COLOR_BGR2GRAY)
    gray_b = cv2.cvtColor(img_b, cv2.COLOR_BGR2GRAY)
    flow_ab = cv2.calcOpticalFlowFarneback(
        gray_a,
        gray_b,
        None,
        pyr_scale=0.5,
        levels=3,
        winsize=25,
        iterations=5,
        poly_n=7,
        poly_sigma=1.5,
        flags=0,
    )
    flow_ba = cv2.calcOpticalFlowFarneback(
        gray_b,
        gray_a,
        None,
        pyr_scale=0.5,
        levels=3,
        winsize=25,
        iterations=5,
        poly_n=7,
        poly_sigma=1.5,
        flags=0,
    )

    height, width = gray_a.shape
    grid_x, grid_y = np.meshgrid(np.arange(width, dtype=np.float32), np.arange(height, dtype=np.float32))
    map_x = grid_x + flow_ab[:, :, 0]
    map_y = grid_y + flow_ab[:, :, 1]

    sampled_ba_x = cv2.remap(flow_ba[:, :, 0], map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    sampled_ba_y = cv2.remap(flow_ba[:, :, 1], map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    fb_error = np.sqrt((flow_ab[:, :, 0] + sampled_ba_x) ** 2 + (flow_ab[:, :, 1] + sampled_ba_y) ** 2)
    magnitude = np.sqrt(flow_ab[:, :, 0] ** 2 + flow_ab[:, :, 1] ** 2)

    valid_coords = (
        common_mask
        & (map_x >= 0)
        & (map_x < width)
        & (map_y >= 0)
        & (map_y < height)
    )
    if not np.any(valid_coords):
        return {"meanEPE": 999.0, "p90EPE": 999.0, "meanMagnitude": 0.0}

    epe_values = fb_error[valid_coords]
    magnitude_values = magnitude[valid_coords]
    return {
        "meanEPE": float(epe_values.mean()),
        "p90EPE": float(np.percentile(epe_values, 90)),
        "meanMagnitude": float(magnitude_values.mean()),
    }


def _compute_intensity_deviation(
    generated_path: str,
    source_frame0_path: str,
    source_frame1_path: str,
    ratio: float,
    *,
    generated_mask_paths: Optional[dict] = None,
    source_mask_paths_0: Optional[dict] = None,
    source_mask_paths_1: Optional[dict] = None,
) -> float:
    generated, generated_valid = _load_bgr_with_mask(generated_path, mask_paths=generated_mask_paths)
    source0, source0_valid = _load_bgr_with_mask(source_frame0_path, mask_paths=source_mask_paths_0)
    source1, source1_valid = _load_bgr_with_mask(source_frame1_path, mask_paths=source_mask_paths_1)

    if source0.shape[:2] != generated.shape[:2]:
        source0 = cv2.resize(source0, (generated.shape[1], generated.shape[0]), interpolation=cv2.INTER_LINEAR)
        source0_valid = cv2.resize(source0_valid.astype(np.uint8), (generated.shape[1], generated.shape[0]), interpolation=cv2.INTER_NEAREST) > 0
    if source1.shape[:2] != generated.shape[:2]:
        source1 = cv2.resize(source1, (generated.shape[1], generated.shape[0]), interpolation=cv2.INTER_LINEAR)
        source1_valid = cv2.resize(source1_valid.astype(np.uint8), (generated.shape[1], generated.shape[0]), interpolation=cv2.INTER_NEAREST) > 0

    valid = generated_valid & source0_valid & source1_valid
    if not np.any(valid):
        return 100.0

    generated_sum = float(generated[valid].astype(np.float32).sum())
    source0_sum = float(source0[valid].astype(np.float32).sum())
    source1_sum = float(source1[valid].astype(np.float32).sum())
    expected = (1.0 - ratio) * source0_sum + ratio * source1_sum
    if expected <= 1e-6:
        return 0.0
    return abs(generated_sum - expected) / expected * 100.0


def _confidence_from_metrics(
    avg_ssim: float,
    sequential_mad: float,
    avg_epe: float,
    intensity_deviation_pct: float,
    thresholds: dict,
    label: str,
) -> float:
    ssim_score = np.clip((avg_ssim - thresholds["ssim_low"]) / max(thresholds["ssim_high"] - thresholds["ssim_low"], 1e-6), 0.0, 1.0)
    mad_score = np.clip(1.0 - (sequential_mad / max(thresholds["mad_adaptive"] * 3.0, 1e-6)), 0.0, 1.0)
    epe_score = np.clip(1.0 - (avg_epe / max(thresholds["epe_adaptive"] * 2.0, 1e-6)), 0.0, 1.0)
    intensity_score = np.clip(1.0 - (intensity_deviation_pct / max(thresholds["intensity_low_pct"], 1e-6)), 0.0, 1.0)
    base = float(np.mean([ssim_score, mad_score, epe_score, intensity_score]))
    cap = {"HIGH": 1.0, "MEDIUM": 0.84, "LOW": 0.64, "REJECTED": 0.44}.get(label, 0.44)
    floor = {"HIGH": 0.85, "MEDIUM": 0.65, "LOW": 0.45, "REJECTED": 0.0}.get(label, 0.0)
    return float(np.clip(min(base, cap), floor, cap))


def _label_from_ssim(value: float, thresholds: dict) -> str:
    if value >= thresholds["ssim_high"]:
        return "HIGH"
    if value >= thresholds["ssim_medium"]:
        return "MEDIUM"
    if value >= thresholds["ssim_low"]:
        return "LOW"
    return "REJECTED"


def _label_from_epe(value: float, thresholds: dict) -> str:
    adaptive = max(thresholds["epe_adaptive"], 1e-6)
    if value < adaptive:
        return "HIGH"
    if value < adaptive * 1.5:
        return "MEDIUM"
    if value < adaptive * 2.0:
        return "LOW"
    return "REJECTED"


def _label_from_mad(value: float, thresholds: dict) -> str:
    adaptive = max(thresholds["mad_adaptive"], 1e-6)
    if value < adaptive * 0.75:
        return "HIGH"
    if value < adaptive:
        return "MEDIUM"
    if value < adaptive * 3.0:
        return "LOW"
    return "REJECTED"


def _label_from_intensity(value: float, thresholds: dict) -> str:
    if value < thresholds["intensity_high_pct"]:
        return "HIGH"
    if value < thresholds["intensity_medium_pct"]:
        return "MEDIUM"
    if value < thresholds["intensity_low_pct"]:
        return "LOW"
    return "REJECTED"


def _most_conservative_label(labels) -> str:
    resolved = [label for label in labels if label in LABEL_ORDER]
    if not resolved:
        return "REJECTED"
    return min(resolved, key=lambda item: LABEL_ORDER[item])


def _apply_runtime_caps(label: str, gap_minutes: Optional[float], domain_flags: set[str]) -> str:
    capped = label
    if gap_minutes is not None:
        if gap_minutes > 20:
            capped = _cap_label(capped, "MEDIUM")
        elif gap_minutes > 15:
            capped = _cap_label(capped, "LOW")

    if "CALIBRATION_SHIFT" in domain_flags:
        capped = _cap_label(capped, "LOW")
    if "LIMB" in domain_flags or "TERMINATOR" in domain_flags:
        capped = _cap_label(capped, "MEDIUM")
    return capped


def _cap_label(label: str, ceiling: str) -> str:
    if LABEL_ORDER.get(label, 0) > LABEL_ORDER.get(ceiling, 0):
        return ceiling
    return label


def _collect_domain_flags(frame0: Optional[dict], frame1: Optional[dict]) -> set[str]:
    flags = set()
    for frame in (frame0 or {}, frame1 or {}):
        for key in ("flags", "preprocessingFlags"):
            values = frame.get(key) or []
            flags.update(str(value) for value in values)
    return flags


def _extract_mask_paths(payload: Optional[dict]) -> dict:
    payload = payload or {}
    mask_info = payload.get("maskInfo") or payload.get("masks") or {}
    resolved = {}
    for key in ("nodata", "limb", "terminator"):
        direct_key = f"{key}MaskPath"
        if payload.get(direct_key):
            resolved[key] = payload[direct_key]
            continue
        nested = mask_info.get(key) or {}
        if nested.get("path"):
            resolved[key] = nested["path"]
    return resolved


def _load_bgr_with_mask(path: str, *, mask_paths: Optional[dict] = None) -> tuple[np.ndarray, np.ndarray]:
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(path)
    if img.ndim == 2:
        bgr = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        valid_mask = np.ones(img.shape[:2], dtype=bool)
    elif img.shape[2] == 4:
        bgr = img[:, :, :3]
        valid_mask = img[:, :, 3] >= 64
    else:
        bgr = img
        valid_mask = np.ones(img.shape[:2], dtype=bool)

    for mask_path in (mask_paths or {}).values():
        if not mask_path or not os.path.exists(mask_path):
            continue
        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            continue
        if mask.shape[:2] != valid_mask.shape[:2]:
            mask = cv2.resize(mask, (valid_mask.shape[1], valid_mask.shape[0]), interpolation=cv2.INTER_NEAREST)
        valid_mask &= mask < 127

    return bgr, valid_mask


def _normalize_timezone(value: datetime) -> datetime:
    """Return naive UTC-like datetimes for consistent arithmetic."""
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value
