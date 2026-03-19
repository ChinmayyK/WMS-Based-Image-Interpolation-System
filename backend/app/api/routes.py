from fastapi import APIRouter, HTTPException
from app.models import FrameRetrievalRequest, InterpolationRequest, MetadataResponse
import json
import os

router = APIRouter()

# Base path to data directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

# India bounding box [minLon, minLat, maxLon, maxLat]
INDIA_BBOX = [68.0, 6.0, 98.0, 36.0]

# Pre-computed EPSG:3857 extent [minX, minY, maxX, maxY] in metres
# (matches 960×1024 WMS request dimensions exactly — no transformExtent needed in frontend)
INDIA_EXTENT_3857 = [7569725.37, 669141.06, 10909310.10, 4300621.37]



def build_frame_catalog():
    """
    Dynamically build the frame catalog from files on disk.
    Scans raw_frames/ and interpolated_frames/ directories.
    """
    catalog = []

    # 1. Scan raw frames
    raw_dir = os.path.join(DATA_DIR, "raw_frames")
    if os.path.exists(raw_dir):
        for f in sorted(os.listdir(raw_dir)):
            if not f.endswith(".png") and not f.endswith(".jpg"):
                continue
            # Extract the date from the file if embedded, otherwise derive from filename index
            wms_date = _filename_to_wms_date(f)
            entry = {
                "timestamp": _filename_to_timestamp(f, is_raw=True),
                "imageUrl": f"/data/raw_frames/{f}",
                "isOriginal": True,
                "confidence": 1.0,
                "bbox": INDIA_BBOX,
                "extent3857": INDIA_EXTENT_3857,
                "wmsLayer": "MODIS_Terra_CorrectedReflectance_TrueColor",
            }
            if wms_date:
                entry["wmsDate"] = wms_date
            catalog.append(entry)


    # 2. Scan interpolated frames
    interp_dir = os.path.join(DATA_DIR, "interpolated_frames")
    if os.path.exists(interp_dir):
        for f in sorted(os.listdir(interp_dir)):
            if not f.startswith("interp_") or (not f.endswith(".png") and not f.endswith(".jpg")):
                continue
            # Parse ratio from filename (e.g., interp_frame_10_00_frame_25_00_50.png)
            ratio = _parse_ratio_from_filename(f)
            catalog.append({
                "timestamp": _filename_to_timestamp(f, is_raw=False),
                "imageUrl": f"/data/interpolated_frames/{f}",
                "isOriginal": False,
                "confidence": round(0.95 - 0.05 * (ratio / 100.0), 2) if ratio else 0.90,
                "bbox": INDIA_BBOX,
                "extent3857": INDIA_EXTENT_3857,
            })

    # Sort by timestamp string
    catalog.sort(key=lambda x: x["timestamp"])
    return catalog


def _filename_to_timestamp(filename, is_raw=True):
    """Convert a frame filename to a display timestamp."""
    name = os.path.splitext(filename)[0]
    if is_raw:
        # Try to map known raw frame names to real dates
        date = _filename_to_wms_date(filename)
        if date:
            return date
        parts = name.replace("frame_", "").split("_")
        if len(parts) >= 2:
            return f"{parts[0]}:{parts[1]}"
        return name
    else:
        # e.g., interp_frame_10_00_frame_25_00_50 → meaningful interpolated timestamp
        # Extract source dates and ratio
        try:
            name_clean = name.replace("interp_", "")
            # Find the ratio at the end
            last_underscore = name_clean.rfind("_")
            ratio_str = name_clean[last_underscore + 1:]
            ratio = int(ratio_str)
            # Find source frame labels
            body = name_clean[:last_underscore]
            parts = body.split("_frame_")
            if len(parts) == 2:
                d1 = _filename_to_wms_date(f"frame_{parts[0]}.png") or parts[0]
                d2 = _filename_to_wms_date(f"frame_{parts[1]}.png") or parts[1]
                # Compute interpolated date
                if d1 and d2 and "-" in d1 and "-" in d2:
                    from datetime import datetime, timedelta
                    dt1 = datetime.strptime(d1, "%Y-%m-%d")
                    dt2 = datetime.strptime(d2, "%Y-%m-%d")
                    delta = (dt2 - dt1).total_seconds() * ratio / 100
                    interp_dt = dt1 + timedelta(seconds=delta)
                    return interp_dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            pass
        return name.replace("interp_", "").replace("_", ":")


