import os

import cv2
import numpy as np

import pytest
import requests

from app.models import FrameRetrievalRequest
from app.services.confidence import parse_timestamp
from app.services.wms_client import (
    WMSClientError,
    extract_available_timestamps,
    fetch_time_series,
)


GOES_CAPABILITIES_XML = """
<WMS_Capabilities version="1.3.0" xmlns="http://www.opengis.net/wms">
  <Capability>
    <Layer>
      <Layer>
        <Name>GOES-East_ABI_Band2_Red_Visible_1km</Name>
        <Title>GOES-East_ABI_Band2_Red_Visible_1km</Title>
        <Dimension name="time" units="ISO8601" default="2026-03-20T10:30:00Z">
          2026-03-20T10:00:00Z/2026-03-20T10:30:00Z/PT10M
        </Dimension>
      </Layer>
    </Layer>
  </Capability>
</WMS_Capabilities>
""".strip()


class FakeResponse:
    def __init__(
        self,
        *,
        text: str = "",
        content: bytes = b"",
        status_code: int = 200,
        content_type: str = "text/xml",
        url: str = "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
    ):
        self.text = text
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def _png_bytes(value: int) -> bytes:
    image = np.full((16, 16, 4), value, dtype=np.uint8)
    ok, encoded = cv2.imencode(".png", image)
    assert ok
    return encoded.tobytes()


def test_extract_available_timestamps_filters_native_cadence():
    timestamps = extract_available_timestamps(
        "2026-03-20T10:00:00Z/2026-03-20T10:30:00Z/PT10M",
        start_time=parse_timestamp("2026-03-20T10:10:00Z"),
        end_time=parse_timestamp("2026-03-20T10:30:00Z"),
    )

    assert [value.strftime("%Y-%m-%dT%H:%M:%SZ") for value in timestamps] == [
        "2026-03-20T10:10:00Z",
        "2026-03-20T10:20:00Z",
        "2026-03-20T10:30:00Z",
    ]


def test_fetch_time_series_downloads_all_filtered_frames(tmpdir, monkeypatch):
    import app.services.wms_client as wms_client

    wms_client.__file__ = os.path.join(tmpdir, "wms_client.py")
    wms_client.CAPABILITIES_CACHE.clear()
    wms_client.LAST_WMS_REQUESTS.clear()
    monkeypatch.setattr("app.services.wms_client._cache_db_path", lambda: os.path.join(tmpdir, "wms_cache.sqlite"))

    responses = [
        FakeResponse(text=GOES_CAPABILITIES_XML, content_type="text/xml"),
        FakeResponse(content=_png_bytes(10), content_type="image/png"),
        FakeResponse(content=_png_bytes(20), content_type="image/png"),
        FakeResponse(content=_png_bytes(30), content_type="image/png"),
        FakeResponse(content=_png_bytes(40), content_type="image/png"),
    ]

    def fake_get(_url, params=None, timeout=None):
        response = responses.pop(0)
        if params:
            response.url = f"https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?REQUEST={params.get('REQUEST')}"
        return response

    monkeypatch.setattr("app.services.wms_client.requests.get", fake_get)

    request = FrameRetrievalRequest(
        bbox=[-10575351.63, 1345708.41, -6679169.45, 4865942.28],
        start_time="2026-03-20T10:00:00Z",
        end_time="2026-03-20T10:30:00Z",
        layers="GOES-East_ABI_Band2_Red_Visible_1km",
        crs="EPSG:3857",
        width=512,
        height=512,
    )

    result = fetch_time_series(request)

    assert len(result["frames"]) == 4
    assert [frame["timestamp"] for frame in result["frames"]] == [
        "2026-03-20 10:00",
        "2026-03-20 10:10",
        "2026-03-20 10:20",
        "2026-03-20 10:30",
    ]
    assert result["session"]["downloadedFrameCount"] == 4
    assert result["session"]["source"] == "GOES-East ABI"
    assert result["session"]["validation"]["continuousFrames"] is True
    assert open(result["frames"][0]["path"], "rb").read() == _png_bytes(10)


