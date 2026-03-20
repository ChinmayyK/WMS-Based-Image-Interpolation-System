#!/usr/bin/env python3
"""
Fetch a full GOES observed time series from NASA GIBS and persist the active
session manifest used by the backend and frontend.

Usage:
    cd backend
    python fetch_satellite_data.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.models import FrameRetrievalRequest
from app.services.metadata import get_observed_session_path, persist_observed_session
from app.services.wms_client import fetch_time_series


def main():
    request = FrameRetrievalRequest()
    result = fetch_time_series(request)
    session_path = persist_observed_session(result["session"])

    print("=" * 72)
    print("NASA GIBS GOES Time-Series Fetch")
    print("=" * 72)
    print(f"Source:   {result['session']['source']}")
    print(f"Layer:    {result['session']['layer']}")
    print(f"BBOX:     {result['session']['bbox']}")
    print(f"Window:   {result['session']['requestedStartTime']} -> {result['session']['requestedEndTime']}")
    print(f"Frames:   {result['session']['downloadedFrameCount']} observed")
    print(f"Cadence:  {json.dumps(result['session']['cadenceMinutes'])}")
    print(f"Failures: {len(result['session']['failedTimestamps'])}")
    print(f"Session:  {session_path}")
    print()

    for frame in result["session"]["frames"]:
        print(f"  {frame['timestamp']} -> {frame['filename']}")


if __name__ == "__main__":
    main()
