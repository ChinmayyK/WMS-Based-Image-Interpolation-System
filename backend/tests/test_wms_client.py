import os
import pytest
import responses
from app.models import FrameRetrievalRequest
from app.services.wms_client import fetch_wms_frames, WMSClientError

@responses.activate
def test_fetch_wms_frames_success(tmpdir):
    # Mock OS path
    import app.services.wms_client as wms_client
    wms_client.__file__ = os.path.join(tmpdir, "wms_client.py")
    
    req = FrameRetrievalRequest(
        bbox=[-180.0, -90.0, 180.0, 90.0],
        start_time="2023-01-01T00:00:00Z",
        end_time="2023-01-01T01:00:00Z",
        layers="MODIS_Terra_CorrectedReflectance_TrueColor",
        crs="EPSG:4326",
        width=256,
        height=256
    )

    # Mock responses for the requested times
    for t in [req.start_time, req.end_time]:
        responses.add(
            responses.GET,
            "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
            body=b"fake_image_data",
            status=200,
            content_type="image/png"
        )
        
    frames = fetch_wms_frames(req)
    
    assert len(frames) == 2
    assert frames[0]["timestamp"] == req.start_time
    assert frames[1]["timestamp"] == req.end_time
    assert "fake_image_data" in open(frames[0]["path"], "rb").read().decode('utf-8')

@responses.activate
def test_fetch_wms_frames_error():
    req = FrameRetrievalRequest(
        bbox=[-180.0, -90.0, 180.0, 90.0],
        start_time="2023-01-01",
        end_time="2023-01-02",
        layers="layer"
    )
    
    responses.add(
        responses.GET,
        "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
        status=500,
        body="Internal Server Error"
    )
    
    with pytest.raises(WMSClientError):
        fetch_wms_frames(req)
