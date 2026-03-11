# WMS-Based Image Interpolation System

A full-stack research prototype for fetching satellite images from WMS, preprocessing them geospatially, generating intermediate frames using AI (RIFE), and visualizing on a WebGIS interface.

## Project Structure
- `backend/`: FastAPI Python backend for WMS, Geospatial processing, and AI interpolation.
- `frontend/`: React + OpenLayers frontend.
- `docs/`: System documentation and architecture.
- `scripts/`: Automation scripts.

## Setup Instructions

Run the setup script:
```bash
./scripts/setup_env.sh
```

Alternatively, you can use the Makefile:
```bash
make setup
```

## Running the Application

To run both backend and frontend, you can use the Makefile commands or the provided run script:
```bash
./scripts/run_pipeline.sh
```

Or run them individually:
```bash
make run-backend
make run-frontend
```

## Refer to `docs/` for detailed architectural and workflow information.
