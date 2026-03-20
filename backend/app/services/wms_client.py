import hashlib
import json
import logging
import math
import os
import re
import shutil
import sqlite3
import threading
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import cv2
import requests

from app.models import FrameRetrievalRequest
from app.services.confidence import format_timestamp, parse_timestamp


logger = logging.getLogger(__name__)


DEFAULT_WMS_URLS = {
    "EPSG:3857": "https://gibs.earthdata.nasa.gov/wms/epsg3857/best/wms.cgi",
    "EPSG:4326": "https://gibs.earthdata.nasa.gov/wms/epsg4326/best/wms.cgi",
}
DEFAULT_MOSDAC_URLS = {
    "EPSG:3857": os.getenv("MOSDAC_WMS_URL", "https://mosdac.gov.in/live/wms"),
    "EPSG:4326": os.getenv("MOSDAC_WMS_URL", "https://mosdac.gov.in/live/wms"),
}
DEFAULT_GOES_LAYER = os.getenv("WMS_LAYER", "GOES-East_ABI_Band2_Red_Visible_1km")
DEFAULT_FETCH_WINDOW_MINUTES = int(os.getenv("GOES_DEFAULT_FETCH_WINDOW_MINUTES", "90"))
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("WMS_TIMEOUT_SECONDS", "60"))
DEFAULT_MAX_RETRIES = int(os.getenv("WMS_MAX_RETRIES", "4"))
DEFAULT_BACKOFF_SECONDS = float(os.getenv("WMS_BACKOFF_SECONDS", "1.0"))
WMS_CACHE_TTL_SECONDS = int(os.getenv("WMS_CACHE_TTL_SECONDS", "86400"))
CAPABILITIES_CACHE_TTL_SECONDS = int(os.getenv("WMS_CAPABILITIES_CACHE_TTL_SECONDS", str(WMS_CACHE_TTL_SECONDS)))
MAX_WMS_HISTORY = 50
DEFAULT_MAX_CONCURRENT_REQUESTS = int(os.getenv("WMS_MAX_CONCURRENT_REQUESTS", "3"))
MOSDAC_MAX_CONCURRENT_REQUESTS = int(os.getenv("MOSDAC_MAX_CONCURRENT_REQUESTS", "2"))
MOSDAC_ARCHIVE_DIR = os.getenv("MOSDAC_ARCHIVE_DIR", "")
STATIC_INSAT_ARCHIVE_DIR = os.getenv("STATIC_INSAT_ARCHIVE_DIR", "")

LAST_WMS_REQUESTS: List[dict] = []
CAPABILITIES_CACHE: Dict[str, dict] = {}
LAST_CAPABILITIES_FETCH: Optional[dict] = None
SOURCE_LIMITERS: Dict[str, threading.BoundedSemaphore] = {}
SOURCE_LIMITERS_LOCK = threading.Lock()

ISO8601_DURATION_RE = re.compile(
    r"^P"
    r"(?:(?P<days>\d+)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d+)H)?"
    r"(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?"
    r")?$"
)


class WMSClientError(Exception):
    pass


class MissingTimestampError(WMSClientError):
    pass


def _backend_data_dir() -> str:
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_dir, "data")


def _cache_dir() -> str:
    path = os.path.join(_backend_data_dir(), "cache")
    os.makedirs(path, exist_ok=True)
    return path


def _cache_db_path() -> str:
    return os.path.join(_cache_dir(), "wms_cache.sqlite")


