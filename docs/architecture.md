# System Architecture

The WMS-Based Image Interpolation System follows a decoupled, client-server architecture to handle geospatial operations seamlessly.

## 1. Backend API (FastAPI)
The backend functions as the processing and data retrieval engine:
- **WMS Service Wrapper (`services/wms_client.py`)**: Responsible for constructing REST/SOAP requests to OGC-compliant WMS servers (e.g., GeoServer), retrieving specific frames based on BBOX, Temporal parameters, and CRS.
- **Geospatial Processing Module (`services/geospatial.py`)**: Uses `rasterio` and `GDAL` to re-project coordinates and compute statistical normalizations required for machine learning. Aligns images pixel-by-pixel.
- **AI Inference Engine (`services/interpolation.py`)**: A wrapper around the RIFE (Real-Time Intermediate Flow Estimation) PyTorch model. Performs tensor transformations on frames, computes optical flow, and returns generated frames back to the workflow.

## 2. Frontend Interface (React & OpenLayers)
The user interface connects to the FastAPI backend:
- **Map Engine**: Uses OpenLayers to present WMS tiles via standard Web Mercator coordinates.
- **Controls**: Includes timeline sliders to trigger fetching frames, and buttons to invoke the `/interpolate` backend methods. 

## Data Flow
1. **User interaction** → Selects bounding box and date range.
2. **Frontend** → Calls `POST /api/frames/fetch`.
3. **Backend** → Queries external WMS, saves raw data locally in `data/`, returns metadata to Frontend.
4. **User action** → clicks "Interpolate".
5. **Frontend** → Calls `POST /api/frames/interpolate`.
6. **Backend** → Runs AI model on stored frames, caches newly generated frames, returns new metadata.
