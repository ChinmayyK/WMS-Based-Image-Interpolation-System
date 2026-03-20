from pydantic import BaseModel, Field
from typing import List, Optional

class FrameRetrievalRequest(BaseModel):
    bbox: List[float] = Field(
        default_factory=lambda: [-10575351.63, 1345708.41, -6679169.45, 4865942.28]
    )
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    layers: str = "GOES-East_ABI_Band2_Red_Visible_1km"
    provider: str = "auto"
    crs: str = "EPSG:3857"
    width: int = 1024
    height: int = 768

class InterpolationRequest(BaseModel):
    frame1_id: str
    frame2_id: str
    steps: int = 1


class ExportFrameRequest(BaseModel):
    timestamp: str
    imageUrl: str
    rawImageUrl: Optional[str] = None
    cleanImageUrl: Optional[str] = None
    isOriginal: bool
    confidence: float
    confidenceLabel: Optional[str] = None
    sourceFrames: Optional[List[str]] = None
    isGapPlaceholder: Optional[bool] = False


class VideoExportRequest(BaseModel):
    frames: List[ExportFrameRequest]
    fps: int = 15
    raw_mode: bool = False
    job_name: str = "sequence_export"


class EvaluationRequest(BaseModel):
    rerun: bool = True

class MetadataResponse(BaseModel):
    frame_id: str
    timestamp: str
    confidence_score: Optional[float]
    is_interpolated: bool
