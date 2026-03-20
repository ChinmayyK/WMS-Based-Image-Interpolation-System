import json
import logging
import os
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
    provenance_label_for,
    recommended_interpolation_frames,
    score_generated_frame,
    score_generated_sequence,
)
from app.services.metadata import (
    get_interpolation_log_path,
    generate_metadata_for_frame,
    get_metadata_dir,
    get_observed_session_path,
    load_interpolation_log,
    load_observed_session,
    persist_observed_session,
)
from app.services.preprocessing import (
    ensure_session_preprocessed,
    get_preprocessing_report_path,
    load_preprocessing_report,
)
from app.services.visualization import create_gap_placeholder


router = APIRouter()
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
RAW_FRAMES_DIR = os.path.join(DATA_DIR, "raw_frames")
INTERPOLATED_FRAMES_DIR = os.path.join(DATA_DIR, "interpolated_frames")
METADATA_DIR = get_metadata_dir()
GAP_PLACEHOLDERS_DIR = os.path.join(DATA_DIR, "gap_placeholders")

FRAME_CATALOG = []
LAST_CONFIDENCE_PROFILE = {}


def _safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value)


def _sort_key(timestamp: str):
    parsed = parse_timestamp(timestamp)
    if parsed is None:
        return (1, timestamp)
    return (0, parsed.isoformat())


def _to_data_url(path: str) -> str:
    rel = os.path.relpath(path, DATA_DIR).replace(os.sep, "/")
    return f"/data/{rel}"


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


