"""Tests for the job pipeline and manager."""
import os

import pytest
from app.services.jobs import JobManager, JobSubmissionRequest


def test_create_job_stores_parameters():
    """Job creation stores request parameters and initializes audit log."""
    mgr = JobManager()
    params = {"bbox": [0, 0, 1, 1], "start_time": "2024-01-01", "end_time": "2024-01-02", "layers": "TestLayer"}
    job_id = mgr.create_job(parameters=params)

    job = mgr.get_job(job_id)
    assert job is not None
    assert job["status"] == "PENDING"
    assert job["parameters"] == params
    assert "audit_log_path" in job["artifacts"]
    assert len(job["audit_log"]) == 1
    assert job["audit_log"][0]["stage"] == "queued"
    assert job["audit_log"][0]["status"] == "created"


def test_update_job_merges_updates():
    mgr = JobManager()
    job_id = mgr.create_job()
    mgr.update_job(job_id, {"status": "PROCESSING", "progress": 50.0})

    job = mgr.get_job(job_id)
    assert job["status"] == "PROCESSING"
    assert job["progress"] == 50.0


def test_audit_log_appends_events():
    mgr = JobManager()
    job_id = mgr.create_job()
    mgr._audit(job_id, "ingestion", "started")
    mgr._audit(job_id, "ingestion", "completed", duration_ms=1234.5, details={"frames": 10})

    audit = mgr.get_audit_log(job_id)
    assert len(audit) == 3  # 1 from create + 2 manual
    assert audit[1]["stage"] == "ingestion"
    assert audit[1]["status"] == "started"
    assert audit[2]["duration_ms"] == 1234.5
    assert audit[2]["details"]["frames"] == 10


def test_stage_timing_storage():
    mgr = JobManager()
    job_id = mgr.create_job()
    mgr._set_stage_timing(job_id, "ingestion", 512.33)
    mgr._set_stage_timing(job_id, "preprocessing", 200.11)

    job = mgr.get_job(job_id)
    assert job["stage_timings"]["ingestion"] == 512.33
    assert job["stage_timings"]["preprocessing"] == 200.11


def test_artifacts_tracking():
    mgr = JobManager()
    job_id = mgr.create_job()
    mgr._add_artifact(job_id, "frame_count", 42)
    mgr._add_artifact(job_id, "export_path", "/data/exports/test")

    job = mgr.get_job(job_id)
    assert job["artifacts"]["frame_count"] == 42
    assert job["artifacts"]["export_path"] == "/data/exports/test"


def test_get_nonexistent_job_returns_none():
    mgr = JobManager()
    assert mgr.get_job("nonexistent") is None
    assert mgr.get_audit_log("nonexistent") is None


def test_job_submission_request_defaults():
    req = JobSubmissionRequest(bbox=[0, 0, 1, 1], start_time="2024-01-01", end_time="2024-01-02")
    assert req.layers == "GOES-East_ABI_Band2_Red_Visible_1km"
    assert req.interpolation_steps == 1


def test_job_persists_and_loads_from_disk(tmpdir, monkeypatch):
    from app.services import jobs as jobs_module

    monkeypatch.setattr(jobs_module, "JOB_AUDITS_DIR", os.path.join(tmpdir, "job_audits"))
    mgr = jobs_module.JobManager()
    job_id = mgr.create_job(parameters={"bbox": [1, 2, 3, 4]})

    reloaded = jobs_module.JobManager()
    job = reloaded.get_job(job_id)
    assert job is not None
    assert job["parameters"]["bbox"] == [1, 2, 3, 4]
    assert os.path.exists(job["artifacts"]["audit_log_path"])
