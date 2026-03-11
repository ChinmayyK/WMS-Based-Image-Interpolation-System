# System Workflow

This document explains the step-by-step workflow of the application from end-to-end.

## 1. Initiation
The operator runs `./scripts/run_pipeline.sh` to begin both the Python backend and the React development frontend. The user opens `localhost:5173`.

## 2. WMS Frame Extraction
The system is built to target satellite imagery servers.
* The frontend makes a request providing `[minX, minY, maxX, maxY]` as the bounding box, and timestamps for Frame A and Frame B.
* The backend downloads the resulting frames.
* Geospatial normalization aligns pixels and scales dimensions.

## 3. Frame Interpolation
The pipeline runs RIFE to generate intermediary observations where data is naturally missing due to satellite orbit constraints.
* Frame A and Frame B are encoded into the ML pipeline.
* Optical flows are computed.
* Missing frames are written inside the `backend/data/` folder and registered in the response.

## 4. Animation Rendering
* The React client lists the resulting set of temporal frames.
* The OpenLayers map receives Image Layers with corresponding metadata to animate the sequence on loop.
