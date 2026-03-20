from fastapi import APIRouter, HTTPException

from app.services.evaluation import get_job_evaluation, get_latest_evaluation


router = APIRouter()


@router.get("/evaluation/{job_id}/report")
async def get_job_evaluation_report(job_id: str):
    report = get_latest_evaluation()
    if not report:
        raise HTTPException(status_code=404, detail="Evaluation report not found")

    evaluation = get_job_evaluation(job_id)
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation for job not found")

    return {
        "status": "success",
        "job_id": job_id,
        "evaluation": evaluation,
        "report": {
            "generatedAt": report.get("generatedAt"),
            "version": report.get("version"),
            "heldOutProtocol": report.get("heldOutProtocol"),
            "thresholds": report.get("thresholds"),
            "targetValidation": report.get("targetValidation"),
            "distributions": report.get("distributions"),
            "baselineDistributions": report.get("baselineDistributions"),
            "confidenceValidation": report.get("confidenceValidation"),
            "confidenceCalibration": report.get("confidenceCalibration"),
            "qualificationGate": report.get("qualificationGate"),
            "datasets": report.get("datasets"),
            "reportPaths": report.get("reportPaths"),
        },
    }