def _resolve_data_asset_path(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("/data/"):
        return os.path.join(DATA_DIR, url.replace("/data/", "", 1))
    return os.path.join(BASE_DIR, url.lstrip("/"))


def _resolve_catalog_path(frame: dict, prefer_clean: bool = False) -> str:
    candidate = frame.get("cleanImageUrl") if prefer_clean and frame.get("cleanImageUrl") else frame.get("imageUrl")
    if not candidate:
        raise ValueError(f"Frame is missing an image URL: {frame.get('timestamp')}")
    if candidate.startswith("/data/"):
        return os.path.join(DATA_DIR, candidate.replace("/data/", "", 1))
    return os.path.join(BASE_DIR, candidate.lstrip("/"))


def _interpolated_timestamp(start: str, end: str, ratio: float) -> str:
    start_dt = parse_timestamp(start)
    end_dt = parse_timestamp(end)
    if start_dt is None or end_dt is None:
        return f"{start}::{end}::{ratio:.2f}"
    interpolated = start_dt + (end_dt - start_dt) * ratio
    return format_timestamp(interpolated)


def _load_session() -> Optional[dict]:
    session = load_observed_session()
    if not session:
        return None

    processed_session = ensure_session_preprocessed(session)
    if session != processed_session:
        persist_observed_session(processed_session)
    return processed_session


def _session_metadata_url() -> str:
    return "/data/metadata/observed_session.json"


def _session_summary(session: Optional[dict]) -> Optional[dict]:
    if not session:
        return None
    preprocessing = session.get("preprocessing") or {}
    return {
        "sessionId": session.get("session_id"),
        "source": session.get("source"),
        "layer": session.get("layer"),
        "title": session.get("title"),
        "bbox": session.get("bbox"),
        "extent3857": session.get("extent3857"),
        "crs": session.get("crs"),
        "wmsUrl": session.get("wmsUrl"),
        "requestedStartTime": session.get("requestedStartTime"),
        "requestedEndTime": session.get("requestedEndTime"),
        "availableStartTime": session.get("availableStartTime"),
        "availableEndTime": session.get("availableEndTime"),
        "availableFrameCount": session.get("availableFrameCount", 0),
        "downloadedFrameCount": session.get("downloadedFrameCount", 0),
        "failedFrameCount": len(session.get("failedTimestamps") or []),
        "failedTimestamps": session.get("failedTimestamps") or [],
        "cadenceMinutes": session.get("cadenceMinutes") or {},
        "validation": session.get("validation") or {},
        "metadataUrl": _session_metadata_url(),
        "preprocessing": {
            "version": preprocessing.get("version"),
            "reportUrl": preprocessing.get("reportUrl"),
            "validFrameCount": preprocessing.get("validFrameCount", 0),
            "missingFrameCount": preprocessing.get("missingFrameCount", 0),
            "calibrationIssueCount": preprocessing.get("calibrationIssueCount", 0),
            "flaggedFrameCount": preprocessing.get("flaggedFrameCount", 0),
        },
    }


def _build_observed_frames(session: Optional[dict] = None):
    session = session or _load_session()
    if not session:
        return []

    extent = session.get("extent3857") or session.get("bbox")
    deduped = {}

    for source in session.get("frames") or []:
        validation = source.get("validation") or {}
        preprocessing_flags = source.get("flags") or validation.get("flags") or []
        if not validation.get("valid", source.get("valid", False)):
            continue

        filename = source.get("filename") or os.path.basename(source.get("path", ""))
        path = source.get("path") or os.path.join(RAW_FRAMES_DIR, filename)
        if not filename or not os.path.exists(path):
            continue

        raw_image_url = source.get("url") or f"/data/raw_frames/{filename}"
        image_url = source.get("normalizedUrl") or raw_image_url
        entry = {
            "timestamp": source.get("timestamp") or source.get("wmsTime") or filename,
            "wmsTime": source.get("wmsTime"),
            "imageUrl": image_url,
            "rawImageUrl": raw_image_url,
            "cleanImageUrl": image_url,
            "normalizedImageUrl": source.get("normalizedUrl"),
            "isOriginal": True,
            "type": source.get("type", "OBSERVED"),
            "source": source.get("source") or session.get("source"),
            "confidence": 1.0,
            "confidenceLabel": "OBSERVED",
            "confidenceMethod": "Observed GOES frame",
            "metrics": {},
            "bbox": source.get("bbox") or session.get("bbox"),
            "extent3857": extent,
            "wmsLayer": source.get("layer") or session.get("layer"),
            "wmsUrl": session.get("wmsUrl"),
            "wmsCrs": source.get("crs") or session.get("crs") or "EPSG:3857",
            "isGapPlaceholder": False,
            "hasSensorGap": float(source.get("nodataRatio", 0.0)) > 0.0,
            "gapCoveragePct": round(float(source.get("nodataRatio", 0.0)) * 100.0, 3),
            "gapFillMethod": "Radiometric normalization + NoData masking",
            "gapMaskUrl": source.get("nodataMaskUrl"),
            "nodataMaskUrl": source.get("nodataMaskUrl"),
            "limbMaskUrl": source.get("limbMaskUrl"),
            "terminatorMaskUrl": source.get("terminatorMaskUrl"),
            "isValid": True,
            "validationIssues": validation.get("issues", []),
            "preprocessingFlags": preprocessing_flags,
        }

        previous = deduped.get(entry["timestamp"])
        if previous is None or os.path.getmtime(path) >= previous["_mtime"]:
            deduped[entry["timestamp"]] = {**entry, "_mtime": os.path.getmtime(path)}

    observed = [
        {key: value for key, value in entry.items() if key != "_mtime"}
        for entry in deduped.values()
    ]
    observed.sort(key=lambda frame: _sort_key(frame["timestamp"]))
    return observed


def _load_generated_frames(session: Optional[dict] = None):
    session = session or _load_session()
    session_id = session.get("session_id") if session else None
    generated = {}

    if not os.path.isdir(METADATA_DIR):
        return generated

    for filename in sorted(os.listdir(METADATA_DIR)):
        if not filename.endswith(".json") or filename in {"session_confidence_profile.json", os.path.basename(get_observed_session_path())}:
            continue

        path = os.path.join(METADATA_DIR, filename)
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)

        if not isinstance(data, dict) or not data.get("generated"):
            continue
        if session_id and data.get("session_id") != session_id:
            continue
        if not session_id and data.get("session_id"):
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
            "type": data.get("type", "INTERPOLATED"),
            "source": session.get("source") if session else None,
            "confidence": data.get("confidence", 0.0),
            "confidenceLabel": data.get("confidence_label") or classify_confidence(data.get("confidence", 0.0)),
            "provenanceLabel": data.get("provenance_label"),
            "confidenceMethod": data.get("confidence_method"),
            "metrics": data.get("metrics") or {},
            "sourceFrames": source_timestamps,
            "gapMinutes": data.get("gap_minutes"),
            "bbox": session.get("bbox") if session else None,
            "extent3857": (session.get("extent3857") if session else None),
            "hasSensorGap": False,
            "gapCoveragePct": 0.0,
            "isGapPlaceholder": bool(data.get("rendered_as_gap")),
            "placeholderReason": data.get("placeholder_reason"),
            "modelInfo": data.get("model") or {},
            "nodataMaskUrl": ((data.get("masks") or {}).get("nodata") or {}).get("url"),
            "limbMaskUrl": ((data.get("masks") or {}).get("limb") or {}).get("url"),
            "terminatorMaskUrl": ((data.get("masks") or {}).get("terminator") or {}).get("url"),
            "fallbackUsed": (data.get("interpolation") or {}).get("fallbackUsed", False),
            "fallbackMethod": (data.get("interpolation") or {}).get("fallbackMethod"),
            "inferenceTimeMs": (data.get("interpolation") or {}).get("inferenceTimeMs"),
            "motionInfo": data.get("motion") or {},
            "audit": data.get("audit") or {},
            "wmsLayer": session.get("layer") if session else None,
            "wmsUrl": session.get("wmsUrl") if session else None,
            "wmsCrs": session.get("crs") if session else "EPSG:3857",
        }
        generated.setdefault(pair_key, []).append(entry)

    return generated


