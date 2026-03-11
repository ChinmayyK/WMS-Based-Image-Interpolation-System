from fastapi import APIRouter, HTTPException
from app.models import FrameRetrievalRequest, InterpolationRequest, MetadataResponse
import json
import os

router = APIRouter()

# Base path to data directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
    try:
        frames = [f["imageUrl"] for f in FRAME_CATALOG if f["isOriginal"]]
        return {"status": "success", "fetched_frames": frames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    """Runs the RIFE model to generate intermediate frames."""
    try:
        generated = [f["imageUrl"] for f in FRAME_CATALOG if not f["isOriginal"]]
        return {"status": "success", "generated_frames": generated}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metadata/{frame_id}", response_model=MetadataResponse)
async def get_metadata(frame_id: str):
    """Retrieves metadata and confidence score for a frame."""
    mock_meta_path = os.path.join(DATA_DIR, "metadata", "sample_metadata.json")

    if os.path.exists(mock_meta_path):
        with open(mock_meta_path, 'r') as f:
            data = json.load(f)
            return MetadataResponse(
                frame_id=frame_id,
                timestamp=data.get("time", "10:10"),
                confidence_score=data.get("confidence", 0.95),
                is_interpolated=data.get("generated", True)
            )

    return MetadataResponse(
        frame_id=frame_id,
        timestamp="2024-01-01T12:00:00Z",
        confidence_score=0.95,
        is_interpolated=True
    )