# Mapping from raw frame filename stem → actual WMS date fetched
# This is populated from DATES in fetch_satellite_data.py:
#   frame_10_00 → 2024-06-01
#   frame_25_00 → 2024-06-02
#   frame_40_00 → 2024-06-03
_RAW_FRAME_DATE_MAP = {
    "frame_10_00": "2024-06-01",
    "frame_25_00": "2024-06-02",
    "frame_40_00": "2024-06-03",
}


def _filename_to_wms_date(filename):
    """Return the WMS date string (YYYY-MM-DD) for a raw frame file, or None."""
    stem = os.path.splitext(filename)[0]
    return _RAW_FRAME_DATE_MAP.get(stem)




def _parse_ratio_from_filename(filename):
    """Extract interpolation ratio from filename. e.g., ...50.png → 50."""
    name = os.path.splitext(filename)[0]
    parts = name.split("_")
    try:
        return int(parts[-1])
    except (ValueError, IndexError):
        return 50


# Build initial catalog from whatever is on disk
FRAME_CATALOG = build_frame_catalog()


# ── GET endpoints ──────────────────────────────────────────

@router.get("/frames")
async def get_all_frames():
    """Returns the full list of frames (raw + interpolated) ordered by time."""
    global FRAME_CATALOG
    if not FRAME_CATALOG:
        FRAME_CATALOG = build_frame_catalog()
    return {"status": "success", "frames": FRAME_CATALOG}


@router.get("/animation")
async def get_animation():
    """Returns ordered frame sequence for the animation player."""
    global FRAME_CATALOG
    if not FRAME_CATALOG:
        FRAME_CATALOG = build_frame_catalog()
    return {
        "status": "success",
        "total_frames": len(FRAME_CATALOG),
        "interval_seconds": 5,
        "frames": FRAME_CATALOG,
    }


@router.get("/frame")
async def get_frame_by_timestamp(timestamp: str):
    """Returns a single frame by its timestamp."""
    for frame in FRAME_CATALOG:
        if frame["timestamp"] == timestamp:
            return {"status": "success", "frame": frame}
    raise HTTPException(status_code=404, detail=f"Frame with timestamp '{timestamp}' not found")


# ── POST endpoints (for pipeline triggers) ───────────────────