def _build_gap_placeholder_entry(left_frame: dict, right_frame: dict, gap_minutes: float):
    midpoint = midpoint_timestamp(left_frame["timestamp"], right_frame["timestamp"]) or left_frame["timestamp"]
    placeholder_name = f"gap_{_safe_name(left_frame['timestamp'])}_{_safe_name(right_frame['timestamp'])}.png"
    placeholder_path = os.path.join(GAP_PLACEHOLDERS_DIR, placeholder_name)
    message = "Interpolation disabled: observed gap exceeds 30 minutes"
    create_gap_placeholder(placeholder_path, midpoint, message)
    return {
        "timestamp": midpoint,
        "imageUrl": _to_data_url(placeholder_path),
        "cleanImageUrl": _to_data_url(placeholder_path),
        "rawImageUrl": None,
        "isOriginal": False,
        "type": "GAP",
        "source": left_frame.get("source"),
        "confidence": 0.0,
        "confidenceLabel": "GAP",
        "confidenceMethod": "Temporal guardrail",
        "metrics": {},
        "sourceFrames": [left_frame["timestamp"], right_frame["timestamp"]],
        "gapMinutes": round(gap_minutes, 2),
        "bbox": left_frame.get("bbox"),
        "extent3857": left_frame.get("extent3857"),
        "hasSensorGap": False,
        "gapCoveragePct": 0.0,
        "isGapPlaceholder": True,
        "placeholderReason": message,
        "wmsLayer": left_frame.get("wmsLayer"),
        "wmsUrl": left_frame.get("wmsUrl"),
        "wmsCrs": left_frame.get("wmsCrs"),
    }


def build_frame_catalog():
    session = _load_session()
    observed_frames = _build_observed_frames(session)

    confidence_profile = build_session_confidence_profile(
        [
            {
                "timestamp": frame["timestamp"],
                "path": _resolve_catalog_path(frame, prefer_clean=True),
                "nodataMaskPath": _resolve_data_asset_path(frame.get("nodataMaskUrl")),
                "limbMaskPath": _resolve_data_asset_path(frame.get("limbMaskUrl")),
                "terminatorMaskPath": _resolve_data_asset_path(frame.get("terminatorMaskUrl")),
                "flags": frame.get("preprocessingFlags") or [],
            }
            for frame in observed_frames
        ]
    )
    persist_session_confidence_profile(confidence_profile, METADATA_DIR)

    generated_by_pair = _load_generated_frames(session)
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
    LAST_CONFIDENCE_PROFILE = confidence_profile
    return catalog


FRAME_CATALOG = build_frame_catalog()


@router.get("/frames")
async def get_all_frames():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "frames": FRAME_CATALOG,
        "session": _session_summary(_load_session()),
    }


