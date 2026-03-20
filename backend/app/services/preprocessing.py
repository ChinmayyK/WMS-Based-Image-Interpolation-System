"""
PRD v2.0 preprocessing pipeline for observed GOES sessions.

This module validates spatial and temporal consistency, derives scientific
quality masks, performs session-wide radiometric normalization, and persists a
session-level report consumed by the API and interpolation pipeline.
"""
from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from datetime import timedelta
from typing import Optional

import cv2
import numpy as np

from app.services.confidence import format_timestamp, parse_timestamp
from app.services.metadata import get_metadata_dir


logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
METADATA_DIR = get_metadata_dir()
PREPROCESSED_FRAMES_DIR = os.path.join(DATA_DIR, "preprocessed_frames")
NODATA_MASKS_DIR = os.path.join(DATA_DIR, "nodata_masks")
LIMB_MASKS_DIR = os.path.join(DATA_DIR, "limb_masks")
TERMINATOR_MASKS_DIR = os.path.join(DATA_DIR, "terminator_masks")
PREPROCESSING_REPORT_PATH = os.path.join(METADATA_DIR, "preprocessing_report.json")

PREPROCESSING_VERSION = "2.0"
EXPECTED_CRS = "EPSG:3857"
NODATA_INTENSITY_THRESHOLD = 1
TEMPORAL_TOLERANCE_RATIO = 0.2
MIN_TEMPORAL_TOLERANCE_MINUTES = 1.0
LIMB_BAND_RADIUS = 8
MIN_VALID_PIXEL_RATIO = 0.80
MAX_TERMINATOR_RATIO = 0.04
MIN_BORDER_COMPONENT_PIXELS = 64
MIN_INTERNAL_COMPONENT_RATIO = 0.01


class PreprocessingError(Exception):
    pass


def get_preprocessing_report_path() -> str:
    return PREPROCESSING_REPORT_PATH


