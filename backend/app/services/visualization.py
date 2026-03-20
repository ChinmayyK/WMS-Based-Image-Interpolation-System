"""
Visualization helpers for preparing raw-vs-clean observed frame assets.

These assets are display-oriented: they preserve a raw scientific mode while
also generating a cleaner visualization product with filled sensor gaps.
"""
import os
import re
from datetime import datetime
from typing import List, Dict, Optional

import cv2
import numpy as np

BLACK_THRESHOLD = 8
TEMPORAL_FILL_METHOD = "Temporal weighted fill + nearest-neighbor inpaint"


def _parse_timestamp(value: str) -> Optional[datetime]:
    """Best-effort parser for raw frame timestamps."""
    if not value:
        return None

    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        pass

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y%m%d", "%Y%m%dT%H%M%S%z", "%Y%m%dT%H%M%S"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue
    return None


def _ensure_bgra(img: np.ndarray) -> np.ndarray:
    """Normalize an image array to BGRA."""
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGRA)
    if img.shape[2] == 4:
        return img
    if img.shape[2] == 3:
        return cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
    raise ValueError(f"Unsupported image shape: {img.shape}")


def detect_nodata_mask(img: np.ndarray, black_threshold: int = BLACK_THRESHOLD) -> np.ndarray:
    """
    Detect NoData pixels using alpha transparency and near-black RGB values.
    Returns a boolean mask where True means "sensor gap / no data".
    """
    rgba = _ensure_bgra(img)
    rgb = rgba[:, :, :3]
    alpha_gap = rgba[:, :, 3] < 64
    near_black = np.max(rgb, axis=2) <= black_threshold
    return alpha_gap | near_black


def _build_gap_mask_image(mask: np.ndarray) -> np.ndarray:
    """Create a grey translucent overlay for sensor-gap visualization."""
    overlay = np.zeros((*mask.shape, 4), dtype=np.uint8)
    overlay[mask] = [117, 117, 117, 156]
    return overlay


def _temporal_weight(
    target_timestamp: Optional[datetime],
    candidate_timestamp: Optional[datetime],
    target_index: int,
    candidate_index: int,
) -> float:
    """Compute a stable weight for temporal borrowing."""
    if target_timestamp is not None and candidate_timestamp is not None:
        delta_hours = abs((candidate_timestamp - target_timestamp).total_seconds()) / 3600.0
        return 1.0 / max(delta_hours, 1.0)
    return 1.0 / max(abs(candidate_index - target_index), 1)


def _fill_sensor_gaps(
    target_index: int,
    frames_bgr: List[np.ndarray],
    gap_masks: List[np.ndarray],
    timestamps: List[Optional[datetime]],
) -> np.ndarray:
    """
    Produce a gap-filled visualization frame.

    Strategy:
    1. Borrow valid pixels from neighboring frames using temporal weights.
    2. If some pixels are still missing, fill them spatially with inpainting.
    """
    base = frames_bgr[target_index]
    gap_mask = gap_masks[target_index]
    if not gap_mask.any():
        return base.copy()

    h, w = gap_mask.shape
    accumulator = np.zeros((h, w, 3), dtype=np.float32)
    weight_sum = np.zeros((h, w), dtype=np.float32)

    for candidate_index, candidate_bgr in enumerate(frames_bgr):
        if candidate_index == target_index:
            continue

        candidate_valid = ~gap_masks[candidate_index]
        use_mask = gap_mask & candidate_valid
        if not use_mask.any():
            continue

        weight = _temporal_weight(
            timestamps[target_index],
            timestamps[candidate_index],
            target_index,
            candidate_index,
        )
        accumulator[use_mask] += candidate_bgr[use_mask].astype(np.float32) * weight
        weight_sum[use_mask] += weight

    filled = base.copy()
    temporally_fillable = gap_mask & (weight_sum > 0)
    if temporally_fillable.any():
        filled[temporally_fillable] = np.clip(
            accumulator[temporally_fillable] / weight_sum[temporally_fillable, None],
            0,
            255,
        ).astype(np.uint8)

    remaining = gap_mask & ~temporally_fillable
    if remaining.any():
        inpaint_input = filled.copy()
        inpaint_input[remaining] = 0
        filled = cv2.inpaint(
            inpaint_input,
            (remaining.astype(np.uint8) * 255),
            5,
            cv2.INPAINT_TELEA,
        )

    return filled