@router.get("/animation")
async def get_animation():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "total_frames": len(FRAME_CATALOG),
        "interval_seconds": 1,
        "frames": FRAME_CATALOG,
        "session": _session_summary(_load_session()),
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
    logger.info(
        "GOES time-series fetch request received | bbox=%s | start=%s | end=%s | layer=%s",
        request.bbox,
        request.start_time,
        request.end_time,
        request.layers,
    )
    try:
        from app.services.wms_client import fetch_time_series, get_wms_diagnostics

        result = fetch_time_series(request)
        processed_session = ensure_session_preprocessed(result["session"], force=True)
        persist_observed_session(processed_session)

        global FRAME_CATALOG
        FRAME_CATALOG = build_frame_catalog()
        return {
            "status": "success",
            "frames": FRAME_CATALOG,
            "fetched_frames": [f"/data/raw_frames/{os.path.basename(frame['path'])}" for frame in result["frames"]],
            "session": _session_summary(processed_session),
            "wms": get_wms_diagnostics(),
            "preprocessing": load_preprocessing_report(),
        }
    except Exception as exc:
        logger.exception("GOES WMS fetch failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/wms/layer-info")
async def get_wms_layer_info(layer: str, crs: str = "EPSG:3857", provider: str = "auto"):
    try:
        from app.services.wms_client import (
            _format_wms_time,
            get_layer_capabilities,
            get_latest_available_timestamp,
            resolve_provider,
            resolve_source_label,
            resolve_wms_url,
        )

        resolved_provider = resolve_provider(layer, provider)
        capabilities = get_layer_capabilities(layer, crs, resolved_provider)
        latest_available = get_latest_available_timestamp(capabilities["timeDimension"])
        return {
            "status": "success",
            "layer": layer,
            "provider": resolved_provider,
            "source": resolve_source_label(layer, resolved_provider),
            "crs": crs,
            "wmsUrl": resolve_wms_url(crs, resolved_provider),
            "title": capabilities.get("title"),
            "defaultTime": capabilities.get("defaultTime"),
            "latestAvailableTime": _format_wms_time(latest_available) if latest_available else None,
            "timeDimension": capabilities.get("timeDimension"),
        }
    except Exception as exc:
        logger.exception("WMS layer info lookup failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    logger.info("Interpolation request: %s -> %s (steps=%s)", request.frame1_id, request.frame2_id, request.steps)
    try:
        from app.services.interpolation import generate_intermediate_frames, interpolator

        global FRAME_CATALOG
        FRAME_CATALOG = build_frame_catalog()
        frame1 = next((frame for frame in FRAME_CATALOG if frame["timestamp"] == request.frame1_id), None)
        frame2 = next((frame for frame in FRAME_CATALOG if frame["timestamp"] == request.frame2_id), None)
        if not frame1 or not frame2:
            raise HTTPException(status_code=404, detail="One or both frames not found in catalog")
        if not frame1.get("isOriginal") or not frame2.get("isOriginal"):
            raise HTTPException(status_code=422, detail="Interpolation is only allowed between observed frames")
        if frame1.get("isValid") is False or frame2.get("isValid") is False:
            raise HTTPException(status_code=422, detail="Interpolation is only allowed for preprocessing-valid observed frames")

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
        frame1_context = {
            "nodataMaskPath": _resolve_data_asset_path(frame1.get("nodataMaskUrl")),
            "limbMaskPath": _resolve_data_asset_path(frame1.get("limbMaskUrl")),
            "terminatorMaskPath": _resolve_data_asset_path(frame1.get("terminatorMaskUrl")),
        }
        frame2_context = {
            "nodataMaskPath": _resolve_data_asset_path(frame2.get("nodataMaskUrl")),
            "limbMaskPath": _resolve_data_asset_path(frame2.get("limbMaskUrl")),
            "terminatorMaskPath": _resolve_data_asset_path(frame2.get("terminatorMaskUrl")),
        }
        safe_f1 = _safe_name(request.frame1_id)
        safe_f2 = _safe_name(request.frame2_id)
        active_session = _load_session() or {}

        generated_records = generate_intermediate_frames(
            frame1_path,
            frame2_path,
            INTERPOLATED_FRAMES_DIR,
            steps,
            file_prefix=f"interp_{safe_f1}_{safe_f2}",
            frame0_context=frame1_context,
            frame1_context=frame2_context,
        )

        new_frames = []
        diagnostics = interpolator.get_diagnostics()
        source_frame0_score_context = {
            "path": frame1_path,
            "nodataMaskPath": frame1_context["nodataMaskPath"],
            "limbMaskPath": frame1_context["limbMaskPath"],
            "terminatorMaskPath": frame1_context["terminatorMaskPath"],
            "flags": frame1.get("preprocessingFlags") or frame1.get("flags") or [],
        }
        source_frame1_score_context = {
            "path": frame2_path,
            "nodataMaskPath": frame2_context["nodataMaskPath"],
            "limbMaskPath": frame2_context["limbMaskPath"],
            "terminatorMaskPath": frame2_context["terminatorMaskPath"],
            "flags": frame2.get("preprocessingFlags") or frame2.get("flags") or [],
        }
        scored_records = score_generated_sequence(
            generated_records,
            frame1_path,
            frame2_path,
            gap_minutes,
            LAST_CONFIDENCE_PROFILE,
            source_frame0=source_frame0_score_context,
            source_frame1=source_frame1_score_context,
        )

        for record, score in zip(generated_records, scored_records):
            ratio = record["ratio"]
            timestamp = _interpolated_timestamp(frame1["timestamp"], frame2["timestamp"], ratio)
            run = record.get("interpolation") or {}
            mask_info = record.get("maskInfo") or {}
            motion_info = record.get("motion") or {}

            rendered_as_gap = score["confidenceLabel"] == "REJECTED"
            output_path = record["path"]
            placeholder_reason = None
            if rendered_as_gap:
                placeholder_reason = "Rejected by adaptive confidence classifier"
                placeholder_name = f"{os.path.splitext(os.path.basename(record['path']))[0]}_rejected.png"
                output_path = os.path.join(GAP_PLACEHOLDERS_DIR, placeholder_name)
                create_gap_placeholder(output_path, timestamp, placeholder_reason, title="REJECTED FRAME")

            model_info = diagnostics["model"]
            batch_info = diagnostics["execution"].get("lastBatch") or {}
            generate_metadata_for_frame(
                output_path,
                frame1_path,
                frame2_path,
                timestamp,
                score["confidence"],
                confidence_label=score["confidenceLabel"],
                provenance_label=score.get("provenanceLabel") or provenance_label_for(score["confidenceLabel"]),
                metrics=score["metrics"],
                source_timestamps=[frame1["timestamp"], frame2["timestamp"]],
                gap_minutes=score["gapMinutes"],
                confidence_method=score["confidenceMethod"],
                model_info=model_info,
                rendered_as_gap=rendered_as_gap,
                placeholder_reason=placeholder_reason,
                session_id=active_session.get("session_id"),
                frame_type="GAP" if rendered_as_gap else "INTERPOLATED",
                interpolation={
                    "jobId": batch_info.get("jobId"),
                    "strategy": batch_info.get("strategy"),
                    "executionMode": run.get("executionMode"),
                    "fallbackUsed": run.get("fallbackUsed", False),
                    "fallbackMethod": run.get("fallbackMethod"),
                    "fallbackReason": run.get("fallbackReason"),
                    "inferenceTimeMs": run.get("durationMs"),
                    "recursionDepth": record.get("recursionDepth"),
                    "tileInfo": run.get("tileInfo"),
                    "suspiciousRuntime": run.get("suspiciousRuntime", False),
                    "warnings": run.get("warnings", []),
                    "errors": run.get("errors", []),
                },
                masks={
                    key: value for key, value in {
                        "nodata": mask_info.get("nodata"),
                        "limb": mask_info.get("limb"),
                        "terminator": mask_info.get("terminator"),
                    }.items() if value
                },
                motion=motion_info,
                audit={
                    "jobId": batch_info.get("jobId"),
                    "logPath": batch_info.get("auditLogPath"),
                    "logUrl": batch_info.get("auditLogUrl"),
                    "batchTotalInferenceTimeMs": batch_info.get("totalInferenceTimeMs"),
                },
            )

            new_frames.append(
                {
                    "timestamp": timestamp,
                    "imageUrl": _to_data_url(output_path),
                    "cleanImageUrl": _to_data_url(output_path),
                    "rawImageUrl": None,
                    "isOriginal": False,
                    "type": "GAP" if rendered_as_gap else "INTERPOLATED",
                    "source": frame1.get("source"),
                    "confidence": score["confidence"],
                    "confidenceLabel": score["confidenceLabel"],
                    "provenanceLabel": score.get("provenanceLabel"),
                    "confidenceMethod": score["confidenceMethod"],
                    "metrics": score["metrics"],
                    "sourceFrames": [frame1["timestamp"], frame2["timestamp"]],
                    "gapMinutes": score["gapMinutes"],
                    "bbox": frame1.get("bbox"),
                    "extent3857": frame1.get("extent3857"),
                    "hasSensorGap": False,
                    "gapCoveragePct": 0.0,
                    "isGapPlaceholder": rendered_as_gap,
                    "placeholderReason": placeholder_reason,
                    "nodataMaskUrl": (mask_info.get("nodata") or {}).get("url"),
                    "limbMaskUrl": (mask_info.get("limb") or {}).get("url"),
                    "terminatorMaskUrl": (mask_info.get("terminator") or {}).get("url"),
                    "fallbackUsed": run.get("fallbackUsed", False),
                    "fallbackMethod": run.get("fallbackMethod"),
                    "inferenceTimeMs": run.get("durationMs"),
                    "motionInfo": motion_info,
                    "audit": {
                        "jobId": batch_info.get("jobId"),
                        "logUrl": batch_info.get("auditLogUrl"),
                    },
                    "modelInfo": model_info,
                    "wmsLayer": frame1.get("wmsLayer"),
                    "wmsUrl": frame1.get("wmsUrl"),
                    "wmsCrs": frame1.get("wmsCrs"),
                }
            )

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
            "jsonReportUrl": "/data/evaluations/latest_evaluation.json",
            "htmlReportUrl": "/data/evaluations/latest_evaluation.html",
        }
    except Exception as exc:
        logger.exception("Evaluation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/frames/refresh")
