"""
Cache & storage management + configuration control endpoints.
"""
import logging
import os
import shutil
from typing import Optional

import yaml
from fastapi import APIRouter, HTTPException

logger = logging.getLogger(__name__)
router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

CACHE_DIRS = {
    "raw_frames": os.path.join(DATA_DIR, "raw_frames"),
    "clean_frames": os.path.join(DATA_DIR, "clean_frames"),
    "interpolated_frames": os.path.join(DATA_DIR, "interpolated_frames"),
    "gap_placeholders": os.path.join(DATA_DIR, "gap_placeholders"),
    "exports": os.path.join(DATA_DIR, "exports"),
    "evaluations": os.path.join(DATA_DIR, "evaluations"),
    "metadata": os.path.join(DATA_DIR, "metadata"),
}


def _dir_stats(path: str) -> dict:
    """Return file count and total size for a directory."""
    if not os.path.isdir(path):
        return {"exists": False, "file_count": 0, "size_bytes": 0}
    total_size = 0
    file_count = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            fp = os.path.join(root, f)
            try:
                total_size += os.path.getsize(fp)
                file_count += 1
            except OSError:
                pass
    return {"exists": True, "file_count": file_count, "size_bytes": total_size}


@router.get("/cache/status")
async def cache_status():
    """Report frame counts and disk usage per cache directory."""
    stats = {}
    total_bytes = 0
    total_files = 0
    for key, path in CACHE_DIRS.items():
        s = _dir_stats(path)
        stats[key] = s
        total_bytes += s["size_bytes"]
        total_files += s["file_count"]
    return {
        "status": "success",
        "directories": stats,
        "total_files": total_files,
        "total_size_bytes": total_bytes,
        "total_size_mb": round(total_bytes / (1024 * 1024), 2),
    }


@router.post("/cache/clear")
async def cache_clear():
    """Remove interpolated frames, exports, and gap placeholders."""
    cleared = {}
    clearable = ["interpolated_frames", "gap_placeholders", "exports"]
    for key in clearable:
        path = CACHE_DIRS.get(key)
        if path and os.path.isdir(path):
            before = _dir_stats(path)
            shutil.rmtree(path, ignore_errors=True)
            os.makedirs(path, exist_ok=True)
            cleared[key] = {"removed_files": before["file_count"], "freed_bytes": before["size_bytes"]}
        else:
            cleared[key] = {"removed_files": 0, "freed_bytes": 0}
    return {"status": "success", "cleared": cleared}


@router.get("/config")
async def get_config():
    """Return current runtime configuration from config.yaml."""
    if not os.path.exists(CONFIG_PATH):
        raise HTTPException(status_code=404, detail="config.yaml not found")
    with open(CONFIG_PATH, "r") as f:
        config = yaml.safe_load(f)
    return {"status": "success", "config": config}