def load_preprocessing_report() -> Optional[dict]:
    if not os.path.exists(PREPROCESSING_REPORT_PATH):
        return None
    with open(PREPROCESSING_REPORT_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _persist_preprocessing_report(report: dict) -> str:
    os.makedirs(METADATA_DIR, exist_ok=True)
    with open(PREPROCESSING_REPORT_PATH, "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    return PREPROCESSING_REPORT_PATH


def ensure_session_preprocessed(session_metadata: dict, *, force: bool = False) -> dict:
    """
    Run the preprocessing pipeline once for the active observed session.
    """
    if not session_metadata:
        raise PreprocessingError("Observed session metadata is required for preprocessing.")

    if not force:
        preprocessing_meta = session_metadata.get("preprocessing") or {}
        if preprocessing_meta.get("version") == PREPROCESSING_VERSION and os.path.exists(PREPROCESSING_REPORT_PATH):
            return session_metadata

    return preprocess_observed_session(session_metadata)


def preprocess_observed_session(session_metadata: dict) -> dict:
    os.makedirs(PREPROCESSED_FRAMES_DIR, exist_ok=True)
    os.makedirs(NODATA_MASKS_DIR, exist_ok=True)
    os.makedirs(LIMB_MASKS_DIR, exist_ok=True)
    os.makedirs(TERMINATOR_MASKS_DIR, exist_ok=True)

    session = deepcopy(session_metadata)
    frames = session.get("frames") or []
    if not frames:
        raise PreprocessingError("Observed session contains no frames to preprocess.")

    reference_bbox = session.get("bbox")
    reference_crs = session.get("crs") or EXPECTED_CRS
    original_timestamps = [frame.get("timestamp") for frame in frames if frame.get("timestamp")]

    processed_frames = []
    reference_dimensions = None
    spatially_valid_candidates = []

    for frame in frames:
        processed = _process_single_frame(
            frame,
            reference_bbox=reference_bbox,
            reference_crs=reference_crs,
            reference_dimensions=reference_dimensions,
        )
        if processed["decoded"] and reference_dimensions is None:
            reference_dimensions = (processed["width"], processed["height"])
            # Re-evaluate the first decodable frame against the now-known dimensions.
            if processed["width"] != reference_dimensions[0] or processed["height"] != reference_dimensions[1]:
                processed["issues"].append("DIMENSION_MISMATCH")
        elif processed["decoded"] and reference_dimensions is not None:
            if (processed["width"], processed["height"]) != reference_dimensions:
                processed["issues"].append("DIMENSION_MISMATCH")

        processed["issues"] = list(dict.fromkeys(processed["issues"]))
        processed["spatiallyValid"] = len(processed["issues"]) == 0
        processed_frames.append(processed)
        if processed["spatiallyValid"]:
            spatially_valid_candidates.append(processed)

    timeline_report = _build_timeline_report(original_timestamps)
    calibration_issues = _detect_calibration_shifts(spatially_valid_candidates)

    for issue in calibration_issues:
        frame = next((item for item in processed_frames if item["timestamp"] == issue["to"]), None)
        if frame is not None:
            frame["flags"].append("CALIBRATION_SHIFT")
            frame["calibrationShift"] = issue

    for frame in processed_frames:
        if frame["decoded"]:
            if frame["limbDetected"]:
                frame["flags"].append("LIMB")
            if frame["terminatorDetected"]:
                frame["flags"].append("TERMINATOR")
        frame["flags"] = list(dict.fromkeys(frame["flags"]))
        frame["valid"] = frame["decoded"] and len(frame["issues"]) == 0

    final_valid_frames = [frame for frame in processed_frames if frame["valid"]]
    session_min_intensity, session_max_intensity = _compute_session_intensity_range(final_valid_frames)

    for frame in processed_frames:
        if frame["decoded"]:
            _save_masks(frame)
        if frame["valid"]:
            _save_normalized_frame(frame, session_min_intensity, session_max_intensity)

    if not final_valid_frames:
        raise PreprocessingError("No scientifically valid frames remained after preprocessing.")

    average_nodata_ratio = float(np.mean([frame["nodataRatio"] for frame in processed_frames if frame["decoded"]])) if any(frame["decoded"] for frame in processed_frames) else 0.0
    report = {
        "version": PREPROCESSING_VERSION,
        "session_id": session.get("session_id"),
        "generated_at": session.get("createdAt"),
        "total_frames": len(processed_frames),
        "valid_frames": len(final_valid_frames),
        "missing_frames": len(timeline_report["missing"]),
        "missing_timestamps": timeline_report["missing"],
        "nodata_ratio": round(average_nodata_ratio, 6),
        "limb_detected": any(frame["limbDetected"] for frame in processed_frames),
        "terminator_detected": any(frame["terminatorDetected"] for frame in processed_frames),
        "calibration_issues": calibration_issues,
        "normalization": {
            "min_intensity": None if session_min_intensity is None else round(session_min_intensity, 6),
            "max_intensity": None if session_max_intensity is None else round(session_max_intensity, 6),
        },
        "timeline_report": timeline_report,
        "validation_results": [
            {
                "timestamp": frame["timestamp"],
                "valid": frame["valid"],
                "issues": frame["issues"],
                "flags": frame["flags"],
            }
            for frame in processed_frames
        ],
    }

    _persist_preprocessing_report(report)

    session["frames"] = [_serialize_frame_metadata(frame) for frame in processed_frames]
    session["preprocessing"] = {
        "version": PREPROCESSING_VERSION,
        "reportPath": PREPROCESSING_REPORT_PATH,
        "reportUrl": "/data/metadata/preprocessing_report.json",
        "timelineReport": timeline_report,
        "normalization": report["normalization"],
        "validFrameCount": len(final_valid_frames),
        "missingFrameCount": len(timeline_report["missing"]),
        "calibrationIssueCount": len(calibration_issues),
        "flaggedFrameCount": sum(1 for frame in processed_frames if frame["flags"]),
    }
    session["validationResults"] = report["validation_results"]
    return session


def _process_single_frame(
    frame: dict,
    *,
    reference_bbox: Optional[list[float]],
    reference_crs: str,
    reference_dimensions: Optional[tuple[int, int]],
) -> dict:
    path = frame.get("path")
    timestamp = frame.get("timestamp") or frame.get("wmsTime") or "unknown"
    issues: list[str] = []

    if (frame.get("crs") or reference_crs) != EXPECTED_CRS:
        issues.append("CRS_MISMATCH")
    if reference_bbox and not _bbox_matches(frame.get("bbox"), reference_bbox):
        issues.append("BBOX_MISMATCH")
    if not path or not os.path.exists(path):
        issues.append("MISSING_FILE")
        return {
            **frame,
            "timestamp": timestamp,
            "issues": issues,
            "flags": [],
            "valid": False,
            "decoded": False,
            "width": None,
            "height": None,
            "nodataRatio": 1.0,
            "limbDetected": False,
            "terminatorDetected": False,
        }

    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        issues.append("CORRUPTED_IMAGE")
        return {
            **frame,
            "timestamp": timestamp,
            "issues": issues,
            "flags": [],
            "valid": False,
            "decoded": False,
            "width": None,
            "height": None,
            "nodataRatio": 1.0,
            "limbDetected": False,
            "terminatorDetected": False,
        }

    rgba = _ensure_bgra(image)
    height, width = rgba.shape[:2]
    if reference_dimensions and (width, height) != reference_dimensions:
        issues.append("DIMENSION_MISMATCH")
    if width < 2 or height < 2:
        issues.append("INCOMPLETE_IMAGE")

    nodata_mask = detect_nodata_mask(rgba)
    valid_pixel_ratio = 1.0 - float(nodata_mask.mean())
    if valid_pixel_ratio < MIN_VALID_PIXEL_RATIO:
        issues.append("INSUFFICIENT_VALID_PIXELS")

    limb_mask, limb_detected, limb_ratio = _detect_limb_mask(rgba, nodata_mask)
    terminator_mask, terminator_detected, terminator_ratio = _detect_terminator_mask(rgba, nodata_mask, limb_mask)

    return {
        **frame,
        "timestamp": timestamp,
        "issues": issues,
        "flags": [],
        "valid": False,
        "decoded": True,
        "rgba": rgba,
        "width": width,
        "height": height,
        "nodataMask": nodata_mask,
        "limbMask": limb_mask,
        "terminatorMask": terminator_mask,
        "nodataRatio": round(float(nodata_mask.mean()), 6),
        "limbDetected": bool(limb_detected),
        "limbRatio": round(float(limb_ratio), 6),
        "terminatorDetected": bool(terminator_detected),
        "terminatorRatio": round(float(terminator_ratio), 6),
    }


def _serialize_frame_metadata(frame: dict) -> dict:
    serializable = {key: value for key, value in frame.items() if key not in {"rgba", "nodataMask", "limbMask", "terminatorMask", "spatiallyValid"}}
    serializable["type"] = frame.get("type", "OBSERVED")
    serializable["validation"] = {
        "valid": frame["valid"],
        "issues": list(frame["issues"]),
        "flags": list(frame.get("flags", [])),
    }
    serializable["flags"] = list(frame.get("flags", []))
    if frame.get("normalizedPath"):
        serializable["normalizedPath"] = frame["normalizedPath"]
        serializable["normalizedUrl"] = frame["normalizedUrl"]
    if frame.get("nodataMaskPath"):
        serializable["nodataMaskPath"] = frame["nodataMaskPath"]
        serializable["nodataMaskUrl"] = frame["nodataMaskUrl"]
    if frame.get("limbMaskPath"):
        serializable["limbMaskPath"] = frame["limbMaskPath"]
        serializable["limbMaskUrl"] = frame["limbMaskUrl"]
    if frame.get("terminatorMaskPath"):
        serializable["terminatorMaskPath"] = frame["terminatorMaskPath"]
        serializable["terminatorMaskUrl"] = frame["terminatorMaskUrl"]
    return serializable


def _bbox_matches(candidate: Optional[list[float]], expected: list[float], tolerance: float = 1e-3) -> bool:
    if candidate is None or len(candidate) != len(expected):
        return False
    return all(abs(float(left) - float(right)) <= tolerance for left, right in zip(candidate, expected))


def _ensure_bgra(image: np.ndarray) -> np.ndarray:
    if image.ndim == 2:
        return cv2.cvtColor(image, cv2.COLOR_GRAY2BGRA)
    if image.shape[2] == 4:
        return image
    if image.shape[2] == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2BGRA)
    raise PreprocessingError(f"Unsupported image shape: {image.shape}")


def _component_mask(
    candidate_mask: np.ndarray,
    *,
    min_area_pixels: int,
    require_border_touch: bool,
) -> np.ndarray:
    if not np.any(candidate_mask):
        return np.zeros_like(candidate_mask, dtype=bool)

    height, width = candidate_mask.shape
    component_mask = np.zeros_like(candidate_mask, dtype=bool)
    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(
        candidate_mask.astype(np.uint8),
        connectivity=8,
    )

    for label in range(1, component_count):
        x, y, w, h, area = stats[label]
        if area < min_area_pixels:
            continue
        touches_border = x == 0 or y == 0 or (x + w) >= width or (y + h) >= height
        if require_border_touch and not touches_border:
            continue
        component_mask |= labels == label

    return component_mask


def detect_nodata_mask(image: np.ndarray, black_threshold: int = NODATA_INTENSITY_THRESHOLD) -> np.ndarray:
    rgba = _ensure_bgra(image)
    rgb = rgba[:, :, :3]
    alpha_gap = rgba[:, :, 3] < 64
    strict_dark = np.max(rgb, axis=2) <= black_threshold

    border_dark = _component_mask(
        strict_dark,
        min_area_pixels=max(MIN_BORDER_COMPONENT_PIXELS, int(strict_dark.size * 0.00005)),
        require_border_touch=True,
    )

    internal_dark = np.zeros_like(strict_dark, dtype=bool)
    if np.any(alpha_gap):
        # Internal opaque voids only count as NoData when there is other explicit gap evidence.
        internal_dark = _component_mask(
            strict_dark,
            min_area_pixels=max(256, int(strict_dark.size * MIN_INTERNAL_COMPONENT_RATIO)),
            require_border_touch=False,
        )

    return alpha_gap | border_dark | internal_dark


def _detect_limb_mask(image: np.ndarray, nodata_mask: np.ndarray) -> tuple[np.ndarray, bool, float]:
    valid_mask = (~nodata_mask).astype(np.uint8) * 255
    if not np.any(valid_mask):
        return np.zeros_like(nodata_mask, dtype=bool), False, 0.0

    border = np.concatenate([nodata_mask[0, :], nodata_mask[-1, :], nodata_mask[:, 0], nodata_mask[:, -1]])
    if float(border.mean()) < 0.01:
        return np.zeros_like(nodata_mask, dtype=bool), False, 0.0

    closed = cv2.morphologyEx(
        valid_mask,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)),
    )
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return np.zeros_like(nodata_mask, dtype=bool), False, 0.0

    contour = max(contours, key=cv2.contourArea)
    filled = np.zeros_like(valid_mask)
    if len(contour) >= 5:
        ellipse = cv2.fitEllipse(contour)
        cv2.ellipse(filled, ellipse, 255, -1)
    else:
        cv2.drawContours(filled, [contour], -1, 255, thickness=-1)

    outer_region = filled == 0
    if float(outer_region.mean()) < 0.005:
        return np.zeros_like(nodata_mask, dtype=bool), False, 0.0

    band_kernel = cv2.getStructuringElement(
        cv2.MORPH_ELLIPSE,
        (LIMB_BAND_RADIUS * 2 + 1, LIMB_BAND_RADIUS * 2 + 1),
    )
    band = cv2.morphologyEx(filled, cv2.MORPH_GRADIENT, band_kernel) > 0
    limb_mask = outer_region | band
    return limb_mask, True, float(limb_mask.mean())


