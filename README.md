# WMS-Based Image Interpolation System

A full-stack research prototype for fetching satellite images from WMS, preprocessing them geospatially, generating intermediate frames using AI (RIFE), and visualizing on a WebGIS interface. 

**Industry Focus**: This project is engineered with robust standards for Indian organizations, including the Indian Meteorological Department (IMD), ISRO, and Indian Defense sectors. It is highly applicable for continuous weather forecasting, border surveillance, and scalable disaster monitoring across the Indian subcontinent.

## Project Structure
- `backend/`: FastAPI Python backend. Includes WMS Data Acquisition (via `requests`), Geospatial image preprocessing (via `opencv`), and AI interpolation.
- `frontend/`: React + OpenLayers frontend.
- `docs/`: System documentation and architecture.
- `scripts/`: Automation scripts.

## Setup & Run Instructions

### 1. Running on your device a cloned repo
Since the environment and virtual environments are already set up on your machine, you can simply run the application:
```bash
make run-backend
make run-frontend
```

*(Alternatively, use `./scripts/run_pipeline.sh` if you prefer to launch both together).*

### 2. Setting up from a fresh clone
If someone else clones this repository, they need to install the dependencies first before running. 
They should execute:
```bash
# 1. Setup the environment (installs python and node dependencies)
make setup

# 2. Run the application
make run-backend
make run-frontend
```

## Testing

To run the automated unit tests for the backend (including WMS Data Acquisition and Geospatial modules):
```bash
make test-backend
```
*(On Windows, you may need to run `cd backend && pytest tests/` manually if `make` is not fully supported).*

## Refer to `docs/` for detailed architectural and workflow information.