def test_fetch_time_series_logs_failed_timestamp_and_continues(tmpdir, monkeypatch):
    import app.services.wms_client as wms_client

    wms_client.__file__ = os.path.join(tmpdir, "wms_client.py")
    wms_client.CAPABILITIES_CACHE.clear()
    wms_client.LAST_WMS_REQUESTS.clear()
    monkeypatch.setattr("app.services.wms_client._cache_db_path", lambda: os.path.join(tmpdir, "wms_cache.sqlite"))
    monkeypatch.setattr("app.services.wms_client.time.sleep", lambda *_args, **_kwargs: None)

    responses = [
        FakeResponse(text=GOES_CAPABILITIES_XML, content_type="text/xml"),
        FakeResponse(content=_png_bytes(10), content_type="image/png"),
        FakeResponse(status_code=503, text="temporary outage", content_type="text/plain"),
        FakeResponse(status_code=503, text="temporary outage", content_type="text/plain"),
        FakeResponse(status_code=503, text="temporary outage", content_type="text/plain"),
        FakeResponse(status_code=503, text="temporary outage", content_type="text/plain"),
        FakeResponse(content=_png_bytes(30), content_type="image/png"),
        FakeResponse(content=_png_bytes(40), content_type="image/png"),
    ]

    def fake_get(_url, params=None, timeout=None):
        response = responses.pop(0)
        if params:
            response.url = f"https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?REQUEST={params.get('REQUEST')}&TIME={params.get('TIME', '')}"
        return response

    monkeypatch.setattr("app.services.wms_client.requests.get", fake_get)

    request = FrameRetrievalRequest(
        start_time="2026-03-20T10:00:00Z",
        end_time="2026-03-20T10:30:00Z",
    )
    result = fetch_time_series(request)

    assert len(result["frames"]) == 3
    assert result["session"]["downloadedFrameCount"] == 3
    assert len(result["session"]["failedTimestamps"]) == 1
    assert result["session"]["failedTimestamps"][0]["timestamp"] == "2026-03-20 10:10"


def test_fetch_time_series_raises_for_missing_layer(tmpdir, monkeypatch):
    import app.services.wms_client as wms_client

    wms_client.CAPABILITIES_CACHE.clear()
    monkeypatch.setattr("app.services.wms_client._cache_db_path", lambda: os.path.join(tmpdir, "wms_cache.sqlite"))

    def fake_get(_url, params=None, timeout=None):
        return FakeResponse(text=GOES_CAPABILITIES_XML, content_type="text/xml")

    monkeypatch.setattr("app.services.wms_client.requests.get", fake_get)

    request = FrameRetrievalRequest(
        start_time="2026-03-20T10:00:00Z",
        end_time="2026-03-20T10:30:00Z",
        layers="GOES-East_ABI_GeoColor",
    )

    with pytest.raises(WMSClientError):
        fetch_time_series(request)


def test_fetch_time_series_uses_earthdata_auth_and_cache_hit(tmpdir, monkeypatch):
    import app.services.wms_client as wms_client

    wms_client.__file__ = os.path.join(tmpdir, "wms_client.py")
    wms_client.CAPABILITIES_CACHE.clear()
    wms_client.LAST_WMS_REQUESTS.clear()
    monkeypatch.setattr("app.services.wms_client._cache_db_path", lambda: os.path.join(tmpdir, "wms_cache.sqlite"))
    monkeypatch.setenv("EARTHDATA_TOKEN", "secret-token")

    seen_headers = []
    responses = [
        FakeResponse(text=GOES_CAPABILITIES_XML, content_type="text/xml"),
        FakeResponse(content=_png_bytes(10), content_type="image/png"),
    ]

    def fake_get(_url, params=None, timeout=None, headers=None):
        seen_headers.append(headers or {})
        response = responses.pop(0)
        if params:
            response.url = f"https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi?REQUEST={params.get('REQUEST')}"
        return response

    monkeypatch.setattr("app.services.wms_client.requests.get", fake_get)

    request = FrameRetrievalRequest(
        start_time="2026-03-20T10:00:00Z",
        end_time="2026-03-20T10:00:00Z",
    )

    first = fetch_time_series(request)
    second = fetch_time_series(request)

    assert seen_headers[0]["Authorization"] == "Bearer secret-token"
    assert first["frames"][0]["cacheHit"] is False
    assert second["frames"][0]["cacheHit"] is True
