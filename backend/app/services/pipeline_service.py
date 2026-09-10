import uuid
from datetime import datetime, timezone
from typing import Dict
from ..models.job import JobResult, JobStatus, ProcessingParameters
from ..geometry.loader import inspect_mesh
import asyncio
import traceback
import os

# Em-memória storage temporário para os jobs. Em produção usaria banco de dados/Redis.
jobs_db: Dict[str, JobResult] = {}

async def process_job_background(job_id: str, filepath: str):
    """
    Executa o processamento do job em background.
    Para o Milestone 1, isso faz apenas a inspeção inicial.
    """
    job = jobs_db.get(job_id)
    if not job:
        return

    job.status = JobStatus.PROCESSING
    job.updated_at = datetime.now(timezone.utc)
    
    try:
        # Run synchronous blocking CPU-bound work in executor
        loop = asyncio.get_running_loop()
        metrics = await loop.run_in_executor(None, inspect_mesh, filepath)
        
        job.mesh_metrics = metrics.model_dump()
        job.status = JobStatus.COMPLETED
    except Exception as e:
        job.errors.append(str(e))
        job.errors.append(traceback.format_exc())
        job.status = JobStatus.FAILED
    finally:
        job.updated_at = datetime.now(timezone.utc)
        # Em produção, removeríamos o arquivo temporário após sucesso, mas deixaremos para testes por enquanto.

def create_job(filepath: str, original_filename: str) -> str:
    job_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    jobs_db[job_id] = JobResult(
        job_id=job_id,
        status=JobStatus.QUEUED,
        created_at=now,
        updated_at=now,
        input_file=original_filename
    )
    return job_id

def get_job(job_id: str) -> JobResult | None:
    return jobs_db.get(job_id)
