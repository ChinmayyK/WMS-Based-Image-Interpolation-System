"""API endpoint tests using FastAPI TestClient."""
import pytest
from fastapi.testclient import TestClient
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


# ---- Root ----

def test_root_endpoint(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert resp.json()["message"] == "Welcome to WMS-Based Image Interpolation API"


# ---- Job API ----

def test_job_not_found(client):
    resp = client.get("/api/v1/jobs/nonexistent")
    assert resp.status_code == 404


def test_job_status_not_found(client):
    resp = client.get("/api/v1/jobs/nonexistent/status")
    assert resp.status_code == 404


def test_job_stream_not_found(client):
    resp = client.get("/api/v1/jobs/nonexistent/stream")
    assert resp.status_code == 404


def test_job_audit_not_found(client):
    resp = client.get("/api/v1/jobs/nonexistent/audit")
    assert resp.status_code == 404


def test_job_export_not_found(client):
    resp = client.post("/api/v1/jobs/nonexistent/export")
    assert resp.status_code == 404


def test_job_exports_not_found(client):
    resp = client.get("/api/v1/jobs/nonexistent/exports")
    assert resp.status_code == 404


def test_job_evaluation_report_not_found(client):
    resp = client.get("/api/v1/evaluation/nonexistent/report")
    assert resp.status_code == 404


# ---- Cache API ----

def test_cache_status(client):
    resp = client.get("/api/v1/cache/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "directories" in data
    assert "total_size_mb" in data


# ---- Config API ----

def test_config_endpoint(client):
    resp = client.get("/api/v1/config")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "config" in data
    config = data["config"]
    assert "interpolation" in config
    assert "confidence" in config
    assert "data" in config


# ---- Error responses ----

def test_export_requires_completed_job(client):
    """POST /export on a non-existent job returns 404."""
    resp = client.post("/api/v1/jobs/fake-id/export")
    assert resp.status_code == 404
    assert "detail" in resp.json()


def test_frames_for_nonexistent_job(client):
    resp = client.get("/api/v1/jobs/nonexistent/frames")
    assert resp.status_code == 404
