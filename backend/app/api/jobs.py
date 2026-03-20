import asyncio
import json
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from app.services.jobs import job_manager, JobSubmissionRequest
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/")
async def submit_job(request: JobSubmissionRequest, background_tasks: BackgroundTasks):
    job_id = job_manager.create_job(parameters=request.dict())
    background_tasks.add_task(job_manager.run_job, job_id, request)
    return {"status": "success", "job_id": job_id}

@router.get("/{job_id}")
async def get_job(job_id: str):
    """Return full job model including parameters, artifacts, stage timings."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "success", "job": job}

@router.get("/{job_id}/status")
async def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "success", "job": job}


@router.get("/{job_id}/stream")
async def stream_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        while True:
            current = job_manager.get_job(job_id)
            if not current:
                yield "event: error\ndata: {\"detail\":\"Job not found\"}\n\n"
                break

            payload = json.dumps({"status": "success", "job": current})
            yield f"event: status\ndata: {payload}\n\n"

            if current.get("status") in {"COMPLETED", "FAILED"}:
                break
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

@router.get("/{job_id}/audit")
async def get_job_audit(job_id: str):
    """Return structured audit log for a job."""
    audit = job_manager.get_audit_log(job_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"status": "success", "job_id": job_id, "events": audit}

@router.get("/{job_id}/frames")
async def get_job_frames(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
        
    if job["status"] != "COMPLETED":
        return {"status": "pending", "message": "Job is not fully complete"}
        
    import app.api.routes
    from app.api.routes import _load_session, _session_summary
    return {
        "status": "success",
        "frames": app.api.routes.FRAME_CATALOG,
        "session": _session_summary(_load_session())
    }


@router.post("/{job_id}/export")
async def export_job(job_id: str, background_tasks: BackgroundTasks):
    """Trigger multi-output export for a completed job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "COMPLETED":
        raise HTTPException(status_code=400, detail="Job must be COMPLETED before export")

    try:
        import app.api.routes
        from app.services.interpolation import interpolator
        from app.services.video_export import export_multi_output

        frames = app.api.routes.FRAME_CATALOG
        if not frames:
            raise HTTPException(status_code=400, detail="No frames available for export")

        model_info = interpolator.get_diagnostics().get("model", {})
        result = export_multi_output(
            [f if isinstance(f, dict) else f for f in frames],
            fps=15,
            job_name=f"job_{job_id}",
            job_id=job_id,
            model_info=model_info,
        )

        # Store export result on the job
        job_manager.update_job(job_id, {"export_result": result})

        return {"status": "success", "export": result}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Export failed for job %s", job_id)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/{job_id}/exports")
async def get_job_exports(job_id: str):
    """Return export file URLs and metadata for a job."""
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    export_result = job.get("export_result")
    if not export_result:
        # Try loading from disk
        from app.services.video_export import get_export_summary
        export_result = get_export_summary(job_id)

    if not export_result:
        return {"status": "pending", "message": "No export has been run for this job yet"}

    return {"status": "success", "export": export_result}


@router.get("/{job_id}/evaluation")
async def get_job_evaluation(job_id: str):
    from app.services.evaluation import get_job_evaluation as load_job_evaluation
    from app.services.evaluation import get_latest_evaluation

    evaluation = load_job_evaluation(job_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation for job not found")

    latest = get_latest_evaluation()
    return {
        "status": "success",
        "job_id": job_id,
        "evaluation": evaluation,
        "summary": {
            "generatedAt": (latest or {}).get("generatedAt"),
            "thresholds": (latest or {}).get("thresholds"),
            "targetValidation": (latest or {}).get("targetValidation"),
            "distributions": (latest or {}).get("distributions"),
            "confidenceValidation": (latest or {}).get("confidenceValidation"),
            "qualificationGate": (latest or {}).get("qualificationGate"),
            "reportPaths": (latest or {}).get("reportPaths"),
        },
    }
