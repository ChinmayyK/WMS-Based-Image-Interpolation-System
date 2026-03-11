# Setup and Run Instructions

Follow these instructions to configure and execute the project locally.

## Dependencies

- Python 3.9+
- Node.js 18+
- GDAL tools installed on system

## Simple Setup

We provide shell scripts and a Makefile to ease the installation.

### Option 1: Using the provided bash script
```bash
chmod +x scripts/*.sh
./scripts/setup_env.sh
```

### Option 2: Using Make
```bash
make setup
```

## Running the Application

Once the setup finishes, start up the local server and client:

### Using single script (Recommended)
```bash
./scripts/run_pipeline.sh
```
This boots up the backend on port 8000 and the vite server concurrently.

### Manual Launching
**Terminal 1:**
```bash
cd backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**Terminal 2:**
```bash
cd frontend
npm run dev
```

Navigate to the frontend path in your browser to view the WebGIS setup.
