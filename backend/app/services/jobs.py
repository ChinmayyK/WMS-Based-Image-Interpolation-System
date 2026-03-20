"""
Job-oriented pipeline manager with audit logging and per-stage timing.

PRD v2.0 compliant: parameters storage, artifacts tracking, audit events.
"""
import asyncio
import concurrent.futures
import json
import logging
import os
import tempfile
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.models import FrameRetrievalRequest
from app.services.wms_client import fetch_time_series
from app.services.preprocessing import ensure_session_preprocessed
from app.api.routes import (
    build_frame_catalog,
    _safe_name,
    _resolve_catalog_path,
    _resolve_data_asset_path,
    _interpolated_timestamp,
)

logger = logging.getLogger(__name__)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_DIR = os.path.join(BASE_DIR, "data")
JOB_AUDITS_DIR = os.path.join(DATA_DIR, "job_audits")
JOB_AUDIT_RETENTION_DAYS = int(os.getenv("JOB_AUDIT_RETENTION_DAYS", "30"))


def _ensure_job_audits_dir() -> str:
    os.makedirs(JOB_AUDITS_DIR, exist_ok=True)
    return JOB_AUDITS_DIR


def _job_audit_path(job_id: str) -> str:
    return os.path.join(_ensure_job_audits_dir(), f"{job_id}.json")


def _atomic_write_json(path: str, payload: dict) -> None:
    directory = os.path.dirname(path)
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)


def _load_job_from_disk(job_id: str) -> Optional[Dict[str, Any]]:
    path = _job_audit_path(job_id)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        logger.exception("Failed to load persisted job audit for %s", job_id)
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _persist_job_to_disk(job: Dict[str, Any]) -> str:
    path = _job_audit_path(job["id"])
    snapshot = dict(job)
    snapshot["updated_at"] = datetime.now(timezone.utc).isoformat()
    _atomic_write_json(path, snapshot)
    return path


def _cleanup_old_job_audits() -> None:
    cutoff = datetime.now(timezone.utc) - timedelta(days=JOB_AUDIT_RETENTION_DAYS)
    audit_dir = _ensure_job_audits_dir()
    for filename in os.listdir(audit_dir):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(audit_dir, filename)
        try:
            mtime = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            try:
                os.unlink(path)
            except OSError:
                logger.warning("Failed to remove expired audit log %s", path)


def _classify_exception(exc: Exception) -> dict:
    message = str(exc)
    category = "NON_RETRIABLE"
    if any(token in message.upper() for token in ("429", "TIMEOUT", "CONNECTION", "TEMPORARY")):
        category = "RETRIABLE"
    elif any(token in message.upper() for token in ("FAILED TIMESTAMP", "MISSING", "PARTIAL")):
        category = "PARTIAL_FAILURE"
    return {
        "category": category,
        "message": message,
        "type": exc.__class__.__name__,
    }


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------

class JobSubmissionRequest(BaseModel):
    bbox: list[float]
    start_time: str
    end_time: str
    layers: str = "GOES-East_ABI_Band2_Red_Visible_1km"
    provider: str = "auto"
    interpolation_steps: int = 1


# ---------------------------------------------------------------------------
# Job Manager
# ---------------------------------------------------------------------------

