import os
import requests
import uuid
from typing import List
from app.models import FrameRetrievalRequest

class WMSClientError(Exception):
    pass

def fetch_wms_frames(request: FrameRetrievalRequest) -> List[dict]:
    """
    Fetches satellite imagery frames from a Web Map Service (WMS)
    for the given request parameters.
    """
    # Use a default open WMS endpoint if not specified, e.g., NASA GIBS for test purposes (Blue Marble)
    wms_url = os.getenv("WMS_URL", "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi")
    # Data directory relative to backend root
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    data_dir = os.path.join(base_dir, "data", "frames")
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
            response = requests.get(wms_url, params=params)
            response.raise_for_status()
            
            if "image" not in response.headers.get("Content-Type", ""):
                raise WMSClientError(f"Unexpected content type from WMS: {response.headers.get('Content-Type')}")

            frame_id = f"frame_{uuid.uuid4().hex[:8]}"
            filename = f"{frame_id}_{t.replace(':', '').replace('-', '')}.png"
            filepath = os.path.join(data_dir, filename)
            
            with open(filepath, "wb") as f:
                f.write(response.content)
                
            retrieved_frames.append({
                "id": frame_id,
                "timestamp": t,
                "path": filepath
            })
            
        except requests.exceptions.RequestException as e:
            raise WMSClientError(f"Failed to fetch WMS data for time {t}: {e}")
            
    return retrieved_frames
