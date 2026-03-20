import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import router as api_router
from app.api.jobs import router as jobs_router
from app.api.cache import router as cache_router
from app.api.evaluation import router as evaluation_router
import os
import yaml

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(asctime)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = FastAPI(title="WMS-Based Image Interpolation System API")

# Load config
config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.yaml")
try:
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
        logger.info(f"Loaded configuration from {config_path}")
except Exception as e:
    logger.warning(f"Could not load config.yaml: {e}")

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Setup path to data directories relative to current file
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")

app.mount("/data", StaticFiles(directory=DATA_DIR), name="data")

app.include_router(api_router, prefix="/api")
app.include_router(jobs_router, prefix="/api/v1/jobs")
app.include_router(cache_router, prefix="/api/v1")
app.include_router(evaluation_router, prefix="/api/v1")

@app.get("/")
def read_root():
    return {"message": "Welcome to WMS-Based Image Interpolation API"}
