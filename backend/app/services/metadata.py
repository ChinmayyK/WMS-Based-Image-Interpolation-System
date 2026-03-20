import json
import logging
import os
import tempfile
import time
from typing import Optional


BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
METADATA_DIR = os.path.join(DATA_DIR, "metadata")
OBSERVED_SESSION_FILENAME = "observed_session.json"
INTERPOLATION_LOG_FILENAME = "interpolation_log.json"
logger = logging.getLogger(__name__)


def get_metadata_dir() -> str:
    os.makedirs(METADATA_DIR, exist_ok=True)
    return METADATA_DIR


def get_observed_session_path() -> str:
    return os.path.join(get_metadata_dir(), OBSERVED_SESSION_FILENAME)


def get_interpolation_log_path() -> str:
    return os.path.join(get_metadata_dir(), INTERPOLATION_LOG_FILENAME)


def _atomic_write_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    os.replace(temp_path, path)


def _safe_load_json(path: str, *, default: dict) -> dict:
    if not os.path.exists(path):
        return dict(default)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        corrupt_path = f"{path}.corrupt-{int(time.time())}"
        try:
            os.replace(path, corrupt_path)
        except OSError:
            logger.warning("Failed to quarantine corrupt JSON file %s after %s", path, exc)
        else:
            logger.warning("Recovered from corrupt JSON file %s; moved to %s", path, corrupt_path)
        return dict(default)
    if not isinstance(payload, dict):
        return dict(default)
    return payload


def persist_observed_session(session_metadata: dict) -> str:
    output_path = get_observed_session_path()
    _atomic_write_json(output_path, session_metadata)
    return output_path


def load_observed_session() -> Optional[dict]:
    session_path = get_observed_session_path()
    if not os.path.exists(session_path):
        return None
    return _safe_load_json(session_path, default={})


def load_interpolation_log() -> dict:
    log_path = get_interpolation_log_path()
    payload = _safe_load_json(log_path, default={"jobs": []})
    payload.setdefault("jobs", [])
    return payload


def append_interpolation_log(job: dict) -> str:
    log = load_interpolation_log()
    log["jobs"].append(job)
    log["latest"] = job

    log_path = get_interpolation_log_path()
    _atomic_write_json(log_path, log)
    return log_path


def generate_metadata_for_frame(
    frame_path: str,
    source_frame1: str,
    source_frame2: str,
    timestamp_str: str,
    confidence: float,
    *,
    confidence_label: str = "LOW",
    provenance_label: Optional[str] = None,
    metrics: Optional[dict] = None,
    source_timestamps: Optional[list[str]] = None,
    gap_minutes: Optional[float] = None,
    confidence_method: Optional[str] = None,
    model_info: Optional[dict] = None,
    rendered_as_gap: bool = False,
    placeholder_reason: Optional[str] = None,
    session_id: Optional[str] = None,
    frame_type: str = "INTERPOLATED",
    interpolation: Optional[dict] = None,
    masks: Optional[dict] = None,
    motion: Optional[dict] = None,
    audit: Optional[dict] = None,
):
    """
    Generate metadata JSON for an interpolated or placeholder frame.
    """
    base_name = os.path.basename(frame_path)
    name_without_ext = os.path.splitext(base_name)[0]

    metadata = {
        "frame_id": name_without_ext,
        "time": timestamp_str,
        "type": frame_type,
        "generated": True,
        "confidence": round(confidence, 4),
        "confidence_label": confidence_label,
        "provenance_label": provenance_label,
        "source_frames": [os.path.basename(source_frame1), os.path.basename(source_frame2)],
        "source_timestamps": source_timestamps or [],
        "gap_minutes": gap_minutes,
        "confidence_method": confidence_method,
        "metrics": metrics or {},
        "model": model_info or {},
        "rendered_as_gap": rendered_as_gap,
        "placeholder_reason": placeholder_reason,
        "session_id": session_id,
        "generated_at": time.time(),
        "interpolation": interpolation or {},
        "masks": masks or {},
        "motion": motion or {},
        "audit": audit or {},
    }

    meta_dir = get_metadata_dir()
    meta_path = os.path.join(meta_dir, f"{name_without_ext}.json")
    _atomic_write_json(meta_path, metadata)

    return meta_path
