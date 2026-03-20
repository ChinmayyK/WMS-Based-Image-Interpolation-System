import json
import logging
import os
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException

from app.models import (
    EvaluationRequest,
    FrameRetrievalRequest,
    InterpolationRequest,
    MetadataResponse,
    VideoExportRequest,
)
from app.services.confidence import (
    MAX_INTERPOLATION_GAP_MINUTES,
    build_session_confidence_profile,
    classify_confidence,
    format_timestamp,
    gap_minutes_between,
    midpoint_timestamp,
    parse_timestamp,
    persist_session_confidence_profile,
    recommended_interpolation_frames,
    score_generated_frame,
)
from app.services.visualization import create_gap_placeholder, prepare_visualization_assets

router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_FRAMES_DIR = os.path.join(DATA_DIR, "raw_frames")
INTERPOLATED_FRAMES_DIR = os.path.join(DATA_DIR, "interpolated_frames")
CLEAN_FRAMES_DIR = os.path.join(DATA_DIR, "clean_frames")
SENSOR_GAP_MASKS_DIR = os.path.join(DATA_DIR, "sensor_gap_masks")
METADATA_DIR = os.path.join(DATA_DIR, "metadata")
GAP_PLACEHOLDERS_DIR = os.path.join(DATA_DIR, "gap_placeholders")

INDIA_BBOX = [68.0, 6.0, 98.0, 36.0]
INDIA_EXTENT_3857 = [7569725.37, 669141.06, 10909310.10, 4300621.37]
NASA_GIBS_3857_WMS_URL = os.getenv(
    "WMS_URL", "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi"
)
DEFAULT_WMS_LAYER = "MODIS_Terra_CorrectedReflectance_TrueColor"

_RAW_FRAME_DATE_MAP = {
    "frame_10_00": "2024-06-01",
    "frame_25_00": "2024-06-02",
    "frame_40_00": "2024-06-03",
}

FRAME_CATALOG = []
LAST_CONFIDENCE_PROFILE = {}


def build_frame_catalog():
    """
    Build the frontend frame sequence from on-disk observed frames plus
    PRD-compliant interpolated outputs and gap placeholders.
    """
    observed_frames = _build_observed_frames()
    session_profile = build_session_confidence_profile([
        {
            "timestamp": frame["timestamp"],
            "path": _resolve_catalog_path(frame, prefer_clean=True),
        }
        for frame in observed_frames
    ])
    persist_session_confidence_profile(session_profile, METADATA_DIR)

    generated_by_pair = _load_generated_frames()
    catalog = []

    for index, observed in enumerate(observed_frames):
        catalog.append(observed)
        if index == len(observed_frames) - 1:
            continue

        next_observed = observed_frames[index + 1]
        pair_key = (observed["timestamp"], next_observed["timestamp"])
        gap_minutes = gap_minutes_between(*pair_key)

        if gap_minutes is not None and gap_minutes > MAX_INTERPOLATION_GAP_MINUTES:
            catalog.append(_build_gap_placeholder_entry(observed, next_observed, gap_minutes))
            continue

        generated_entries = sorted(
            generated_by_pair.get(pair_key, []),
            key=lambda frame: _sort_key(frame["timestamp"]),
        )
        catalog.extend(generated_entries)

    catalog.sort(key=lambda frame: _sort_key(frame["timestamp"]))

    global LAST_CONFIDENCE_PROFILE
    LAST_CONFIDENCE_PROFILE = session_profile
    return catalog