def _detect_terminator_mask(
    image: np.ndarray,
    nodata_mask: np.ndarray,
    limb_mask: np.ndarray,
) -> tuple[np.ndarray, bool, float]:
    gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    analysis_mask = ~(nodata_mask | limb_mask)
    if float(analysis_mask.mean()) < MIN_VALID_PIXEL_RATIO:
        return np.zeros_like(analysis_mask, dtype=bool), False, 0.0

    blurred = cv2.GaussianBlur(gray, (0, 0), sigmaX=2.0, sigmaY=2.0)
    grad_x = cv2.Sobel(blurred, cv2.CV_32F, 1, 0, ksize=3)
    grad_y = cv2.Sobel(blurred, cv2.CV_32F, 0, 1, ksize=3)
    magnitude = cv2.magnitude(grad_x, grad_y)
    valid_gradients = magnitude[analysis_mask]
    if valid_gradients.size < 64:
        return np.zeros_like(analysis_mask, dtype=bool), False, 0.0

    threshold = max(float(np.percentile(valid_gradients, 97.5)), 20.0)
    candidate = (magnitude >= threshold) & analysis_mask
    candidate_uint8 = candidate.astype(np.uint8) * 255
    candidate_uint8 = cv2.morphologyEx(
        candidate_uint8,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7)),
    )
    candidate_uint8 = cv2.morphologyEx(
        candidate_uint8,
        cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
    )

    component_count, labels, stats, _ = cv2.connectedComponentsWithStats(candidate_uint8, connectivity=8)
    terminator_mask = np.zeros_like(candidate, dtype=bool)
    max_span_ratio = 0.0

    for label in range(1, component_count):
        x, y, w, h, area = stats[label]
        if area < gray.size * 0.005:
            continue
        span_ratio = max(w / gray.shape[1], h / gray.shape[0])
        if span_ratio < 0.25:
            continue
        terminator_mask |= labels == label
        max_span_ratio = max(max_span_ratio, span_ratio)

    terminator_ratio = float(terminator_mask.mean())
    detected = terminator_ratio >= MAX_TERMINATOR_RATIO and max_span_ratio >= 0.35
    if not detected:
        return np.zeros_like(candidate, dtype=bool), False, terminator_ratio
    return terminator_mask, True, terminator_ratio