async def refresh_catalog():
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "total_frames": len(FRAME_CATALOG),
        "session": _session_summary(_load_session()),
    }


@router.get("/diagnostics/status")
async def get_runtime_diagnostics():
    from app.services.evaluation import get_latest_evaluation
    from app.services.interpolation import interpolator
    from app.services.video_export import get_latest_export_summary
    from app.services.wms_client import get_wms_diagnostics

    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    session = _load_session()
    return {
        "status": "success",
        "catalog": {
            "frameCount": len(FRAME_CATALOG),
            "rawFramesDir": RAW_FRAMES_DIR,
            "interpolatedFramesDir": INTERPOLATED_FRAMES_DIR,
            "gapPlaceholdersDir": GAP_PLACEHOLDERS_DIR,
            "source": "Session-backed GOES time series catalog. Refresh observed frames via POST /api/frames/fetch.",
            "sessionMetadataPath": get_observed_session_path(),
            "preprocessingReportPath": get_preprocessing_report_path(),
            "interpolationLogPath": get_interpolation_log_path(),
        },
        "session": _session_summary(session),
        "wms": get_wms_diagnostics(),
        "preprocessing": load_preprocessing_report(),
        "interpolation": interpolator.get_diagnostics(),
        "interpolationLog": load_interpolation_log(),
        "confidence": LAST_CONFIDENCE_PROFILE,
        "export": get_latest_export_summary(),
        "evaluation": get_latest_evaluation(),
    }


@router.get("/preprocessing/report")
async def get_preprocessing_report():
    session = _load_session()
    if not session:
        raise HTTPException(status_code=404, detail="No observed GOES session is available.")

    report = load_preprocessing_report()
    if not report:
        raise HTTPException(status_code=404, detail="Preprocessing report not found.")
    return {
        "status": "success",
        "report": report,
        "session": _session_summary(session),
    }


@router.get("/interpolation/log")
async def get_interpolation_log():
    from app.services.interpolation import interpolator

    return {
        "status": "success",
        "log": load_interpolation_log(),
        "path": get_interpolation_log_path(),
        "interpolation": interpolator.get_diagnostics(),
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
            is_interpolated=data.get("type") != "OBSERVED",
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
