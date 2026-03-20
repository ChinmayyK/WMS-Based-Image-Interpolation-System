import os
import requests
import uuid
import logging
from typing import List
from app.models import FrameRetrievalRequest

logger = logging.getLogger(__name__)


DEFAULT_WMS_URLS = {
    "EPSG:3857": "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
    "EPSG:4326": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
}
MAX_WMS_HISTORY = 10
LAST_WMS_REQUESTS = []


class WMSClientError(Exception):
    pass


def _record_wms_request(entry: dict) -> None:
    """Keep a short in-memory history for diagnostics."""
    LAST_WMS_REQUESTS.append(entry)
    if len(LAST_WMS_REQUESTS) > MAX_WMS_HISTORY:
        del LAST_WMS_REQUESTS[:-MAX_WMS_HISTORY]


def resolve_wms_url(crs: str) -> str:
    """Resolve the default NASA GIBS endpoint for the requested CRS."""
    normalized = (crs or "EPSG:4326").upper()
    override = os.getenv("WMS_URL")
    if override:
        return override
    return DEFAULT_WMS_URLS.get(normalized, DEFAULT_WMS_URLS["EPSG:4326"])


def get_wms_diagnostics() -> dict:
    """Expose recent WMS request history for verification."""
    return {
        "defaultEndpoints": DEFAULT_WMS_URLS,
        "overrideEndpoint": os.getenv("WMS_URL"),
        "lastRequests": list(LAST_WMS_REQUESTS),
    }


def fetch_wms_frames(request: FrameRetrievalRequest) -> List[dict]:
    """
    Fetches satellite imagery frames from a Web Map Service (WMS)
    for the given request parameters.
    """
    wms_url = resolve_wms_url(request.crs)
    # Data directory relative to backend root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data", "raw_frames")
    os.makedirs(data_dir, exist_ok=True)

    # Example format: minx, miny, maxx, maxy
    bbox_str = ",".join(map(str, request.bbox))

    retrieved_frames = []

    time_points = [request.start_time, request.end_time]

    for t in time_points:
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.3.0",
            "REQUEST": "GetMap",
            "LAYERS": request.layers,
            "STYLES": "",
            "CRS": request.crs,
            "BBOX": bbox_str,
            "WIDTH": str(request.width),
            "HEIGHT": str(request.height),
            "FORMAT": "image/png",
            "TIME": t,
            "TRANSPARENT": "TRUE"
        }

        try:
            logger.info(
                "WMS GetMap request | endpoint=%s | time=%s | layers=%s | crs=%s | bbox=%s | width=%s | height=%s",
                wms_url,
                t,
                request.layers,
                request.crs,
                bbox_str,
                params["WIDTH"],
                params["HEIGHT"],
            )
            response = requests.get(wms_url, params=params, timeout=60)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            logger.info(
                "WMS response received | status=%s | content_type=%s | url=%s",
                response.status_code,
                content_type,
                response.url,
            )
            if "image" not in content_type:
                _record_wms_request({
                    "time": t,
                    "endpoint": wms_url,
                    "requestedUrl": response.url,
                    "statusCode": response.status_code,
                    "contentType": content_type,
                    "bbox": list(request.bbox),
                    "crs": request.crs,
                    "layers": request.layers,
                    "width": request.width,
                    "height": request.height,
                    "savedPath": None,
                    "error": f"Unexpected content type from WMS: {content_type}",
                })
                raise WMSClientError(f"Unexpected content type from WMS: {content_type}")

            frame_id = f"frame_{uuid.uuid4().hex[:8]}"
            filename = f"{frame_id}_{t.replace(':', '').replace('-', '')}.png"
            filepath = os.path.join(data_dir, filename)

            with open(filepath, "wb") as f:
                f.write(response.content)

            request_record = {
                "time": t,
                "endpoint": wms_url,
                "requestedUrl": response.url,
                "statusCode": response.status_code,
                "contentType": content_type,
                "bbox": list(request.bbox),
                "crs": request.crs,
                "layers": request.layers,
                "width": request.width,
                "height": request.height,
                "savedPath": filepath,
                "savedBytes": len(response.content),
            }
            _record_wms_request(request_record)

            retrieved_frames.append({
                "id": frame_id,
                "timestamp": t,
                "path": filepath,
                "wmsUrl": wms_url,
                "requestedUrl": response.url,
                "statusCode": response.status_code,
            })

        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            response_url = getattr(getattr(e, "response", None), "url", None)
            _record_wms_request({
                "time": t,
                "endpoint": wms_url,
                "requestedUrl": response_url,
                "statusCode": status_code,
                "contentType": getattr(getattr(e, "response", None), "headers", {}).get("Content-Type"),
                "bbox": list(request.bbox),
                "crs": request.crs,
                "layers": request.layers,
                "width": request.width,
                "height": request.height,
                "savedPath": None,
                "error": str(e),
            })
            raise WMSClientError(f"Failed to fetch WMS data for time {t}: {e}")

    return retrieved_frames