@router.post("/frames/fetch")
async def fetch_frames(request: FrameRetrievalRequest):
    """Fetches frames from a WMS endpoint based on temporal and spatial bounds."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"WMS Fetch request received for bbox: {request.bbox}")
    try:
        from app.services.wms_client import fetch_wms_frames
        from app.services.geospatial import apply_transparency

        # Real fetch from NASA GIBS or specified WMS
        retrieved = fetch_wms_frames(request)
        logger.info(f"Successfully fetched {len(retrieved)} frames from WMS.")

        # Clear/Update catalog with real data
        global FRAME_CATALOG
        new_catalog = []
        for frame in retrieved:
            # Apply transparency mask to remove black backgrounds
            apply_transparency(frame['path'])

            img_url = f"/data/frames/{os.path.basename(frame['path'])}"
            new_entry = {
                "timestamp": frame["timestamp"],
                "imageUrl": img_url,
                "isOriginal": True,
                "confidence": 1.0,
                "bbox": list(request.bbox),
            }
            new_catalog.append(new_entry)

        FRAME_CATALOG = sorted(new_catalog, key=lambda x: x["timestamp"])

        return {"status": "success", "fetched_frames": [f["imageUrl"] for f in new_catalog]}
    except Exception as e:
        logger.error(f"WMS fetch failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    """Runs the RIFE model to generate intermediate frames."""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Interpolation request: {request.frame1_id} -> {request.frame2_id} (steps: {request.steps})")
    try:
        from app.services.interpolation import generate_intermediate_frames
        from app.services.metadata import generate_metadata_for_frame

        # Find the frame paths from FRAME_CATALOG
        f1 = next((f for f in FRAME_CATALOG if f["timestamp"] == request.frame1_id), None)
        f2 = next((f for f in FRAME_CATALOG if f["timestamp"] == request.frame2_id), None)

        if not f1 or not f2:
            raise HTTPException(status_code=404, detail="One or both frames not found in catalog")

        idx1 = FRAME_CATALOG.index(f1)

        # Absolute paths for OpenCV/Torch
        f1_path = os.path.join(BASE_DIR, f1["imageUrl"].lstrip('/'))
        f2_path = os.path.join(BASE_DIR, f2["imageUrl"].lstrip('/'))

        out_dir = os.path.join(DATA_DIR, "interpolated_frames")

        # Windows-safe identifiers
        safe_f1 = request.frame1_id.replace(":", "-")
        safe_f2 = request.frame2_id.replace(":", "-")

        logger.info(f"Running RIFE interpolation between {f1_path} and {f2_path}")
        generated_paths = generate_intermediate_frames(
            f1_path, f2_path, out_dir, request.steps, file_prefix=f"interp_{safe_f1}_{safe_f2}"
        )
        logger.info(f"Generated {len(generated_paths)} frames successfully.")

        new_frames = []
        for i, path in enumerate(generated_paths):
            ratio = (i + 1) / (request.steps + 1)
            new_ts = f"interp_{safe_f1}_{safe_f2}_{i+1}"
            confidence = round(0.95 - (0.05 * ratio), 2)

            generate_metadata_for_frame(path, f1_path, f2_path, new_ts, confidence)

            img_url = f"/data/interpolated_frames/{os.path.basename(path)}"
            new_entry = {
                "timestamp": new_ts,
                "imageUrl": img_url,
                "isOriginal": False,
                "confidence": confidence,
                "sourceFrames": [request.frame1_id, request.frame2_id],
                "bbox": f1.get("bbox", INDIA_BBOX),
            }
            new_frames.append(new_entry)

        # Insert into catalog
        FRAME_CATALOG[idx1+1:idx1+1] = new_frames

        return {"status": "success", "generated_frames": [f["imageUrl"] for f in new_frames]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Interpolation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frames/refresh")
async def refresh_catalog():
    """Rebuild the frame catalog from disk."""
    global FRAME_CATALOG
    FRAME_CATALOG = build_frame_catalog()
    return {"status": "success", "total_frames": len(FRAME_CATALOG)}


@router.get("/metadata/{frame_id}", response_model=MetadataResponse)
async def get_metadata(frame_id: str):
    """Retrieves metadata and confidence score for a frame."""
    meta_path = os.path.join(DATA_DIR, "metadata", f"{frame_id}.json")

    if os.path.exists(meta_path):
        with open(meta_path, 'r') as f:
            data = json.load(f)
            return MetadataResponse(
                frame_id=frame_id,
                timestamp=data.get("time", frame_id),
                confidence_score=data.get("confidence", 0.95),
                is_interpolated=data.get("generated", True)
            )

    # Fallback to catalog lookup
    for frame in FRAME_CATALOG:
        if frame["timestamp"] == frame_id:
            return MetadataResponse(
                frame_id=frame_id,
                timestamp=frame_id,
                confidence_score=frame.get("confidence", 1.0),
                is_interpolated=not frame["isOriginal"]
            )

    raise HTTPException(status_code=404, detail="Metadata not found")
