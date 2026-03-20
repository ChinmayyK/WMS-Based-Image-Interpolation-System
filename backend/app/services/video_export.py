"""
FFmpeg-backed video export for sequence playback with provenance overlays.

PRD v2.0 Module 5 compliant: multi-output, HLS, ffprobe validation, metadata sidecars.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
EXPORTS_DIR = os.path.join(DATA_DIR, "exports")
LATEST_EXPORT_SUMMARY_PATH = os.path.join(EXPORTS_DIR, "latest_export.json")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def export_multi_output(
    frames: List[dict],
    *,
    fps: int = 15,
    raw_mode: bool = False,
    job_name: str = "sequence_export",
    job_id: Optional[str] = None,
    model_info: Optional[dict] = None,
) -> dict:
    """
    Render a full PRD-compliant multi-output export.

    Produces:
      original.mp4  / original.webm   — observed frames only
      interpolated.mp4 / interpolated.webm — all frames (observed + AI)
      stream/         — HLS m3u8 + ts segments
      export_metadata.json             — PRD sidecar
    """
    if not frames:
        raise ValueError("No frames provided for export")

    ffmpeg_exe = _resolve_ffmpeg_executable()
    ffprobe_exe = _resolve_ffprobe_executable()
    os.makedirs(EXPORTS_DIR, exist_ok=True)

    export_id = job_id or f"{_slugify(job_name)}_{uuid.uuid4().hex[:8]}"
    export_dir = os.path.join(EXPORTS_DIR, export_id)
    os.makedirs(export_dir, exist_ok=True)

    # ----- Split frames -----
    observed_frames = [f for f in frames if f.get("isOriginal")]
    all_frames = frames  # observed + AI + gap

    # ----- Render overlay frames -----
    observed_render_dir = os.path.join(export_dir, "render_observed")
    all_render_dir = os.path.join(export_dir, "render_all")
    os.makedirs(observed_render_dir, exist_ok=True)
    os.makedirs(all_render_dir, exist_ok=True)

    resolution = None

    for idx, frame in enumerate(observed_frames):
        src = _resolve_local_image_path(frame, raw_mode=raw_mode)
        out = os.path.join(observed_render_dir, f"{idx:06d}.png")
        res = _render_export_frame(src, frame, out)
        if resolution is None:
            resolution = res

    for idx, frame in enumerate(all_frames):
        src = _resolve_local_image_path(frame, raw_mode=raw_mode)
        out = os.path.join(all_render_dir, f"{idx:06d}.png")
        res = _render_export_frame(src, frame, out)
        if resolution is None:
            resolution = res

    width, height = resolution or (0, 0)
    resolution_str = f"{width}x{height}" if resolution else "unknown"

    # ----- Encode 4 videos -----
    watermark = "AI-GENERATED — NOT OBSERVED DATA watermark burned into interpolated frames."
    meta = {"title": "GeoAI Satellite Sequence", "comment": watermark}

    outputs: Dict[str, str] = {}
    validations: Dict[str, dict] = {}

    encode_jobs = [
        ("original_mp4",  observed_render_dir, "original.mp4",
         ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]),
        ("original_webm", observed_render_dir, "original.webm",
         ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "33"]),
        ("interpolated_mp4",  all_render_dir, "interpolated.mp4",
         ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]),
        ("interpolated_webm", all_render_dir, "interpolated.webm",
         ["-c:v", "libvpx-vp9", "-pix_fmt", "yuv420p", "-b:v", "0", "-crf", "33"]),
    ]

    for key, render_dir, filename, codec_args in encode_jobs:
        pattern = os.path.join(render_dir, "%06d.png")
        out_path = os.path.join(export_dir, filename)

        frame_count = len(os.listdir(render_dir))
        if frame_count == 0:
            logger.warning("Skipping %s — no rendered frames", filename)
            continue

        _run_ffmpeg(ffmpeg_exe, pattern, fps, out_path, codec_args=codec_args, metadata=meta)
        outputs[key] = _to_data_url(out_path)

        # ffprobe validation
        probe = _run_ffprobe(ffprobe_exe, out_path)
        validations[key] = probe

    # ----- HLS Stream -----
    hls_dir = os.path.join(export_dir, "stream")
    os.makedirs(hls_dir, exist_ok=True)
    hls_source = os.path.join(export_dir, "interpolated.mp4")
    hls_playlist = os.path.join(hls_dir, "stream.m3u8")
    hls_url = None

    if os.path.exists(hls_source):
        _generate_hls(ffmpeg_exe, hls_source, hls_dir)
        hls_url = _to_data_url(hls_playlist)

    # ----- PRD Metadata Sidecar -----
    metadata_frames = []
    for index, frame in enumerate(all_frames):
        frame_type = "GAP" if frame.get("isGapPlaceholder") else (
            "OBSERVED" if frame.get("isOriginal") else "INTERPOLATED"
        )
        metadata_frames.append({
            "frame_index": index,
            "timestamp": frame.get("timestamp"),
            "type": frame_type,
            "confidence": frame.get("confidence"),
            "label": frame.get("confidenceLabel") or frame_type,
            "is_observed": bool(frame.get("isOriginal")),
            "model": (model_info or {}).get("name", "RIFE HDv3 (PRD v2.0 preferred: RIFE 4.6)"),
            "inference_time": frame.get("inferenceTime"),
        })

    sidecar = {
        "job_id": export_id,
        "frames": metadata_frames,
        "export_time": datetime.now(timezone.utc).isoformat(),
        "resolution": resolution_str,
        "fps": fps,
    }
    sidecar_path = os.path.join(export_dir, "export_metadata.json")
    with open(sidecar_path, "w", encoding="utf-8") as f:
        json.dump(sidecar, f, indent=2)

    # ----- Result summary -----
    result = {
        "exportId": export_id,
        "fps": fps,
        "rawMode": raw_mode,
        "resolution": resolution_str,
        "observedFrameCount": len(observed_frames),
        "totalFrameCount": len(all_frames),
        "outputs": {
            "original_mp4": outputs.get("original_mp4"),
            "original_webm": outputs.get("original_webm"),
            "interpolated_mp4": outputs.get("interpolated_mp4"),
            "interpolated_webm": outputs.get("interpolated_webm"),
            "hls": hls_url,
            "metadata": _to_data_url(sidecar_path),
        },
        "validation": validations,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
    }

    with open(LATEST_EXPORT_SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    # Store per-export summary
    with open(os.path.join(export_dir, "export_summary.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)

    return result


# Keep backward compat alias
def export_video_sequence(
    frames: List[dict],
    *,
    fps: int = 15,
    raw_mode: bool = False,
    job_name: str = "sequence_export",
    model_info: Optional[dict] = None,
) -> dict:
    """Legacy wrapper — delegates to export_multi_output."""
    return export_multi_output(
        frames,
        fps=fps,
        raw_mode=raw_mode,
        job_name=job_name,
        model_info=model_info,
    )


def get_latest_export_summary() -> Optional[dict]:
    """Return the latest export summary if one exists."""
    if not os.path.exists(LATEST_EXPORT_SUMMARY_PATH):
        return None
    with open(LATEST_EXPORT_SUMMARY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_export_summary(export_id: str) -> Optional[dict]:
    """Return export summary for a specific export ID."""
    path = os.path.join(EXPORTS_DIR, export_id, "export_summary.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Frame rendering
# ---------------------------------------------------------------------------

def _render_export_frame(source_path: str, frame: dict, output_path: str) -> Tuple[int, int]:
    """Render a single frame with PRD-compliant overlays. Returns (width, height)."""
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
    confidence_text = "OBSERVED" if frame.get("isOriginal") else f"{label} {round(float(confidence_value or 0.0) * 100)}%"

    # Top-left: timestamp
    _draw_badge(canvas, (24, 24), f"TIME {timestamp}", (40, 40, 40), (220, 220, 220))
    # Top-right: confidence label
    _draw_badge_right(canvas, (width - 24, 24), confidence_text, _badge_color(label), (245, 245, 245))

    # Mandatory disclosure overlays
    if frame.get("isGapPlaceholder"):
        _draw_center_banner(canvas, f"DATA GAP — {timestamp}", (90, 90, 90))
    elif not frame.get("isOriginal"):
        _draw_center_banner(canvas, "AI-GENERATED — NOT OBSERVED DATA", (40, 40, 210))

    cv2.imwrite(output_path, canvas)
    return (width, height)


# ---------------------------------------------------------------------------
# FFmpeg helpers
# ---------------------------------------------------------------------------

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
        ffmpeg_exe, "-y",
        "-framerate", str(fps),
        "-i", input_pattern,
    ]
    for key, value in metadata.items():
        command.extend(["-metadata", f"{key}={value}"])
    command.extend(codec_args)
    command.append(output_path)

    logger.info("Running FFmpeg export | output=%s", output_path)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg export failed for {output_path}: {result.stderr}")


def _generate_hls(ffmpeg_exe: str, source_mp4: str, hls_dir: str) -> None:
    """Segment an MP4 into HLS m3u8 + .ts chunks."""
    playlist = os.path.join(hls_dir, "stream.m3u8")
    command = [
        ffmpeg_exe, "-y",
        "-i", source_mp4,
        "-codec", "copy",
        "-start_number", "0",
        "-hls_time", "4",
        "-hls_list_size", "0",
        "-f", "hls",
        playlist,
    ]
    logger.info("Generating HLS stream | dir=%s", hls_dir)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("HLS generation failed (non-fatal): %s", result.stderr)


def _run_ffprobe(ffprobe_exe: str, filepath: str) -> dict:
    """Run ffprobe and return validation results."""
    command = [
        ffprobe_exe,
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return {"valid": False, "error": result.stderr}
        info = json.loads(result.stdout)

        video_stream = None
        for s in info.get("streams", []):
            if s.get("codec_type") == "video":
                video_stream = s
                break

        fmt = info.get("format", {})
        return {
            "valid": True,
            "duration": float(fmt.get("duration", 0)),
            "codec": video_stream.get("codec_name") if video_stream else None,
            "width": int(video_stream.get("width", 0)) if video_stream else None,
            "height": int(video_stream.get("height", 0)) if video_stream else None,
            "nb_frames": video_stream.get("nb_frames"),
            "format_name": fmt.get("format_name"),
        }
    except Exception as exc:
        return {"valid": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Executable resolution
# ---------------------------------------------------------------------------

def _resolve_ffmpeg_executable() -> str:
    """Locate an FFmpeg binary, preferring imageio-ffmpeg's bundled executable."""
    explicit = os.getenv("FFMPEG_BINARY")
    if explicit and os.path.exists(explicit):
        return explicit
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        fallback = shutil.which("ffmpeg")
        if fallback:
            return fallback
        raise RuntimeError(
            "FFmpeg export requires imageio-ffmpeg, a system ffmpeg binary, or an FFMPEG_BINARY override."
        ) from exc
    return imageio_ffmpeg.get_ffmpeg_exe()