class JobManager:
    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        _cleanup_old_job_audits()

    def create_job(self, parameters: Optional[dict] = None) -> str:
        _cleanup_old_job_audits()
        job_id = str(uuid.uuid4())
        self.jobs[job_id] = {
            "id": job_id,
            "status": "PENDING",
            "progress": 0.0,
            "phase": "queued",
            "message": "Job queued for processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
            "error": None,
            "result": None,
            "parameters": parameters or {},
            "artifacts": {},
            "audit_log": [],
            "stage_timings": {},
            "frame_confidence_assignments": [],
            "classified_errors": [],
            "final_output_paths": [],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._add_artifact(job_id, "audit_log_path", _job_audit_path(job_id))
        self._audit(job_id, "queued", "created", details={"parameters": parameters or {}})
        return job_id

    def update_job(self, job_id: str, updates: Dict[str, Any]):
        if job_id in self.jobs:
            self.jobs[job_id].update(updates)
            _persist_job_to_disk(self.jobs[job_id])

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        job = self.jobs.get(job_id)
        if job:
            return job
        persisted = _load_job_from_disk(job_id)
        if persisted:
            self.jobs[job_id] = persisted
        return persisted

    def get_audit_log(self, job_id: str) -> Optional[List[dict]]:
        job = self.get_job(job_id)
        return job["audit_log"] if job else None

    def _audit(self, job_id: str, stage: str, status: str, *, details: Optional[dict] = None, duration_ms: Optional[float] = None):
        """Append an audit event to the job."""
        if job_id not in self.jobs:
            return
        event = {
            "stage": stage,
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if duration_ms is not None:
            event["duration_ms"] = round(duration_ms, 2)
        if details:
            event["details"] = details
        self.jobs[job_id]["audit_log"].append(event)
        _persist_job_to_disk(self.jobs[job_id])

    def _set_stage_timing(self, job_id: str, stage: str, duration_ms: float):
        if job_id in self.jobs:
            self.jobs[job_id]["stage_timings"][stage] = round(duration_ms, 2)
            _persist_job_to_disk(self.jobs[job_id])

    def _add_artifact(self, job_id: str, key: str, value: Any):
        if job_id in self.jobs:
            self.jobs[job_id]["artifacts"][key] = value
            _persist_job_to_disk(self.jobs[job_id])

    def _record_frame_assignment(self, job_id: str, assignment: Dict[str, Any]):
        if job_id in self.jobs:
            self.jobs[job_id]["frame_confidence_assignments"].append(assignment)
            _persist_job_to_disk(self.jobs[job_id])

    def _set_final_output_paths(self, job_id: str, paths: List[str]):
        if job_id in self.jobs:
            self.jobs[job_id]["final_output_paths"] = paths
            _persist_job_to_disk(self.jobs[job_id])

    def _record_classified_error(self, job_id: str, exc: Exception, *, stage: str):
        if job_id not in self.jobs:
            return
        classified = {
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **_classify_exception(exc),
        }
        self.jobs[job_id]["classified_errors"].append(classified)
        self._audit(job_id, stage, "error_classified", details=classified)

    # -------------------------------------------------------------------
    # Pipeline execution
    # -------------------------------------------------------------------

    async def run_job(self, job_id: str, request: JobSubmissionRequest):
        loop = asyncio.get_event_loop()
        pool = concurrent.futures.ThreadPoolExecutor()

        try:
            # ========== STAGE 1: INGESTION ==========
            stage_start = time.monotonic()
            self.update_job(job_id, {
                "status": "PROCESSING", "phase": "ingestion",
                "progress": 5.0, "message": "Fetching observed frames from GIBS..."
            })
            self._audit(job_id, "ingestion", "started")

            fetch_req = FrameRetrievalRequest(
                bbox=request.bbox,
                start_time=request.start_time,
                end_time=request.end_time,
                layers=request.layers,
                provider=request.provider,
            )
            result = await loop.run_in_executor(pool, fetch_time_series, fetch_req)
            self._add_artifact(job_id, "ingestion_session_id", result.get("session", {}).get("session_id"))
            self._add_artifact(job_id, "ingestion_source", result.get("session", {}).get("source"))
            self._add_artifact(job_id, "failed_timestamps", result.get("session", {}).get("failedTimestamps", []))

            ingestion_ms = (time.monotonic() - stage_start) * 1000
            self._set_stage_timing(job_id, "ingestion", ingestion_ms)
            self._audit(job_id, "ingestion", "completed", duration_ms=ingestion_ms, details={
                "frames_fetched": result.get("session", {}).get("downloadedFrameCount", 0),
                "failures": len(result.get("session", {}).get("failedTimestamps", [])),
            })

            # ========== STAGE 2: PREPROCESSING ==========
            stage_start = time.monotonic()
            self.update_job(job_id, {
                "phase": "preprocessing", "progress": 30.0,
                "message": "Filtering invalid frames & preprocessing..."
            })
            self._audit(job_id, "preprocessing", "started")

            from app.services.metadata import persist_observed_session
            processed_session = await loop.run_in_executor(
                pool, lambda: ensure_session_preprocessed(result["session"], force=True)
            )
            observed_session_path = await loop.run_in_executor(pool, persist_observed_session, processed_session)
            self._add_artifact(job_id, "observed_session_path", observed_session_path)

            preproc_ms = (time.monotonic() - stage_start) * 1000
            self._set_stage_timing(job_id, "preprocessing", preproc_ms)
            self._audit(job_id, "preprocessing", "completed", duration_ms=preproc_ms, details={
                "valid_frames": processed_session.get("preprocessingSummary", {}).get("validFrameCount"),
                "report_path": processed_session.get("preprocessingReportPath"),
            })

            # ========== STAGE 3: INTERPOLATION ==========
            stage_start = time.monotonic()
            self.update_job(job_id, {
                "phase": "interpolation", "progress": 45.0,
                "message": "Building interpolation catalog..."
            })
            self._audit(job_id, "interpolation", "started")

            FRAME_CATALOG = await loop.run_in_executor(pool, build_frame_catalog)
            observed_frames = [f for f in FRAME_CATALOG if f.get("isOriginal") and f.get("isValid")]

            from app.services.confidence import (
                gap_minutes_between,
                MAX_INTERPOLATION_GAP_MINUTES,
                provenance_label_for,
                recommended_interpolation_frames,
                score_generated_sequence,
            )
            from app.services.interpolation import generate_intermediate_frames, interpolator
            from app.services.metadata import generate_metadata_for_frame
            from app.api.routes import INTERPOLATED_FRAMES_DIR, GAP_PLACEHOLDERS_DIR, LAST_CONFIDENCE_PROFILE
            from app.services.visualization import create_gap_placeholder

            total_pairs = len(observed_frames) - 1
            interpolated_count = 0

            if total_pairs <= 0:
                interp_ms = (time.monotonic() - stage_start) * 1000
                self._set_stage_timing(job_id, "interpolation", interp_ms)
                self._audit(job_id, "interpolation", "completed", duration_ms=interp_ms, details={"pairs": 0})
            else:
                for idx in range(total_pairs):
                    f1 = observed_frames[idx]
                    f2 = observed_frames[idx + 1]

                    pair_progress = 45.0 + (idx / total_pairs) * 45.0
                    self.update_job(job_id, {
                        "message": f"Interpolating pair {idx+1}/{total_pairs}...",
                        "progress": pair_progress,
                    })

                    gap_minutes = gap_minutes_between(f1["timestamp"], f2["timestamp"])
                    if gap_minutes is None or gap_minutes > MAX_INTERPOLATION_GAP_MINUTES:
                        self._audit(job_id, "interpolation", "skipped_pair", details={
                            "pair": idx + 1, "reason": "gap exceeds limit",
                            "gap_minutes": gap_minutes,
                        })
                        continue

                    max_frames = recommended_interpolation_frames(gap_minutes)
                    steps = max(1, min(request.interpolation_steps, max_frames))

                    f1_path = _resolve_catalog_path(f1, prefer_clean=True)
                    f2_path = _resolve_catalog_path(f2, prefer_clean=True)

                    def _do_interp(f1_=f1, f2_=f2, f1p=f1_path, f2p=f2_path, s=steps):
                        f1_ctx = {
                            "nodataMaskPath": _resolve_data_asset_path(f1_.get("nodataMaskUrl")),
                            "limbMaskPath": _resolve_data_asset_path(f1_.get("limbMaskUrl")),
                            "terminatorMaskPath": _resolve_data_asset_path(f1_.get("terminatorMaskUrl")),
                        }
                        f2_ctx = {
                            "nodataMaskPath": _resolve_data_asset_path(f2_.get("nodataMaskUrl")),
                            "limbMaskPath": _resolve_data_asset_path(f2_.get("limbMaskUrl")),
                            "terminatorMaskPath": _resolve_data_asset_path(f2_.get("terminatorMaskUrl")),
                        }
                        return generate_intermediate_frames(
                            f1p, f2p, INTERPOLATED_FRAMES_DIR, s,
                            file_prefix=f"interp_{_safe_name(f1_['timestamp'])}_{_safe_name(f2_['timestamp'])}",
                            frame0_context=f1_ctx, frame1_context=f2_ctx,
                        )

                    records = await loop.run_in_executor(pool, _do_interp)
                    interpolated_count += len(records)

                    # --- STAGE 4: CONFIDENCE (inline per pair) ---
                    def _do_scoring(generated_records, f1_=f1, f2_=f2, f1p=f1_path, f2p=f2_path, gm=gap_minutes):
                        import app.api.routes
                        diagnostics = interpolator.get_diagnostics()
                        batch_info = diagnostics["execution"].get("lastBatch") or {}
                        source0_context = {
                            "path": f1p,
                            "nodataMaskPath": _resolve_data_asset_path(f1_.get("nodataMaskUrl")),
                            "limbMaskPath": _resolve_data_asset_path(f1_.get("limbMaskUrl")),
                            "terminatorMaskPath": _resolve_data_asset_path(f1_.get("terminatorMaskUrl")),
                            "flags": f1_.get("preprocessingFlags") or f1_.get("flags") or [],
                        }
                        source1_context = {
                            "path": f2p,
                            "nodataMaskPath": _resolve_data_asset_path(f2_.get("nodataMaskUrl")),
                            "limbMaskPath": _resolve_data_asset_path(f2_.get("limbMaskUrl")),
                            "terminatorMaskPath": _resolve_data_asset_path(f2_.get("terminatorMaskUrl")),
                            "flags": f2_.get("preprocessingFlags") or f2_.get("flags") or [],
                        }
                        scores = score_generated_sequence(
                            generated_records,
                            f1p,
                            f2p,
                            gm,
                            app.api.routes.LAST_CONFIDENCE_PROFILE,
                            source_frame0=source0_context,
                            source_frame1=source1_context,
                        )

                        for r, score in zip(generated_records, scores):
                            ratio = r["ratio"]
                            ts = _interpolated_timestamp(f1_["timestamp"], f2_["timestamp"], ratio)
                            run = r.get("interpolation") or {}

                            rendered_as_gap = score["confidenceLabel"] == "REJECTED"
                            output_path = r["path"]
                            placeholder_reason = None
                            if rendered_as_gap:
                                placeholder_reason = "Rejected by adaptive confidence classifier"
                                placeholder_name = f"{os.path.splitext(os.path.basename(r['path']))[0]}_rejected.png"
                                output_path = os.path.join(GAP_PLACEHOLDERS_DIR, placeholder_name)
                                create_gap_placeholder(output_path, ts, placeholder_reason, title="REJECTED FRAME")

                            generate_metadata_for_frame(
                                output_path, f1p, f2p, ts, score["confidence"],
                                confidence_label=score["confidenceLabel"],
                                provenance_label=score.get("provenanceLabel") or provenance_label_for(score["confidenceLabel"]),
                                metrics=score["metrics"],
                                source_timestamps=[f1_["timestamp"], f2_["timestamp"]],
                                gap_minutes=score["gapMinutes"],
                                confidence_method=score["confidenceMethod"],
                                model_info=diagnostics["model"],
                                rendered_as_gap=rendered_as_gap,
                                placeholder_reason=placeholder_reason,
                                session_id=processed_session.get("session_id"),
                                frame_type="GAP" if rendered_as_gap else "INTERPOLATED",
                                interpolation={
                                    "jobId": batch_info.get("jobId"),
                                    "executionMode": run.get("executionMode"),
                                    "inferenceTimeMs": run.get("durationMs"),
                                },
                            )
                            self._record_frame_assignment(
                                job_id,
                                {
                                    "timestamp": ts,
                                    "confidence": score["confidence"],
                                    "confidence_label": score["confidenceLabel"],
                                    "provenance_label": score.get("provenanceLabel"),
                                    "output_path": output_path,
                                    "rendered_as_gap": rendered_as_gap,
                                },
                            )

                    await loop.run_in_executor(pool, _do_scoring, records)

                interp_ms = (time.monotonic() - stage_start) * 1000
                self._set_stage_timing(job_id, "interpolation", interp_ms)
                self._audit(job_id, "interpolation", "completed", duration_ms=interp_ms, details={
                    "pairs_processed": total_pairs,
                    "frames_generated": interpolated_count,
                    "model": interpolator.get_diagnostics().get("model", {}).get("name", "unknown"),
                })

            # ========== STAGE 5: CONFIDENCE (summary) ==========
            self._audit(job_id, "confidence", "completed", details={
                "thresholds": {
                    "high": 0.85, "medium": 0.65, "low": 0.45,
                    "max_gap_minutes": MAX_INTERPOLATION_GAP_MINUTES,
                },
            })

            # ========== STAGE 6: FINALIZE ==========
            stage_start = time.monotonic()
            self.update_job(job_id, {
                "phase": "finalizing", "progress": 96.0,
                "message": "Rebuilding frame catalog..."
            })

            import app.api.routes
            app.api.routes.FRAME_CATALOG = await loop.run_in_executor(pool, build_frame_catalog)
            final_output_paths = [
                _resolve_catalog_path(frame, prefer_clean=False)
                for frame in app.api.routes.FRAME_CATALOG
                if _resolve_catalog_path(frame, prefer_clean=False)
            ]

            finalize_ms = (time.monotonic() - stage_start) * 1000
            self._set_stage_timing(job_id, "finalize", finalize_ms)
            self._add_artifact(job_id, "frame_count", len(app.api.routes.FRAME_CATALOG))
            self._set_final_output_paths(job_id, final_output_paths)

            self.update_job(job_id, {
                "status": "COMPLETED",
                "phase": "done",
                "progress": 100.0,
                "message": "Job finished successfully",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
            self._audit(job_id, "pipeline", "completed", details={
                "total_frames": len(app.api.routes.FRAME_CATALOG),
                "stage_timings": self.jobs[job_id].get("stage_timings", {}),
                "final_output_paths": final_output_paths,
            })

        except Exception as e:
            logger.exception("Job %s failed", job_id)
            self._record_classified_error(job_id, e, stage=self.jobs.get(job_id, {}).get("phase", "unknown"))
            self._audit(job_id, self.jobs.get(job_id, {}).get("phase", "unknown"), "failed", details={"error": str(e)})
            self.update_job(job_id, {
                "status": "FAILED",
                "error": str(e),
                "message": f"Job failed: {str(e)}",
                "completed_at": datetime.now(timezone.utc).isoformat(),
            })
        finally:
            pool.shutdown(wait=False)


job_manager = JobManager()