def _raw_frames_dir() -> str:
    path = os.path.join(_backend_data_dir(), "raw_frames")
    os.makedirs(path, exist_ok=True)
    return path


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _format_wms_time(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sanitize_timestamp_for_filename(value: str) -> str:
    cleaned = value.strip()
    for token in (":", "-", "."):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.replace("+0000", "Z").replace("+00:00", "Z")
    return cleaned


def _record_wms_request(entry: dict) -> None:
    LAST_WMS_REQUESTS.append(entry)
    if len(LAST_WMS_REQUESTS) > MAX_WMS_HISTORY:
        del LAST_WMS_REQUESTS[:-MAX_WMS_HISTORY]


def _initialize_cache_db() -> None:
    with sqlite3.connect(_cache_db_path()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS capabilities_cache (
                cache_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                requested_url TEXT,
                xml_text TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS frame_cache (
                cache_key TEXT PRIMARY KEY,
                provider TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                layer TEXT NOT NULL,
                time_value TEXT NOT NULL,
                bbox TEXT NOT NULL,
                crs TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                md5 TEXT NOT NULL,
                metadata_json TEXT NOT NULL,
                fetched_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
            """
        )


def _cache_connection() -> sqlite3.Connection:
    _initialize_cache_db()
    return sqlite3.connect(_cache_db_path(), timeout=30)


def _cache_expiry(ttl_seconds: int) -> float:
    return time.time() + ttl_seconds


def _safe_delete(path: Optional[str]) -> None:
    if path and os.path.exists(path):
        try:
            os.unlink(path)
        except OSError:
            logger.warning("Failed to delete path %s", path)


def _compute_file_md5(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_image_file(path: str, expected_md5: Optional[str] = None) -> bool:
    if not os.path.exists(path):
        return False
    image = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if image is None:
        return False
    height, width = image.shape[:2]
    if width < 10 or height < 10:
        return False
    if expected_md5 and _compute_file_md5(path) != expected_md5:
        return False
    return True


def _load_cached_capabilities(endpoint: str, provider: str) -> Optional[Dict[str, dict]]:
    cache_key = f"{provider}:{endpoint}"
    cached = CAPABILITIES_CACHE.get(cache_key)
    if cached and (time.time() - cached["fetchedAt"]) < CAPABILITIES_CACHE_TTL_SECONDS:
        return cached["layers"]

    with _cache_connection() as conn:
        row = conn.execute(
            "SELECT xml_text, expires_at FROM capabilities_cache WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    xml_text, expires_at = row
    if expires_at < time.time():
        return None
    layers = _parse_capabilities(xml_text)
    CAPABILITIES_CACHE[cache_key] = {"fetchedAt": time.time(), "layers": layers}
    return layers


def _store_capabilities_cache(endpoint: str, provider: str, requested_url: str, xml_text: str) -> None:
    cache_key = f"{provider}:{endpoint}"
    fetched_at = time.time()
    expires_at = _cache_expiry(CAPABILITIES_CACHE_TTL_SECONDS)
    with _cache_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO capabilities_cache
            (cache_key, provider, endpoint, requested_url, xml_text, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (cache_key, provider, endpoint, requested_url, xml_text, fetched_at, expires_at),
        )
        conn.commit()
    CAPABILITIES_CACHE[cache_key] = {"fetchedAt": fetched_at, "layers": _parse_capabilities(xml_text)}


def _frame_cache_key(provider: str, endpoint: str, request: FrameRetrievalRequest, time_value: str) -> str:
    payload = "|".join(
        [
            provider,
            endpoint,
            request.layers,
            time_value,
            ",".join(map(str, request.bbox)),
            request.crs,
            str(request.width),
            str(request.height),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_cached_frame(cache_key: str) -> Optional[dict]:
    with _cache_connection() as conn:
        row = conn.execute(
            """
            SELECT file_path, md5, metadata_json, expires_at
            FROM frame_cache
            WHERE cache_key = ?
            """,
            (cache_key,),
        ).fetchone()
    if not row:
        return None
    file_path, md5_hash, metadata_json, expires_at = row
    if expires_at < time.time():
        _safe_delete(file_path)
        with _cache_connection() as conn:
            conn.execute("DELETE FROM frame_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
        return None
    if not _validate_image_file(file_path, expected_md5=md5_hash):
        _safe_delete(file_path)
        with _cache_connection() as conn:
            conn.execute("DELETE FROM frame_cache WHERE cache_key = ?", (cache_key,))
            conn.commit()
        return None
    payload = json.loads(metadata_json)
    payload["cacheHit"] = True
    return payload


def _store_frame_cache(cache_key: str, provider: str, endpoint: str, request: FrameRetrievalRequest, metadata: dict) -> None:
    fetched_at = time.time()
    expires_at = _cache_expiry(WMS_CACHE_TTL_SECONDS)
    with _cache_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO frame_cache
            (cache_key, provider, endpoint, layer, time_value, bbox, crs, width, height, file_path, md5, metadata_json, fetched_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cache_key,
                provider,
                endpoint,
                request.layers,
                metadata["wmsTime"],
                json.dumps(list(request.bbox)),
                request.crs,
                request.width,
                request.height,
                metadata["path"],
                metadata["md5"],
                json.dumps(metadata),
                fetched_at,
                expires_at,
            ),
        )
        conn.commit()


def _provider_defaults(provider: str) -> dict:
    if provider == "mosdac":
        return {
            "urls": DEFAULT_MOSDAC_URLS,
            "auth_env": "MOSDAC_TOKEN",
            "api_key_env": "MOSDAC_API_KEY",
            "max_concurrent": MOSDAC_MAX_CONCURRENT_REQUESTS,
            "archive_dirs": [path for path in (MOSDAC_ARCHIVE_DIR, STATIC_INSAT_ARCHIVE_DIR) if path],
            "diagnostic_name": "MOSDAC",
        }
    return {
        "urls": DEFAULT_WMS_URLS,
        "auth_env": "EARTHDATA_TOKEN",
        "api_key_env": "",
        "max_concurrent": DEFAULT_MAX_CONCURRENT_REQUESTS,
        "archive_dirs": [],
        "diagnostic_name": "NASA GIBS",
    }


def resolve_provider(layer_name: str, provider: str = "auto") -> str:
    normalized = (provider or "auto").strip().lower()
    if normalized in {"gibs", "mosdac"}:
        return normalized
    layer = (layer_name or "").lower()
    if layer.startswith("insat") or layer.startswith("mosdac"):
        return "mosdac"
    return "gibs"


def resolve_wms_url(crs: str, provider: str = "gibs") -> str:
    normalized = (crs or "EPSG:3857").upper()
    if provider == "gibs":
        override = os.getenv("WMS_URL")
        if override:
            return override
    elif provider == "mosdac":
        override = os.getenv("MOSDAC_WMS_URL")
        if override:
            return override
    return _provider_defaults(provider)["urls"].get(normalized, _provider_defaults(provider)["urls"]["EPSG:3857"])


def resolve_source_label(layer_name: str, provider: Optional[str] = None) -> str:
    provider = resolve_provider(layer_name, provider or "auto")
    if provider == "mosdac":
        return "MOSDAC INSAT"
    if layer_name.startswith("GOES-East_"):
        return "GOES-East ABI"
    if layer_name.startswith("GOES-West_"):
        return "GOES-West ABI"
    return "GOES ABI"


def _provider_headers(provider: str) -> dict:
    defaults = _provider_defaults(provider)
    headers = {}
    token = os.getenv(defaults["auth_env"])
    if token:
        headers["Authorization"] = f"Bearer {token}"
    api_key_env = defaults["api_key_env"]
    if api_key_env:
        api_key = os.getenv(api_key_env)
        if api_key:
            headers["X-API-Key"] = api_key
    return headers


def _source_limiter(provider: str) -> threading.BoundedSemaphore:
    with SOURCE_LIMITERS_LOCK:
        limiter = SOURCE_LIMITERS.get(provider)
        if limiter is None:
            limiter = threading.BoundedSemaphore(_provider_defaults(provider)["max_concurrent"])
            SOURCE_LIMITERS[provider] = limiter
        return limiter


def get_wms_diagnostics() -> dict:
    return {
        "defaultEndpoints": DEFAULT_WMS_URLS,
        "mosdacEndpoints": DEFAULT_MOSDAC_URLS,
        "overrideEndpoint": os.getenv("WMS_URL"),
        "defaultLayer": DEFAULT_GOES_LAYER,
        "lastCapabilitiesFetch": LAST_CAPABILITIES_FETCH,
        "lastRequests": list(LAST_WMS_REQUESTS),
        "cache": {
            "databasePath": _cache_db_path(),
            "ttlSeconds": WMS_CACHE_TTL_SECONDS,
        },
        "auth": {
            "earthdataConfigured": bool(os.getenv("EARTHDATA_TOKEN")),
            "mosdacConfigured": bool(os.getenv("MOSDAC_TOKEN") or os.getenv("MOSDAC_API_KEY")),
        },
        "rateLimit": {
            "gibsMaxConcurrent": _provider_defaults("gibs")["max_concurrent"],
            "mosdacMaxConcurrent": _provider_defaults("mosdac")["max_concurrent"],
        },
    }


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _parse_capabilities(xml_text: str) -> Dict[str, dict]:
    root = ET.fromstring(xml_text)
    layers: Dict[str, dict] = {}

    for element in root.iter():
        if _local_name(element.tag) != "Layer":
            continue

        name = None
        title = None
        time_dimension = None
        default_time = None

        for child in element:
            tag = _local_name(child.tag)
            if tag == "Name":
                name = (child.text or "").strip()
            elif tag == "Title":
                title = (child.text or "").strip()
            elif tag == "Dimension" and child.attrib.get("name") == "time":
                time_dimension = (child.text or "").strip()
                default_time = child.attrib.get("default")

        if not name:
            continue

        layers[name] = {
            "name": name,
            "title": title or name,
            "timeDimension": time_dimension,
            "defaultTime": default_time,
        }

    return layers


def _perform_request(provider: str, endpoint: str, *, params: dict) -> requests.Response:
    with _source_limiter(provider):
        headers = _provider_headers(provider)
        kwargs = {
            "params": params,
            "timeout": DEFAULT_TIMEOUT_SECONDS,
        }
        if headers:
            kwargs["headers"] = headers
        return requests.get(endpoint, **kwargs)


def _fetch_capabilities(endpoint: str, provider: str, *, force_refresh: bool = False) -> Dict[str, dict]:
    global LAST_CAPABILITIES_FETCH

    if not force_refresh:
        cached_layers = _load_cached_capabilities(endpoint, provider)
        if cached_layers is not None:
            return cached_layers

    params = {
        "SERVICE": "WMS",
        "REQUEST": "GetCapabilities",
        "VERSION": "1.3.0",
    }
    last_error: Optional[Exception] = None
    for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
        try:
            logger.info("WMS GetCapabilities request | endpoint=%s | provider=%s", endpoint, provider)
            response = _perform_request(provider, endpoint, params=params)
            response.raise_for_status()
            layers = _parse_capabilities(response.text)
            _store_capabilities_cache(endpoint, provider, response.url, response.text)
            LAST_CAPABILITIES_FETCH = {
                "endpoint": endpoint,
                "provider": provider,
                "requestedUrl": response.url,
                "fetchedAt": _utc_now(),
                "layerCount": len(layers),
            }
            return layers
        except (requests.RequestException, ET.ParseError) as exc:
            last_error = exc
            if attempt == DEFAULT_MAX_RETRIES:
                break
            backoff_seconds = DEFAULT_BACKOFF_SECONDS * (2 ** (attempt - 1))
            time.sleep(backoff_seconds)
    raise WMSClientError(f"Failed to fetch WMS GetCapabilities from {endpoint}: {last_error}")


def get_layer_capabilities(layer_name: str, crs: str = "EPSG:3857", provider: str = "gibs") -> dict:
    endpoint = resolve_wms_url(crs, provider)
    layers = _fetch_capabilities(endpoint, provider, force_refresh=(provider == "mosdac"))
    layer = layers.get(layer_name)
    if layer is None:
        available_layers = sorted(layers.keys())
        raise WMSClientError(
            f"Layer '{layer_name}' was not found in {provider.upper()} capabilities. "
            f"Available layers: {', '.join(available_layers[:25])}"
        )
    if not layer.get("timeDimension"):
        raise WMSClientError(f"Layer '{layer_name}' does not expose a WMS time dimension.")
    return layer


def _parse_iso_duration(value: str) -> timedelta:
    match = ISO8601_DURATION_RE.match(value.strip())
    if not match:
        raise WMSClientError(f"Unsupported ISO-8601 duration in WMS capabilities: {value}")

    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    delta = timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    if delta.total_seconds() <= 0:
        raise WMSClientError(f"Invalid non-positive ISO-8601 duration in WMS capabilities: {value}")
    return delta


def _coerce_utc(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _segment_latest_time(segment: str) -> Optional[datetime]:
    parts = [part.strip() for part in segment.split("/") if part.strip()]
    if not parts:
        return None
    if len(parts) == 1:
        return _coerce_utc(parse_timestamp(parts[0]))
    return _coerce_utc(parse_timestamp(parts[1]))


def get_latest_available_timestamp(time_dimension: str) -> Optional[datetime]:
    latest = None
    for segment in (item.strip() for item in time_dimension.split(",") if item.strip()):
        candidate = _segment_latest_time(segment)
        if candidate is not None and (latest is None or candidate > latest):
            latest = candidate
    return latest


def extract_available_timestamps(
    time_dimension: str,
    start_time: datetime,
    end_time: datetime,
) -> List[datetime]:
    start_time = _coerce_utc(start_time)
    end_time = _coerce_utc(end_time)
    if start_time is None or end_time is None:
        raise WMSClientError("Start and end times are required to extract available timestamps.")
    if end_time < start_time:
        raise WMSClientError("End time must be greater than or equal to start time.")

    results: List[datetime] = []
    seen = set()

    for segment in (item.strip() for item in time_dimension.split(",") if item.strip()):
        parts = [part.strip() for part in segment.split("/") if part.strip()]
        if len(parts) == 1:
            ts = _coerce_utc(parse_timestamp(parts[0]))
            if ts is None or ts < start_time or ts > end_time:
                continue
            key = _format_wms_time(ts)
            if key not in seen:
                seen.add(key)
                results.append(ts)
            continue

        if len(parts) != 3:
            logger.warning("Skipping unsupported WMS time segment: %s", segment)
            continue

        segment_start = _coerce_utc(parse_timestamp(parts[0]))
        segment_end = _coerce_utc(parse_timestamp(parts[1]))
        if segment_start is None or segment_end is None:
            logger.warning("Skipping unparsable WMS time segment: %s", segment)
            continue

        step = _parse_iso_duration(parts[2])
        if segment_end < start_time or segment_start > end_time:
            continue

        effective_start = max(segment_start, start_time)
        if effective_start <= segment_start:
            current = segment_start
        else:
            delta_seconds = (effective_start - segment_start).total_seconds()
            step_seconds = step.total_seconds()
            steps = math.ceil(delta_seconds / step_seconds)
            current = segment_start + (step * steps)

        while current <= segment_end and current <= end_time:
            key = _format_wms_time(current)
            if key not in seen:
                seen.add(key)
                results.append(current)
            current += step

    results.sort()
    return results


def _resolve_requested_window(request: FrameRetrievalRequest, time_dimension: str) -> tuple[datetime, datetime]:
    latest_available = get_latest_available_timestamp(time_dimension)
    if latest_available is None:
        raise WMSClientError("Could not resolve the latest available timestamp from WMS capabilities.")

    requested_end = _coerce_utc(parse_timestamp(request.end_time)) if request.end_time else latest_available
    requested_start = (
        _coerce_utc(parse_timestamp(request.start_time))
        if request.start_time
        else requested_end - timedelta(minutes=DEFAULT_FETCH_WINDOW_MINUTES)
    )

    if requested_start is None or requested_end is None:
        raise WMSClientError("Could not resolve the requested time window.")
    if requested_end < requested_start:
        raise WMSClientError("End time must be greater than or equal to start time.")

    return requested_start, requested_end


def _compute_cadence_summary(wms_times: List[str]) -> dict:
    parsed = [_coerce_utc(parse_timestamp(value)) for value in wms_times]
    parsed = [value for value in parsed if value is not None]
    if len(parsed) < 2:
        return {"minGapMinutes": None, "medianGapMinutes": None, "maxGapMinutes": None}
    gap_minutes = sorted((right - left).total_seconds() / 60.0 for left, right in zip(parsed, parsed[1:]))
    return {
        "minGapMinutes": round(gap_minutes[0], 2),
        "medianGapMinutes": round(gap_minutes[len(gap_minutes) // 2], 2),
        "maxGapMinutes": round(gap_minutes[-1], 2),
    }


def _build_getmap_params(request: FrameRetrievalRequest, time_value: str) -> dict:
    return {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": request.layers,
        "STYLES": "",
        "CRS": request.crs,
        "BBOX": ",".join(map(str, request.bbox)),
        "WIDTH": str(request.width),
        "HEIGHT": str(request.height),
        "FORMAT": "image/png",
        "TIME": time_value,
        "TRANSPARENT": "TRUE",
    }


def _build_frame_metadata(
    *,
    provider: str,
    request: FrameRetrievalRequest,
    source_label: str,
    endpoint: str,
    time_value: str,
    path: str,
    requested_url: str,
    status_code: int,
    md5_hash: str,
    cache_key: str,
) -> dict:
    observed_timestamp = _coerce_utc(parse_timestamp(time_value))
    return {
        "timestamp": format_timestamp(observed_timestamp) if observed_timestamp else time_value,
        "wmsTime": time_value,
        "path": path,
        "filename": os.path.basename(path),
        "type": "OBSERVED",
        "source": source_label,
        "layer": request.layers,
        "bbox": list(request.bbox),
        "crs": request.crs,
        "width": request.width,
        "height": request.height,
        "wmsUrl": endpoint,
        "requestedUrl": requested_url,
        "statusCode": status_code,
        "provider": provider,
        "md5": md5_hash,
        "cacheKey": cache_key,
        "cacheHit": False,
    }


def _download_frame(
    provider: str,
    endpoint: str,
    request: FrameRetrievalRequest,
    time_value: str,
    source_label: str,
) -> dict:
    params = _build_getmap_params(request, time_value)
    cache_key = _frame_cache_key(provider, endpoint, request, time_value)
    cached = _load_cached_frame(cache_key)
    if cached:
        _record_wms_request(
            {
                "requestType": "GetMap",
                "provider": provider,
                "attempt": 0,
                "time": time_value,
                "endpoint": endpoint,
                "requestedUrl": cached.get("requestedUrl"),
                "statusCode": cached.get("statusCode"),
                "contentType": "image/png",
                "bbox": list(request.bbox),
                "crs": request.crs,
                "layers": request.layers,
                "width": request.width,
                "height": request.height,
                "savedPath": cached.get("path"),
                "savedBytes": os.path.getsize(cached["path"]) if os.path.exists(cached["path"]) else None,
                "cacheHit": True,
            }
        )
        return cached

    filename = f"{_sanitize_timestamp_for_filename(time_value)}.png"
    output_path = os.path.join(_raw_frames_dir(), filename)
    last_error: Optional[Exception] = None

    for attempt in range(1, DEFAULT_MAX_RETRIES + 1):
        try:
            logger.info(
                "WMS GetMap request | endpoint=%s | provider=%s | time=%s | layer=%s | attempt=%s/%s",
                endpoint,
                provider,
                time_value,
                request.layers,
                attempt,
                DEFAULT_MAX_RETRIES,
            )
            response = _perform_request(provider, endpoint, params=params)
            response.raise_for_status()
            content_type = response.headers.get("Content-Type", "")
            if not response.content or response.status_code == 204:
                raise MissingTimestampError(f"MISSING timestamp {time_value}: empty response")
            if "image" not in content_type.lower():
                raise WMSClientError(f"Unexpected content type from WMS: {content_type}")
            with open(output_path, "wb") as handle:
                handle.write(response.content)
            if not _validate_image_file(output_path):
                raise WMSClientError(f"Corrupt frame: cv2 could not decode {output_path}")
            content_md5 = hashlib.md5(response.content).hexdigest()
            metadata = _build_frame_metadata(
                provider=provider,
                request=request,
                source_label=source_label,
                endpoint=endpoint,
                time_value=time_value,
                path=output_path,
                requested_url=response.url,
                status_code=response.status_code,
                md5_hash=content_md5,
                cache_key=cache_key,
            )
            _store_frame_cache(cache_key, provider, endpoint, request, metadata)
            _record_wms_request(
                {
                    "requestType": "GetMap",
                    "provider": provider,
                    "attempt": attempt,
                    "time": time_value,
                    "endpoint": endpoint,
                    "requestedUrl": response.url,
                    "statusCode": response.status_code,
                    "contentType": content_type,
                    "bbox": list(request.bbox),
                    "crs": request.crs,
                    "layers": request.layers,
                    "width": request.width,
                    "height": request.height,
                    "savedPath": output_path,
                    "savedBytes": len(response.content),
                    "md5": content_md5,
                    "cacheHit": False,
                }
            )
            return metadata
        except MissingTimestampError as exc:
            _record_wms_request(
                {
                    "requestType": "GetMap",
                    "provider": provider,
                    "attempt": attempt,
                    "time": time_value,
                    "endpoint": endpoint,
                    "requestedUrl": None,
                    "statusCode": 204,
                    "contentType": None,
                    "bbox": list(request.bbox),
                    "crs": request.crs,
                    "layers": request.layers,
                    "width": request.width,
                    "height": request.height,
                    "savedPath": None,
                    "error": str(exc),
                    "classification": "MISSING",
                }
            )
            raise
        except (requests.RequestException, WMSClientError) as exc:
            last_error = exc
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            response_url = getattr(getattr(exc, "response", None), "url", None)
            _record_wms_request(
                {
                    "requestType": "GetMap",
                    "provider": provider,
                    "attempt": attempt,
                    "time": time_value,
                    "endpoint": endpoint,
                    "requestedUrl": response_url,
                    "statusCode": status_code,
                    "contentType": getattr(getattr(exc, "response", None), "headers", {}).get("Content-Type"),
                    "bbox": list(request.bbox),
                    "crs": request.crs,
                    "layers": request.layers,
                    "width": request.width,
                    "height": request.height,
                    "savedPath": None,
                    "error": str(exc),
                    "classification": "RETRIABLE" if status_code == 429 else "NON_RETRIABLE",
                }
            )
            if attempt == DEFAULT_MAX_RETRIES:
                break
            backoff_multiplier = 3 if status_code == 429 else 1
            backoff_seconds = DEFAULT_BACKOFF_SECONDS * backoff_multiplier * (2 ** (attempt - 1))
            time.sleep(backoff_seconds)
    raise WMSClientError(f"Failed to fetch WMS data for time {time_value}: {last_error}")


def _archive_candidates(layer: str) -> List[str]:
    candidates: List[str] = []
    for root in _provider_defaults("mosdac")["archive_dirs"]:
        if not root:
            continue
        layer_dir = os.path.join(root, layer)
        if os.path.isdir(layer_dir):
            candidates.append(layer_dir)
        if os.path.isdir(root):
            candidates.append(root)
    return candidates


def _timestamp_from_filename(filename: str) -> Optional[str]:
    stem = os.path.splitext(filename)[0]
    for candidate in (stem, stem.split("_")[0]):
        parsed = parse_timestamp(candidate)
        if parsed:
            return _format_wms_time(_coerce_utc(parsed))
    return None


def _fetch_from_archive(request: FrameRetrievalRequest, source_label: str, provider: str) -> Optional[dict]:
    candidates = _archive_candidates(request.layers)
    if not candidates:
        return None
    requested_start = _coerce_utc(parse_timestamp(request.start_time)) if request.start_time else None
    requested_end = _coerce_utc(parse_timestamp(request.end_time)) if request.end_time else None
    if requested_start is None or requested_end is None:
        return None

    retrieved_frames = []
    for directory in candidates:
        for filename in sorted(os.listdir(directory)):
            if not filename.lower().endswith(".png"):
                continue
            wms_time = _timestamp_from_filename(filename)
            if not wms_time:
                continue
            ts = _coerce_utc(parse_timestamp(wms_time))
            if ts is None or ts < requested_start or ts > requested_end:
                continue
            source_path = os.path.join(directory, filename)
            cache_key = _frame_cache_key(provider, directory, request, wms_time)
            target_filename = f"{_sanitize_timestamp_for_filename(wms_time)}.png"
            target_path = os.path.join(_raw_frames_dir(), target_filename)
            if os.path.abspath(source_path) != os.path.abspath(target_path):
                shutil.copy2(source_path, target_path)
            md5_hash = _compute_file_md5(target_path)
            retrieved_frames.append(
                _build_frame_metadata(
                    provider=provider,
                    request=request,
                    source_label=f"{source_label} Archive",
                    endpoint=directory,
                    time_value=wms_time,
                    path=target_path,
                    requested_url=source_path,
                    status_code=200,
                    md5_hash=md5_hash,
                    cache_key=cache_key,
                )
            )
        if retrieved_frames:
            break
    if not retrieved_frames:
        return None
    wms_times = [frame["wmsTime"] for frame in retrieved_frames]
    cadence_summary = _compute_cadence_summary(wms_times)
    return {
        "frames": retrieved_frames,
        "session": {
            "session_id": f"{request.layers}_{_sanitize_timestamp_for_filename(retrieved_frames[0]['wmsTime'])}_{_sanitize_timestamp_for_filename(retrieved_frames[-1]['wmsTime'])}",
            "createdAt": _utc_now(),
            "source": f"{source_label} Archive",
            "layer": request.layers,
            "title": request.layers,
            "bbox": list(request.bbox),
            "extent3857": list(request.bbox),
            "crs": request.crs,
            "width": request.width,
            "height": request.height,
            "wmsUrl": None,
            "requestedStartTime": _format_wms_time(requested_start),
            "requestedEndTime": _format_wms_time(requested_end),
            "availableStartTime": retrieved_frames[0]["wmsTime"],
            "availableEndTime": retrieved_frames[-1]["wmsTime"],
            "availableFrameCount": len(retrieved_frames),
            "downloadedFrameCount": len(retrieved_frames),
            "failedTimestamps": [],
            "cadenceMinutes": cadence_summary,
            "validation": {
                "continuousFrames": (cadence_summary["maxGapMinutes"] or 0) <= 15 if len(wms_times) > 1 else True,
                "minGapMinutes": cadence_summary["minGapMinutes"],
                "medianGapMinutes": cadence_summary["medianGapMinutes"],
                "maxGapMinutes": cadence_summary["maxGapMinutes"],
                "observedFrameCount": len(retrieved_frames),
                "failedFrameCount": 0,
            },
            "frames": [
                {
                    "timestamp": frame["timestamp"],
                    "wmsTime": frame["wmsTime"],
                    "source": frame["source"],
                    "layer": frame["layer"],
                    "bbox": frame["bbox"],
                    "crs": frame["crs"],
                    "width": frame["width"],
                    "height": frame["height"],
                    "type": frame["type"],
                    "filename": frame["filename"],
                    "path": frame["path"],
                    "url": f"/data/raw_frames/{frame['filename']}",
                }
                for frame in retrieved_frames
            ],
        },
    }


def fetch_time_series(request: FrameRetrievalRequest) -> dict:
    provider = resolve_provider(request.layers, request.provider)
    endpoint = resolve_wms_url(request.crs, provider)
    source_label = resolve_source_label(request.layers, provider)

    try:
        layer_capabilities = get_layer_capabilities(request.layers, request.crs, provider)
    except WMSClientError:
        if provider == "mosdac":
            archive_result = _fetch_from_archive(request, source_label, provider)
            if archive_result is not None:
                return archive_result
        raise

    requested_start, requested_end = _resolve_requested_window(request, layer_capabilities["timeDimension"])
    available_timestamps = extract_available_timestamps(layer_capabilities["timeDimension"], requested_start, requested_end)
    if not available_timestamps:
        latest_available = get_latest_available_timestamp(layer_capabilities["timeDimension"])
        latest_text = _format_wms_time(latest_available) if latest_available else "unknown"
        raise WMSClientError(
            f"No timestamps were available for layer '{request.layers}' between "
            f"{_format_wms_time(requested_start)} and {_format_wms_time(requested_end)}. "
            f"Latest available timestamp from capabilities is {latest_text}."
        )

    retrieved_frames = []
    failures = []
    for timestamp in available_timestamps:
        wms_time = _format_wms_time(timestamp)
        try:
            frame = _download_frame(provider, endpoint, request, wms_time, source_label)
            retrieved_frames.append(frame)
        except MissingTimestampError as exc:
            logger.warning("Missing timestamp %s: %s", wms_time, exc)
            failures.append(
                {
                    "timestamp": format_timestamp(timestamp),
                    "wmsTime": wms_time,
                    "error": str(exc),
                    "status": "MISSING",
                }
            )
        except WMSClientError as exc:
            logger.error("Failed timestamp %s: %s", wms_time, exc)
            failures.append(
                {
                    "timestamp": format_timestamp(timestamp),
                    "wmsTime": wms_time,
                    "error": str(exc),
                    "status": "FAILED",
                }
            )

    if not retrieved_frames:
        if provider == "mosdac":
            archive_result = _fetch_from_archive(request, source_label, provider)
            if archive_result is not None:
                archive_result["session"]["failedTimestamps"] = failures
                return archive_result
        raise WMSClientError(
            f"All {len(available_timestamps)} WMS frame downloads failed for layer '{request.layers}'."
        )

    wms_times = [frame["wmsTime"] for frame in retrieved_frames]
    cadence_summary = _compute_cadence_summary(wms_times)
    validation = {
        "continuousFrames": (cadence_summary["maxGapMinutes"] or 0) <= 15 if len(wms_times) > 1 else True,
        "minGapMinutes": cadence_summary["minGapMinutes"],
        "medianGapMinutes": cadence_summary["medianGapMinutes"],
        "maxGapMinutes": cadence_summary["maxGapMinutes"],
        "observedFrameCount": len(retrieved_frames),
        "failedFrameCount": len(failures),
    }
    session_metadata = {
        "session_id": f"{request.layers}_{_sanitize_timestamp_for_filename(retrieved_frames[0]['wmsTime'])}_{_sanitize_timestamp_for_filename(retrieved_frames[-1]['wmsTime'])}",
        "createdAt": _utc_now(),
        "source": source_label,
        "provider": provider,
        "layer": request.layers,
        "title": layer_capabilities["title"],
        "bbox": list(request.bbox),
        "extent3857": list(request.bbox),
        "crs": request.crs,
        "width": request.width,
        "height": request.height,
        "wmsUrl": endpoint,
        "requestedStartTime": _format_wms_time(requested_start),
        "requestedEndTime": _format_wms_time(requested_end),
        "availableStartTime": retrieved_frames[0]["wmsTime"],
        "availableEndTime": retrieved_frames[-1]["wmsTime"],
        "availableFrameCount": len(available_timestamps),
        "downloadedFrameCount": len(retrieved_frames),
        "failedTimestamps": failures,
        "cadenceMinutes": cadence_summary,
        "cache": {
            "databasePath": _cache_db_path(),
            "ttlSeconds": WMS_CACHE_TTL_SECONDS,
            "cacheHits": sum(1 for frame in retrieved_frames if frame.get("cacheHit")),
        },
        "validation": validation,
        "frames": [
            {
                "timestamp": frame["timestamp"],
                "wmsTime": frame["wmsTime"],
                "source": frame["source"],
                "layer": frame["layer"],
                "bbox": frame["bbox"],
                "crs": frame["crs"],
                "width": frame["width"],
                "height": frame["height"],
                "type": frame["type"],
                "filename": frame["filename"],
                "path": frame["path"],
                "url": f"/data/raw_frames/{frame['filename']}",
            }
            for frame in retrieved_frames
        ],
    }
    return {"frames": retrieved_frames, "session": session_metadata}


def fetch_wms_frames(request: FrameRetrievalRequest) -> List[dict]:
    return fetch_time_series(request)["frames"]