def _resolve_ffprobe_executable() -> str:
    """Locate ffprobe next to the ffmpeg binary or on PATH."""
    ffmpeg = _resolve_ffmpeg_executable()
    ffprobe_candidate = os.path.join(os.path.dirname(ffmpeg), "ffprobe")
    if os.path.exists(ffprobe_candidate):
        return ffprobe_candidate
    system_probe = shutil.which("ffprobe")
    if system_probe:
        return system_probe
    # Fall back to ffmpeg directory with platform extensions
    for ext in ("", ".exe"):
        candidate = ffprobe_candidate + ext
        if os.path.exists(candidate):
            return candidate
    logger.warning("ffprobe not found — validation will be skipped")
    return "ffprobe"  # will fail gracefully in _run_ffprobe


# ---------------------------------------------------------------------------
# Drawing helpers
# ---------------------------------------------------------------------------

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
    origin: tuple,
    text: str,
    bg_color: tuple,
    fg_color: tuple,
) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.8
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x, y = origin
    cv2.rectangle(canvas, (x, y), (x + text_w + 24, y + text_h + 20), bg_color, -1)
    cv2.putText(canvas, text, (x + 12, y + text_h + 7), font, scale, fg_color, thickness, cv2.LINE_AA)


def _draw_badge_right(
    canvas: np.ndarray,
    origin: tuple,
    text: str,
    bg_color: tuple,
    fg_color: tuple,
) -> None:
    """Draw a badge anchored to the top-right."""
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.8
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x_right, y = origin
    x = x_right - text_w - 24
    cv2.rectangle(canvas, (x, y), (x + text_w + 24, y + text_h + 20), bg_color, -1)
    cv2.putText(canvas, text, (x + 12, y + text_h + 7), font, scale, fg_color, thickness, cv2.LINE_AA)


def _draw_center_banner(canvas: np.ndarray, text: str, color: tuple) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.9
    thickness = 2
    (text_w, text_h), _ = cv2.getTextSize(text, font, scale, thickness)
    x = max((canvas.shape[1] - text_w) // 2 - 16, 20)
    y = canvas.shape[0] - 80
    cv2.rectangle(canvas, (x, y - text_h - 14), (x + text_w + 32, y + 10), color, -1)
    cv2.putText(canvas, text, (x + 16, y - 6), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def _badge_color(label: str) -> tuple:
    """PRD v2.0 color scheme: teal/green, amber, red, gray."""
    colors = {
        "OBSERVED": (51, 137, 0),      # Green (BGR)
        "HIGH":     (123, 137, 0),      # Teal  (BGR for #008B8B-ish)
        "MEDIUM":   (23, 127, 245),     # Amber (BGR for #F57F17)
        "LOW":      (38, 38, 220),      # Red   (BGR)
        "REJECTED": (117, 117, 117),    # Gray
        "GAP":      (117, 117, 117),    # Gray
    }
    return colors.get(label, (90, 90, 90))


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "_" for ch in (value or "sequence_export"))
    cleaned = "_".join(filter(None, cleaned.split("_")))
    return cleaned or "sequence_export"
