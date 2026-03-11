from pydantic import BaseModel
from typing import List, Optional

class FrameRetrievalRequest(BaseModel):
    bbox: List[float] # [minx, miny, maxx, maxy]
    start_time: str
    end_time: str
    layers: str
    crs: str = "EPSG:4326"
    width: int = 512
    height: int = 512

class InterpolationRequest(BaseModel):
    frame1_id: str
    frame2_id: str
    steps: int = 1

class MetadataResponse(BaseModel):
    frame_id: str
    timestamp: str
    confidence_score: Optional[float]
    is_interpolated: bool
