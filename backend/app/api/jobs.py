from fastapi import APIRouter, HTTPException
from ..services.pipeline_service import get_job
from ..models.job import JobResult

router = APIRouter()

@router.get("/{job_id}", response_model=JobResult)
def get_job_status(job_id: str):
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    return job
