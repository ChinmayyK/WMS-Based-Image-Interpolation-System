from fastapi import APIRouter, HTTPException
from app.models import FrameRetrievalRequest, InterpolationRequest, MetadataResponse
from app.services.wms_client import fetch_wms_frames
from app.services.interpolation import run_interpolation

router = APIRouter()

@router.post("/frames/fetch")
async def fetch_frames(request: FrameRetrievalRequest):
    \"\"\"Fetches frames from a WMS endpoint based on temporal and spatial bounds.\"\"\"
    try:
        frames = fetch_wms_frames(request)
        return {"status": "success", "fetched_frames": frames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/frames/interpolate")
async def interpolate_frames(request: InterpolationRequest):
    \"\"\"Runs the RIFE model to generate intermediate frames.\"\"\"
    try:
        generated_frames = run_interpolation(request)
        return {"status": "success", "generated_frames": generated_frames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/metadata/{frame_id}", response_model=MetadataResponse)
async def get_metadata(frame_id: str):
    \"\"\"Retrieves metadata and confidence score for a frame.\"\"\"
    # Placeholder returning mock data
    return MetadataResponse(
        frame_id=frame_id,
        timestamp="2024-01-01T12:00:00Z",
        confidence_score=0.95,
        is_interpolated=True
    )