def _build_observed_frames():
    raw_sources = []
    if os.path.exists(RAW_FRAMES_DIR):
        for filename in sorted(os.listdir(RAW_FRAMES_DIR)):
            if not filename.lower().endswith((".png", ".jpg")):
                continue
            full_path = os.path.join(RAW_FRAMES_DIR, filename)
            timestamp = _filename_to_timestamp(filename)
            raw_sources.append({
                "path": full_path,
                "filename": filename,
                "timestamp": timestamp,
                "wmsDate": _filename_to_wms_date(filename),
            })

    asset_map = prepare_visualization_assets(
        raw_sources,
        clean_dir=CLEAN_FRAMES_DIR,
        gap_mask_dir=SENSOR_GAP_MASKS_DIR,
    ) if raw_sources else {}

    deduped = {}
    for source in raw_sources:
        assets = asset_map.get(source["path"], {})
        entry = {
            "timestamp": source["timestamp"],
            "imageUrl": f"/data/clean_frames/{os.path.basename(assets['cleanPath'])}" if assets.get("cleanPath") else f"/data/raw_frames/{source['filename']}",
            "rawImageUrl": f"/data/raw_frames/{source['filename']}",
            "cleanImageUrl": f"/data/clean_frames/{os.path.basename(assets['cleanPath'])}" if assets.get("cleanPath") else None,
            "gapMaskUrl": f"/data/sensor_gap_masks/{os.path.basename(assets['gapMaskPath'])}" if assets.get("gapMaskPath") else None,
            "hasSensorGap": assets.get("hasSensorGap", False),
            "gapCoveragePct": assets.get("gapCoveragePct", 0.0),
            "gapFillMethod": assets.get("gapFillMethod"),
            "isOriginal": True,
            "confidence": 1.0,
            "confidenceLabel": "OBSERVED",
            "confidenceMethod": "Observed WMS frame",
            "metrics": {},
            "bbox": INDIA_BBOX,
            "extent3857": INDIA_EXTENT_3857,
            "wmsLayer": DEFAULT_WMS_LAYER,
            "wmsUrl": NASA_GIBS_3857_WMS_URL,
            "wmsCrs": "EPSG:3857",
            "isGapPlaceholder": False,
        }
        if source["wmsDate"]:
            entry["wmsDate"] = source["wmsDate"]

        previous = deduped.get(source["timestamp"])
        if previous is None or os.path.getmtime(source["path"]) >= previous["_mtime"]:
            deduped[source["timestamp"]] = {**entry, "_mtime": os.path.getmtime(source["path"])}

    observed = [
        {key: value for key, value in entry.items() if key != "_mtime"}
        for entry in deduped.values()
    ]
    observed.sort(key=lambda frame: _sort_key(frame["timestamp"]))
    return observed


