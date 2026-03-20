from pydantic import BaseModel, Field
from typing import List, Optional

class FrameRetrievalRequest(BaseModel):
    bbox: List[float] = Field(default=[68.111378, 6.753515, 97.395561, 35.674545]) # Default bounding box for India
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