def _compute_session_intensity_range(frames: list[dict]) -> tuple[Optional[float], Optional[float]]:
    min_intensity = None
    max_intensity = None

    for frame in frames:
        rgba = frame.get("rgba")
        nodata_mask = frame.get("nodataMask")
        if rgba is None or nodata_mask is None:
            continue
        valid_pixels = rgba[:, :, :3][~nodata_mask]
        if valid_pixels.size == 0:
            continue

        frame_min = float(valid_pixels.min())
        frame_max = float(valid_pixels.max())
        min_intensity = frame_min if min_intensity is None else min(min_intensity, frame_min)
        max_intensity = frame_max if max_intensity is None else max(max_intensity, frame_max)

    if min_intensity is None or max_intensity is None:
        return None, None
    if abs(max_intensity - min_intensity) < 1e-6:
        max_intensity = min_intensity + 1.0
    return min_intensity, max_intensity


def _save_normalized_frame(frame: dict, session_min: Optional[float], session_max: Optional[float]) -> None:
    if session_min is None or session_max is None:
        return

    rgba = frame["rgba"].astype(np.float32)
    scale = max(session_max - session_min, 1e-6)
    normalized_rgb = np.clip((rgba[:, :, :3] - session_min) / scale, 0.0, 1.0)
    normalized_uint8 = (normalized_rgb * 255.0).astype(np.uint8)

    excluded_mask = frame["nodataMask"] | frame["limbMask"]
    alpha = np.where(excluded_mask, 0, 255).astype(np.uint8)
    output = np.dstack([normalized_uint8, alpha])

    stem = _frame_stem(frame)
    output_path = os.path.join(PREPROCESSED_FRAMES_DIR, f"{stem}_normalized.png")
    cv2.imwrite(output_path, output)

    frame["normalizedPath"] = output_path
    frame["normalizedUrl"] = _to_data_url(output_path)
    frame["normalization"] = {
        "minIntensity": round(session_min, 6),
        "maxIntensity": round(session_max, 6),
    }


