"""
FFmpeg-backed video export for sequence playback with provenance overlays.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from typing import List, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
LATEST_EXPORT_SUMMARY_PATH = os.path.join(EXPORTS_DIR, "latest_export.json")


def export_video_sequence(
    frames: List[dict],
    *,
    fps: int = 15,
    raw_mode: bool = False,
    job_name: str = "sequence_export",
    model_info: Optional[dict] = None,
) -> dict:
    """
    Render a frame sequence to MP4 and WebM with burned-in overlays.
    """
    if not frames:
        raise ValueError("No frames provided for export")

    ffmpeg_exe = _resolve_ffmpeg_executable()
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    job_id = f"{_slugify(job_name)}_{uuid.uuid4().hex[:8]}"
    job_dir = os.path.join(EXPORTS_DIR, job_id)
    render_dir = os.path.join(job_dir, "render_frames")
    os.makedirs(render_dir, exist_ok=True)

    rendered_frames = []
    metadata_frames = []
    for index, frame in enumerate(frames):
        source_path = _resolve_local_image_path(frame, raw_mode=raw_mode)
        rendered_path = os.path.join(render_dir, f"{index:06d}.png")
        _render_export_frame(source_path, frame, rendered_path)
        rendered_frames.append(rendered_path)
        metadata_frames.append({
            "frame_index": index,
            "timestamp": frame.get("timestamp"),
            "type": frame.get("confidenceLabel") or ("OBSERVED" if frame.get("isOriginal") else "LOW"),
            "confidence": frame.get("confidence"),
            "is_observed": bool(frame.get("isOriginal")),
            "source_frames": frame.get("sourceFrames") or [],
            "rendered_as_gap": bool(frame.get("isGapPlaceholder")),
            "image_url": frame.get("imageUrl"),
        })

    mp4_path = os.path.join(job_dir, "sequence.mp4")
    webm_path = os.path.join(job_dir, "sequence.webm")
    metadata_path = os.path.join(job_dir, "sequence_metadata.json")

    with open(metadata_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "jobId": job_id,
                "fps": fps,
                "rawMode": raw_mode,
                "generatedAt": datetime.now(timezone.utc).isoformat(),
                "model": model_info or {},
                "frames": metadata_frames,
            },
            handle,
            indent=2,
        )

    input_pattern = os.path.join(render_dir, "%06d.png")
    watermark_comment = "AI-GENERATED — NOT OBSERVED DATA watermark burned into interpolated frames."

    _run_ffmpeg(
        ffmpeg_exe,
        input_pattern,
        fps,
        mp4_path,
        codec_args=["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"],
        metadata={
            "title": "GeoAI Satellite Sequence",
            "comment": watermark_comment,
        },
    )
    _run_ffmpeg(
        ffmpeg_exe,
        input_pattern,
        fps,
        webm_path,
        codec_args=["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "33"],
        metadata={
            "title": "GeoAI Satellite Sequence",
            "comment": watermark_comment,
        },
    )

    result = {
        "jobId": job_id,
        "ffmpegExecutable": ffmpeg_exe,
        "fps": fps,
        "rawMode": raw_mode,
        "frameCount": len(frames),
        "mp4Url": _to_data_url(mp4_path),
        "webmUrl": _to_data_url(webm_path),
        "metadataUrl": _to_data_url(metadata_path),
    }
    with open(LATEST_EXPORT_SUMMARY_PATH, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2)

    return result


def get_latest_export_summary() -> Optional[dict]:
    """Return the latest export summary if one exists."""
    if not os.path.exists(LATEST_EXPORT_SUMMARY_PATH):
        return None
    with open(LATEST_EXPORT_SUMMARY_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _render_export_frame(source_path: str, frame: dict, output_path: str) -> None:
    img = cv2.imread(source_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise FileNotFoundError(source_path)
    if img.ndim == 2:
        canvas = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    elif img.shape[2] == 4:
        canvas = img[:, :, :3].copy()
    else:
        canvas = img.copy()

    height, width = canvas.shape[:2]
    timestamp = frame.get("timestamp", "Unknown")
    label = frame.get("confidenceLabel") or ("OBSERVED" if frame.get("isOriginal") else "LOW")
    confidence_value = frame.get("confidence")
    confidence_text = "OBSERVED" if frame.get("isOriginal") else f"{label} {round(float(confidence_value or 0.0) * 100):.1f}%"

    _draw_badge(canvas, (24, 24), f"TIME {timestamp}", (40, 40, 40), (220, 220, 220))
    _draw_badge(canvas, (24, 82), confidence_text, _badge_color(label), (245, 245, 245))

    if frame.get("isGapPlaceholder"):
        _draw_center_banner(canvas, "GAP — NO DATA", (90, 90, 90))
    elif not frame.get("isOriginal"):
        _draw_center_banner(canvas, "AI-GENERATED — NOT OBSERVED DATA", (40, 40, 210))

    cv2.imwrite(output_path, canvas)


def _run_ffmpeg(
    ffmpeg_exe: str,
    input_pattern: str,
    fps: int,
    output_path: str,
    *,
    codec_args: List[str],
    metadata: dict,
) -> None:
    command = [
        ffmpeg_exe,
        "-y",
        "-framerate",
        str(fps),
        "-i",
        input_pattern,
    ]
    for key, value in metadata.items():
        command.extend(["-metadata", f"{key}={value}"])
    command.extend(codec_args)
    command.append(output_path)

    logger.info("Running FFmpeg export | output=%s", output_path)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg export failed for {output_path}: {result.stderr}")


def _resolve_ffmpeg_executable() -> str:
    """Locate an FFmpeg binary, preferring imageio-ffmpeg's bundled executable."""
    explicit = os.getenv("FFMPEG_BINARY")
    if explicit and os.path.exists(explicit):
        return explicit

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "FFmpeg export requires imageio-ffmpeg or an FFMPEG_BINARY override."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _resolve_local_image_path(frame: dict, raw_mode: bool = False) -> str:
    candidate = frame.get("rawImageUrl") if raw_mode and frame.get("rawImageUrl") else frame.get("imageUrl")
    if not candidate:
        raise ValueError(f"Frame is missing an exportable image path: {frame.get('timestamp')}")
    if candidate.startswith("/data/"):
        return os.path.join(DATA_DIR, candidate.replace("/data/", "", 1))
    if os.path.isabs(candidate):
        return candidate
    return os.path.join(BASE_DIR, candidate.lstrip("/"))


