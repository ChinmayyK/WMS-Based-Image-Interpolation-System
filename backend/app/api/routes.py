from fastapi import APIRouter, HTTPException
from app.models import FrameRetrievalRequest, InterpolationRequest, MetadataResponse
from app.services.wms_client import fetch_wms_frames
from app.services.interpolation import run_interpolation

router = APIRouter()

@router.post("/frames/fetch")
async def fetch_frames(request: FrameRetrievalRequest):
    """Fetches frames from a WMS endpoint based on temporal and spatial bounds."""
    try:
        # Mocking WMS fetch
        frames = [
            "/data/raw_frames/frame_10_00.png",
            "/data/raw_frames/frame_10_30.png"
        ]
        return {"status": "success", "fetched_frames": frames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    """Runs the RIFE model to generate intermediate frames."""
    try:
        # Mocking RIFE interpolation
        generated_frames = [
            "/data/interpolated_frames/frame_10_10.png"
        ]
        return {"status": "success", "generated_frames": generated_frames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metadata/{frame_id}", response_model=MetadataResponse)
async def get_metadata(frame_id: str):
    """Retrieves metadata and confidence score for a frame."""
    import json
    import os
    
    # Check if we have sample JSON metadata
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    mock_meta_path = os.path.join(BASE_DIR, "data", "metadata", "sample_metadata.json")
    
    if os.path.exists(mock_meta_path):
        with open(mock_meta_path, 'r') as f:
            data = json.load(f)
            return MetadataResponse(
                frame_id=frame_id,
                timestamp=data.get("time", "10:10"),
                confidence_score=data.get("confidence", 0.95),
                is_interpolated=data.get("generated", True)
            )
            
    # Fallback Placeholder
    return MetadataResponse(
        frame_id=frame_id,
        timestamp="2024-01-01T12:00:00Z",
        confidence_score=0.95,
        is_interpolated=True
    )
