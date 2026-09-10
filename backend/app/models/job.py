from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from enum import Enum
from datetime import datetime

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"

class ProcessingParameters(BaseModel):
    diametro_tubo: float = 2.0
    folga_ajuste: float = 0.3
    angulo_insercao: float = 15.0
    espessura_minima: float = 1.2

class JobResult(BaseModel):
    job_id: str
    status: JobStatus
    created_at: datetime
    updated_at: datetime
    parameters: Optional[ProcessingParameters] = None
    input_file: str
    mesh_metrics: Optional[Dict[str, Any]] = None
    warnings: List[str] = []
    errors: List[str] = []