def _save_masks(frame: dict) -> None:
    stem = _frame_stem(frame)
    nodata_path = os.path.join(NODATA_MASKS_DIR, f"{stem}_nodata.png")
    limb_path = os.path.join(LIMB_MASKS_DIR, f"{stem}_limb.png")
    terminator_path = os.path.join(TERMINATOR_MASKS_DIR, f"{stem}_terminator.png")

    cv2.imwrite(nodata_path, (frame["nodataMask"].astype(np.uint8) * 255))
    cv2.imwrite(limb_path, (frame["limbMask"].astype(np.uint8) * 255))
    cv2.imwrite(terminator_path, (frame["terminatorMask"].astype(np.uint8) * 255))

    frame["nodataMaskPath"] = nodata_path
    frame["nodataMaskUrl"] = _to_data_url(nodata_path)
    frame["limbMaskPath"] = limb_path
    frame["limbMaskUrl"] = _to_data_url(limb_path)
    frame["terminatorMaskPath"] = terminator_path
    frame["terminatorMaskUrl"] = _to_data_url(terminator_path)


def _build_timeline_report(timestamps: list[str]) -> dict:
    parsed = [(value, parse_timestamp(value)) for value in timestamps]
    valid = [(raw, parsed_value) for raw, parsed_value in parsed if parsed_value is not None]
    sorted_values = sorted(valid, key=lambda item: item[1])
    gaps = [
        (right[1] - left[1]).total_seconds() / 60.0
        for left, right in zip(sorted_values, sorted_values[1:])
    ]
    positive_gaps = [gap for gap in gaps if gap > 0]

    expected_interval = min(positive_gaps) if positive_gaps else None
    tolerance = (
        max(MIN_TEMPORAL_TOLERANCE_MINUTES, expected_interval * TEMPORAL_TOLERANCE_RATIO)
        if expected_interval is not None
        else None
    )

    missing = []
    evenly_spaced = True
    for left, right in zip(sorted_values, sorted_values[1:]):
        gap_minutes = (right[1] - left[1]).total_seconds() / 60.0
        if expected_interval is None or tolerance is None:
            continue
        if abs(gap_minutes - expected_interval) > tolerance:
            evenly_spaced = False
        if gap_minutes > expected_interval + tolerance:
            steps = max(int(round(gap_minutes / expected_interval)) - 1, 0)
            for step in range(steps):
                candidate = left[1] + timedelta(minutes=expected_interval * (step + 1))
                if candidate < right[1] - timedelta(minutes=tolerance / 2.0):
                    missing.append(format_timestamp(candidate))

    return {
        "timestamps": [raw for raw, _ in sorted_values],
        "missing": missing,
        "interval_stats": {
            "sorted": [raw for raw, _ in valid] == [raw for raw, _ in sorted_values],
            "evenly_spaced": evenly_spaced,
            "expected_interval_minutes": None if expected_interval is None else round(expected_interval, 3),
            "tolerance_minutes": None if tolerance is None else round(tolerance, 3),
            "min_gap_minutes": None if not gaps else round(min(gaps), 3),
            "median_gap_minutes": None if not gaps else round(float(np.median(gaps)), 3),
            "max_gap_minutes": None if not gaps else round(max(gaps), 3),
        },
    }