def _load_generated_frames():
    generated = {}
    if not os.path.isdir(METADATA_DIR):
        return generated

    for filename in sorted(os.listdir(METADATA_DIR)):
        if not filename.endswith(".json") or filename == "session_confidence_profile.json":
            continue
        path = os.path.join(METADATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            continue
        if not data.get("generated"):
            continue
        source_timestamps = data.get("source_timestamps") or []
        if len(source_timestamps) != 2:
            continue
        image_url = _resolve_generated_url(data["frame_id"])
        if image_url is None:
            continue

        pair_key = (source_timestamps[0], source_timestamps[1])
        entry = {
            "timestamp": data.get("time"),
            "imageUrl": image_url,
            "cleanImageUrl": image_url,
            "rawImageUrl": None,
            "isOriginal": False,
            "confidence": data.get("confidence", 0.0),
            "confidenceLabel": data.get("confidence_label") or classify_confidence(data.get("confidence", 0.0)),
            "confidenceMethod": data.get("confidence_method"),
            "metrics": data.get("metrics") or {},
            "sourceFrames": source_timestamps,
            "gapMinutes": data.get("gap_minutes"),
            "bbox": INDIA_BBOX,
            "extent3857": INDIA_EXTENT_3857,
            "hasSensorGap": False,
            "gapCoveragePct": 0.0,
            "isGapPlaceholder": bool(data.get("rendered_as_gap")),
            "placeholderReason": data.get("placeholder_reason"),
            "modelInfo": data.get("model") or {},
        }
        generated.setdefault(pair_key, []).append(entry)
    return generated


def _build_gap_placeholder_entry(left_frame: dict, right_frame: dict, gap_minutes: float):
    midpoint = midpoint_timestamp(left_frame["timestamp"], right_frame["timestamp"]) or left_frame["timestamp"]
    placeholder_name = f"gap_{_safe_name(left_frame['timestamp'])}_{_safe_name(right_frame['timestamp'])}.png"
    placeholder_path = os.path.join(GAP_PLACEHOLDERS_DIR, placeholder_name)
    message = "Interpolation disabled: gap exceeds 30 minutes"
    create_gap_placeholder(placeholder_path, midpoint, message)
    return {
        "timestamp": midpoint,
        "imageUrl": _to_data_url(placeholder_path),
        "cleanImageUrl": _to_data_url(placeholder_path),
        "rawImageUrl": None,
        "isOriginal": False,
        "confidence": 0.0,
        "confidenceLabel": "GAP",
        "confidenceMethod": "Hard temporal guardrail",
        "metrics": {},
        "sourceFrames": [left_frame["timestamp"], right_frame["timestamp"]],
        "gapMinutes": round(gap_minutes, 2),
        "bbox": INDIA_BBOX,
        "extent3857": INDIA_EXTENT_3857,
        "hasSensorGap": False,
        "gapCoveragePct": 0.0,
        "isGapPlaceholder": True,
        "placeholderReason": message,
    }


def _resolve_generated_url(frame_id: str) -> Optional[str]:
    candidates = [
        os.path.join(INTERPOLATED_FRAMES_DIR, f"{frame_id}.png"),
        os.path.join(INTERPOLATED_FRAMES_DIR, f"{frame_id}.jpg"),
        os.path.join(GAP_PLACEHOLDERS_DIR, f"{frame_id}.png"),
        os.path.join(GAP_PLACEHOLDERS_DIR, f"{frame_id}.jpg"),
    ]
    for path in candidates:
        if os.path.exists(path):
            return _to_data_url(path)
    return None


def _resolve_catalog_path(frame: dict, prefer_clean: bool = False) -> str:
    candidate = frame.get("cleanImageUrl") if prefer_clean and frame.get("cleanImageUrl") else frame.get("imageUrl")
    if not candidate:
        raise ValueError(f"Frame is missing an image URL: {frame.get('timestamp')}")
    if candidate.startswith("/data/"):
        return os.path.join(DATA_DIR, candidate.replace("/data/", "", 1))
    return os.path.join(BASE_DIR, candidate.lstrip("/"))


def _to_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"


def _filename_to_timestamp(filename: str) -> str:
    wms_date = _filename_to_wms_date(filename)
    if wms_date:
        return wms_date
    stem = os.path.splitext(filename)[0]
    parts = stem.replace("frame_", "").split("_")
    if len(parts) >= 2:
        return f"{parts[0]}:{parts[1]}"
    return stem


def _filename_to_wms_date(filename: str) -> Optional[str]:
    stem = os.path.splitext(filename)[0]
    mapped = _RAW_FRAME_DATE_MAP.get(stem)
    if mapped:
        return mapped

    parts = stem.split("_")
    for candidate in reversed(parts):
        digits = "".join(ch for ch in candidate if ch.isdigit())
        if len(digits) >= 8:
            value = digits[:8]
            return f"{value[0:4]}-{value[4:6]}-{value[6:8]}"
    return None


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _interpolated_timestamp(start: str, end: str, ratio: float) -> str:
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)
    if start_dt is None or end_dt is None:
        return f"{start}::{end}::{ratio:.2f}"
    interpolated = start_dt + (end_dt - start_dt) * ratio
    return format_timestamp(interpolated)


def _sort_key(timestamp: str):
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return (1, timestamp)
    return (0, parsed.isoformat())


FRAME_CATALOG = build_frame_catalog()


@router.get("/frames")
async def get_all_frames():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {"status": "success", "frames": FRAME_CATALOG}


@router.get("/animation")
async def get_animation():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "total_frames": len(FRAME_CATALOG),
        "interval_seconds": 5,
        "frames": FRAME_CATALOG,
    }


@router.get("/frame")
async def get_frame_by_timestamp(timestamp: str):
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    for frame in FRAME_CATALOG:
        if frame["timestamp"] == timestamp:
            return {"status": "success", "frame": frame}
    raise HTTPException(status_code=404, detail=f"Frame with timestamp '{timestamp}' not found")