def prepare_visualization_assets(
    raw_frames: List[dict],
    clean_dir: str,
    gap_mask_dir: str,
) -> Dict[str, dict]:
    """
    Generate clean observed-frame assets and sensor-gap masks for UI display.

    Returns a mapping of raw frame path -> asset metadata.
    """
    if not raw_frames:
        return {}

    os.makedirs(clean_dir, exist_ok=True)
    os.makedirs(gap_mask_dir, exist_ok=True)

    sorted_frames = sorted(raw_frames, key=lambda frame: frame["timestamp"])
    latest_input_mtime = max(os.path.getmtime(frame["path"]) for frame in sorted_frames)

    rgba_images = [_ensure_bgra(cv2.imread(frame["path"], cv2.IMREAD_UNCHANGED)) for frame in sorted_frames]
    frames_bgr = [img[:, :, :3] for img in rgba_images]
    gap_masks = [detect_nodata_mask(img) for img in rgba_images]
    timestamps = [_parse_timestamp(frame["timestamp"]) for frame in sorted_frames]

    assets = {}

    for index, frame in enumerate(sorted_frames):
        stem = os.path.splitext(os.path.basename(frame["path"]))[0]
        clean_path = os.path.join(clean_dir, f"{stem}_clean.png")
        gap_mask_path = os.path.join(gap_mask_dir, f"{stem}_gap.png")

        needs_regen = (
            not os.path.exists(clean_path)
            or not os.path.exists(gap_mask_path)
            or os.path.getmtime(clean_path) < latest_input_mtime
            or os.path.getmtime(gap_mask_path) < latest_input_mtime
        )

        gap_mask = gap_masks[index]
        if needs_regen:
            filled_bgr = _fill_sensor_gaps(index, frames_bgr, gap_masks, timestamps)
            clean_rgba = np.dstack([filled_bgr, np.full(gap_mask.shape, 255, dtype=np.uint8)])
            cv2.imwrite(clean_path, clean_rgba)
            cv2.imwrite(gap_mask_path, _build_gap_mask_image(gap_mask))

        assets[frame["path"]] = {
            "cleanPath": clean_path,
            "gapMaskPath": gap_mask_path,
            "hasSensorGap": bool(gap_mask.any()),
            "gapCoveragePct": round(float(gap_mask.mean() * 100), 3),
            "gapFillMethod": TEMPORAL_FILL_METHOD,
        }

    return assets


def create_gap_placeholder(
    output_path: str,
    timestamp: str,
    reason: str,
    width: int = 960,
    height: int = 1024,
    title: str = "DATA GAP",
) -> str:
    """
    Create a dark placeholder frame for rejected or non-interpolable gaps.
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    if os.path.exists(output_path):
        return output_path

    canvas = np.zeros((height, width, 4), dtype=np.uint8)
    canvas[:, :, :3] = (24, 24, 24)
    canvas[:, :, 3] = 255

    cv2.rectangle(canvas, (40, 40), (width - 40, height - 40), (117, 117, 117, 255), 3)
    cv2.putText(
        canvas,
        title,
        (90, height // 2 - 80),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.8,
        (220, 220, 220, 255),
        4,
        cv2.LINE_AA,
    )
    cv2.putText(
        canvas,
        f"{timestamp}",
        (90, height // 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.1,
        (180, 180, 180, 255),
        2,
        cv2.LINE_AA,
    )
    for idx, line in enumerate(_wrap_text(reason, max_chars=42)):
        cv2.putText(
            canvas,
            line,
            (90, height // 2 + 70 + idx * 42),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.9,
            (150, 150, 150, 255),
            2,
            cv2.LINE_AA,
        )

    cv2.imwrite(output_path, canvas)
    return output_path


def _wrap_text(text: str, max_chars: int = 40) -> List[str]:
    """Wrap plain text for placeholder rendering."""
    tokens = re.split(r"\s+", text.strip())
    if not tokens:
        return [""]

    lines: List[str] = []
    current = tokens[0]
    for token in tokens[1:]:
        candidate = f"{current} {token}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            lines.append(current)
            current = token
    lines.append(current)
    return lines