def _detect_calibration_shifts(frames: list[dict]) -> list[dict]:
    if len(frames) < 2:
        return []

    candidates = []
    for left, right in zip(frames, frames[1:]):
        left_hist, left_mean = _histogram_signature(left["rgba"], left["nodataMask"] | left["limbMask"])
        right_hist, right_mean = _histogram_signature(right["rgba"], right["nodataMask"] | right["limbMask"])
        if left_hist is None or right_hist is None:
            continue
        histogram_shift = float(np.abs(left_hist - right_hist).sum() / 2.0)
        mean_shift = abs(right_mean - left_mean)
        candidates.append(
            {
                "from": left["timestamp"],
                "to": right["timestamp"],
                "histogramShift": round(histogram_shift, 6),
                "meanShift": round(mean_shift, 6),
            }
        )

    if not candidates:
        return []

    hist_values = np.array([item["histogramShift"] for item in candidates], dtype=np.float32)
    mean_values = np.array([item["meanShift"] for item in candidates], dtype=np.float32)
    hist_median = float(np.median(hist_values))
    hist_mad = float(np.median(np.abs(hist_values - hist_median)))
    mean_median = float(np.median(mean_values))
    mean_mad = float(np.median(np.abs(mean_values - mean_median)))

    histogram_threshold = max(0.18, hist_median + 3.0 * max(hist_mad, 0.015))
    mean_threshold = max(10.0, mean_median + 3.0 * max(mean_mad, 1.5))
    histogram_peak_threshold = max(0.5, float(np.percentile(hist_values, 90)))

    issues = []
    for candidate in candidates:
        histogram_spike = (
            candidate["histogramShift"] > histogram_threshold
            or candidate["histogramShift"] >= histogram_peak_threshold
        )
        if histogram_spike and candidate["meanShift"] > mean_threshold:
            issues.append(
                {
                    **candidate,
                    "issue": "CALIBRATION_SHIFT",
                }
            )
    return issues


def _histogram_signature(image: np.ndarray, excluded_mask: np.ndarray) -> tuple[Optional[np.ndarray], Optional[float]]:
    gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    valid_mask = ~excluded_mask
    valid_pixels = gray[valid_mask]
    if valid_pixels.size < 64:
        return None, None
    histogram, _ = np.histogram(valid_pixels, bins=64, range=(0, 255))
    histogram = histogram.astype(np.float32)
    histogram /= max(histogram.sum(), 1.0)
    return histogram, float(valid_pixels.mean())


def _frame_stem(frame: dict) -> str:
    filename = frame.get("filename")
    if filename:
        return os.path.splitext(filename)[0]
    timestamp = frame.get("wmsTime") or frame.get("timestamp") or "frame"
    return "".join(ch if ch.isalnum() else "_" for ch in timestamp)


def _to_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"