def _to_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"


def _draw_badge(
    canvas: np.ndarray,
    origin: tuple[int, int],
    text: str,
    bg_color: tuple[int, int, int],
    fg_color: tuple[int, int, int],
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.8
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = origin
    cv2.rectangle(canvas, (x, y), (x + text_w + 24, y + text_h + 20), bg_color, -1)
    cv2.putText(canvas, text, (x + 12, y + text_h + 7), font, scale, fg_color, thickness, cv2.LINE_AA)


def _draw_center_banner(canvas: np.ndarray, text: str, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.9
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max((canvas.shape[1] - text_w) // 2 - 16, 20)
    y = canvas.shape[0] - 80
    cv2.rectangle(canvas, (x, y - text_h - 14), (x + text_w + 32, y + 10), color, -1)
    cv2.putText(canvas, text, (x + 16, y - 6), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def _badge_color(label: str) -> tuple[int, int, int]:
    colors = {
        "OBSERVED": (50, 125, 46),
        "HIGH": (50, 168, 82),
        "MEDIUM": (23, 127, 245),
        "LOW": (38, 38, 220),
        "REJECTED": (117, 117, 117),
        "GAP": (117, 117, 117),
    }
    return colors.get(label, (90, 90, 90))


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "sequence_export"))
    cleaned = "_".join(filter(None, cleaned.split("_")))
    return cleaned or "sequence_export"
