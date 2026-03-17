from fastapi import APIRouter, HTTPException
from app.models import FrameRetrievalRequest, InterpolationRequest, MetadataResponse
import json
import os

router = APIRouter()

# Base path to data directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")

# ── Frame catalog (ordered by time) ──────────────────────────
FRAME_CATALOG = [
    {
        "timestamp": "10:00",
        "imageUrl": "/data/raw_frames/frame_10_00.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_00_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_00_vectors.json",
        "isOriginal": True,
        "confidence": 1.0,
    },
    {
        "timestamp": "10:05",
        "imageUrl": "/data/interpolated_frames/frame_10_05.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_05_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_05_vectors.json",
        "isOriginal": False,
        "confidence": 0.94,
        "sourceFrames": ["10:00", "10:30"],
    },
    {
        "timestamp": "10:10",
        "imageUrl": "/data/interpolated_frames/frame_10_10.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_10_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_10_vectors.json",
        "isOriginal": False,
        "confidence": 0.87,
        "sourceFrames": ["10:00", "10:30"],
    },
    {
        "timestamp": "10:15",
        "imageUrl": "/data/interpolated_frames/frame_10_15.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_15_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_15_vectors.json",
        "isOriginal": False,
        "confidence": 0.82,
        "sourceFrames": ["10:00", "10:30"],
    },
    {
        "timestamp": "10:20",
        "imageUrl": "/data/interpolated_frames/frame_10_20.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_20_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_20_vectors.json",
        "isOriginal": False,
        "confidence": 0.89,
        "sourceFrames": ["10:00", "10:30"],
    },
    {
        "timestamp": "10:25",
        "imageUrl": "/data/interpolated_frames/frame_10_25.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_25_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_25_vectors.json",
        "isOriginal": False,
        "confidence": 0.91,
        "sourceFrames": ["10:00", "10:30"],
    },
    {
        "timestamp": "10:30",
        "imageUrl": "/data/raw_frames/frame_10_30.png",
        "cloudMaskUrl": "/data/cloud_masks/frame_10_30_cloud.png",
        "vectorsUrl": "/data/motion_vectors/frame_10_30_vectors.json",
        "isOriginal": True,
        "confidence": 1.0,
    },
]


# ── GET endpoints (what the frontend needs) ──────────────────

@router.get("/frames")
async def get_all_frames():
    """Returns the full list of frames (raw + interpolated) ordered by time."""
    return {"status": "success", "frames": FRAME_CATALOG}


@router.get("/animation")
async def get_animation():
    """Returns ordered frame sequence for the animation player."""
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
        
        # Real fetch from NASA GIBS or specified WMS
        retrieved = fetch_wms_frames(request)
        logger.info(f"Successfully fetched {len(retrieved)} frames from WMS.")
        
        # Clear/Update demo catalog with real data
        global FRAME_CATALOG
        new_catalog = []
        for frame in retrieved:
            # Construct a catalog entry
            img_url = f"/data/frames/{os.path.basename(frame['path'])}"
            new_entry = {
                "timestamp": frame["timestamp"],
                "imageUrl": img_url,
                "cloudMaskUrl": None,
                "vectorsUrl": None,
                "isOriginal": True,
                "confidence": 1.0,
            }
            new_catalog.append(new_entry)
            
        # For simplicity in this demo, we replace the catalog
        # In a real app, we would append and sort
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
    logger.info(f"Interpolation request received: {request.frame1_id} -> {request.frame2_id} (steps: {request.steps})")
    try:
        from app.services.interpolation import generate_intermediate_frames
        from app.services.metadata import generate_metadata_for_frame

        # Find the frame paths from FRAME_CATALOG
        f1 = next((f for f in FRAME_CATALOG if f["timestamp"] == request.frame1_id), None)
        f2 = next((f for f in FRAME_CATALOG if f["timestamp"] == request.frame2_id), None)
        
        if not f1 or not f2:
            logger.error("Frames not found in catalog")
            raise HTTPException(status_code=404, detail="One or both frames not found in catalog")

        idx1 = FRAME_CATALOG.index(f1)
        
        # We need absolute paths to give to OpenCV/Torch
        f1_path = os.path.join(BASE_DIR, f1["imageUrl"].lstrip('/'))
        f2_path = os.path.join(BASE_DIR, f2["imageUrl"].lstrip('/'))
        
        out_dir = os.path.join(DATA_DIR, "interpolated_frames")
        
        # Real interpolation logic
        logger.info(f"Running RIFE interpolation between {f1_path} and {f2_path}")
        generated_paths = generate_intermediate_frames(
            f1_path, f2_path, out_dir, request.steps, file_prefix=f"interp_{request.frame1_id}_{request.frame2_id}"
        )
        logger.info(f"Generated {len(generated_paths)} frames successfully.")
        
        new_frames = []
        for i, path in enumerate(generated_paths):
            ratio = (i + 1) / (request.steps + 1)
            # Use a synthetic intermediate timestamp identifier
            new_ts = f"interp_{request.frame1_id}_{request.frame2_id}_{i+1}"
            confidence = round(0.95 - (0.05 * ratio), 2)
            
            # Generate metadata JSON
            logger.info(f"Saving metadata for generated frame {new_ts}")
            generate_metadata_for_frame(path, f1_path, f2_path, new_ts, confidence)
            
            img_url = f"/data/interpolated_frames/{os.path.basename(path)}"
            new_entry = {
                "timestamp": new_ts,
                "imageUrl": img_url,
                "cloudMaskUrl": None,
                "vectorsUrl": None,
                "isOriginal": False,
                "confidence": confidence,
                "sourceFrames": [request.frame1_id, request.frame2_id],
            }
            new_frames.append(new_entry)
            
        # Insert them into the catalog so the frontend sees them in sequence
        FRAME_CATALOG[idx1+1:idx1+1] = new_frames
        
        logger.info(f"Interpolation pipeline completed for {request.frame1_id} -> {request.frame2_id}")
        return {"status": "success", "generated_frames": [f["imageUrl"] for f in new_frames]}
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Interpolation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


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