@router.post("/frames/fetch")
async def fetch_frames(request: FrameRetrievalRequest):
    logger.info("WMS Fetch request received for bbox: %s", request.bbox)
    try:
        from app.services.geospatial import apply_transparency
        from app.services.wms_client import fetch_wms_frames, get_wms_diagnostics

        retrieved = fetch_wms_frames(request)
        logger.info("Successfully fetched %d frames from WMS.", len(retrieved))

        for frame in retrieved:
            apply_transparency(frame["path"])

        global FRAME_CATALOG
        FRAME_CATALOG = build_frame_catalog()
        return {
            "status": "success",
            "fetched_frames": [f"/data/raw_frames/{os.path.basename(frame['path'])}" for frame in retrieved],
            "wms": get_wms_diagnostics(),
        }
    except Exception as exc:
        logger.error("WMS fetch failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    logger.info("Interpolation request: %s -> %s (steps=%s)", request.frame1_id, request.frame2_id, request.steps)
    try:
        from app.services.interpolation import generate_intermediate_frames, interpolator
        from app.services.metadata import generate_metadata_for_frame

        global FRAME_CATALOG
        FRAME_CATALOG = build_frame_catalog()
        frame1 = next((frame for frame in FRAME_CATALOG if frame["timestamp"] == request.frame1_id), None)
        frame2 = next((frame for frame in FRAME_CATALOG if frame["timestamp"] == request.frame2_id), None)
        if not frame1 or not frame2:
            raise HTTPException(status_code=404, detail="One or both frames not found in catalog")
        if not frame1.get("isOriginal") or not frame2.get("isOriginal"):
            raise HTTPException(status_code=422, detail="Interpolation is only allowed between observed frames")

        gap_minutes = gap_minutes_between(frame1["timestamp"], frame2["timestamp"])
        if gap_minutes is None:
            raise HTTPException(status_code=422, detail="Could not determine frame timestamps for interpolation")
        if gap_minutes > MAX_INTERPOLATION_GAP_MINUTES:
            raise HTTPException(status_code=422, detail="Interpolation disabled: gap exceeds 30 minutes")

        max_frames = recommended_interpolation_frames(gap_minutes)
        steps = max(1, min(request.steps, max_frames))
        if steps != request.steps:
            logger.info(
                "Clamped requested interpolation frames from %d to %d for gap %.2f minutes",
                request.steps,
                steps,
                gap_minutes,
            )

        frame1_path = _resolve_catalog_path(frame1, prefer_clean=True)
        frame2_path = _resolve_catalog_path(frame2, prefer_clean=True)
        safe_f1 = _safe_name(request.frame1_id)
        safe_f2 = _safe_name(request.frame2_id)

        generated_records = generate_intermediate_frames(
            frame1_path,
            frame2_path,
            INTERPOLATED_FRAMES_DIR,
            steps,
            file_prefix=f"interp_{safe_f1}_{safe_f2}",
        )

        new_frames = []
        diagnostics = interpolator.get_diagnostics()
        for record in generated_records:
            ratio = record["ratio"]
            timestamp = _interpolated_timestamp(frame1["timestamp"], frame2["timestamp"], ratio)
            score = score_generated_frame(
                record["path"],
                frame1_path,
                frame2_path,
                gap_minutes,
                LAST_CONFIDENCE_PROFILE,
            )

            rendered_as_gap = score["confidenceLabel"] == "REJECTED"
            output_path = record["path"]
            placeholder_reason = None
            if rendered_as_gap:
                placeholder_reason = "Rejected by adaptive confidence classifier"
                placeholder_name = f"{os.path.splitext(os.path.basename(record['path']))[0]}_rejected.png"
                output_path = os.path.join(GAP_PLACEHOLDERS_DIR, placeholder_name)
                create_gap_placeholder(output_path, timestamp, placeholder_reason, title="REJECTED FRAME")

            model_info = diagnostics["model"]
            generate_metadata_for_frame(
                output_path,
                frame1_path,
                frame2_path,
                timestamp,
                score["confidence"],
                confidence_label=score["confidenceLabel"],
                metrics=score["metrics"],
                source_timestamps=[frame1["timestamp"], frame2["timestamp"]],
                gap_minutes=score["gapMinutes"],
                confidence_method=score["confidenceMethod"],
                model_info=model_info,
                rendered_as_gap=rendered_as_gap,
                placeholder_reason=placeholder_reason,
            )

            new_frames.append({
                "timestamp": timestamp,
                "imageUrl": _to_data_url(output_path),
                "cleanImageUrl": _to_data_url(output_path),
                "rawImageUrl": None,
                "isOriginal": False,
                "confidence": score["confidence"],
                "confidenceLabel": score["confidenceLabel"],
                "confidenceMethod": score["confidenceMethod"],
                "metrics": score["metrics"],
                "sourceFrames": [frame1["timestamp"], frame2["timestamp"]],
                "gapMinutes": score["gapMinutes"],
                "bbox": frame1.get("bbox", INDIA_BBOX),
                "extent3857": frame1.get("extent3857", INDIA_EXTENT_3857),
                "hasSensorGap": False,
                "gapCoveragePct": 0.0,
                "isGapPlaceholder": rendered_as_gap,
                "placeholderReason": placeholder_reason,
            })

        FRAME_CATALOG = build_frame_catalog()
        return {
            "status": "success",
            "generated_frames": new_frames,
            "interpolation": interpolator.get_diagnostics(),
            "confidence": LAST_CONFIDENCE_PROFILE,
            "guardrail": {
                "gapMinutes": round(gap_minutes, 2),
                "maxFramesAllowed": max_frames,
                "appliedFrames": steps,
            },
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Interpolation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/video/export")
async def export_video(request: VideoExportRequest):
    try:
        from app.services.interpolation import interpolator
        from app.services.video_export import export_video_sequence

        result = export_video_sequence(
            [frame.dict() for frame in request.frames],
            fps=request.fps,
            raw_mode=request.raw_mode,
            job_name=request.job_name,
            model_info=interpolator.get_diagnostics()["model"],
        )
        return {"status": "success", "export": result}
    except Exception as exc:
        logger.exception("Video export failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/evaluation/run")
async def run_evaluation(request: EvaluationRequest):
    try:
        from app.services.evaluation import get_latest_evaluation, run_evaluation_suite

        report = run_evaluation_suite() if request.rerun else (get_latest_evaluation() or run_evaluation_suite())
        return {
            "status": "success",
            "evaluation": report,
            "reportUrl": "/data/evaluations/latest_evaluation.json",
        }
    except Exception as exc:
        logger.exception("Evaluation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/frames/refresh")
async def refresh_catalog():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {"status": "success", "total_frames": len(FRAME_CATALOG)}


@router.get("/diagnostics/status")
async def get_runtime_diagnostics():
    from app.services.evaluation import get_latest_evaluation
    from app.services.interpolation import interpolator
    from app.services.video_export import get_latest_export_summary
    from app.services.wms_client import get_wms_diagnostics

    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "catalog": {
            "frameCount": len(FRAME_CATALOG),
            "rawFramesDir": RAW_FRAMES_DIR,
            "interpolatedFramesDir": INTERPOLATED_FRAMES_DIR,
            "cleanFramesDir": CLEAN_FRAMES_DIR,
            "sensorGapMasksDir": SENSOR_GAP_MASKS_DIR,
            "gapPlaceholdersDir": GAP_PLACEHOLDERS_DIR,
            "source": "Disk-backed frame catalog. Fresh WMS fetches occur only via POST /api/frames/fetch.",
        },
        "wms": get_wms_diagnostics(),
        "interpolation": interpolator.get_diagnostics(),
        "confidence": LAST_CONFIDENCE_PROFILE,
        "export": get_latest_export_summary(),
        "evaluation": get_latest_evaluation(),
    }


@router.get("/metadata/{frame_id}", response_model=MetadataResponse)
async def get_metadata(frame_id: str):
    meta_path = os.path.join(METADATA_DIR, f"{frame_id}.json")
    if os.path.exists(meta_path):
        with open(meta_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return MetadataResponse(
            frame_id=frame_id,
            timestamp=data.get("time", frame_id),
            confidence_score=data.get("confidence", 0.95),
            is_interpolated=data.get("generated", True),
        )

    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    for frame in FRAME_CATALOG:
        if frame["timestamp"] == frame_id:
            return MetadataResponse(
                frame_id=frame_id,
                timestamp=frame_id,
                confidence_score=frame.get("confidence", 1.0),
                is_interpolated=not frame["isOriginal"],
            )

    raise HTTPException(status_code=404, detail="Metadata not found")
