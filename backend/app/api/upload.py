from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
import os
import shutil
import uuid
from pathlib import Path
from ..core.config import settings
from ..services.pipeline_service import create_job, process_job_background

router = APIRouter()

@router.post("/upload", status_code=202)
async def upload_stl(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Validações de segurança
    if not file.filename:
        raise HTTPException(status_code=400, detail="Nenhum arquivo enviado.")
        
    ext = Path(file.filename).suffix.lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Extensão inválida. Apenas .stl é permitido.")
    
    # Criar arquivo temporário isolado com nome sanitizado
    safe_filename = f"{uuid.uuid4()}{ext}"
    temp_filepath = settings.TEMP_DIR / safe_filename
    
    try:
        with open(temp_filepath, "wb") as buffer:
            # Proteção contra arquivos gigantes carregados na memória via restrição de chunking
            # e limitação do FastAPI no tamanho máximo do UploadFile antes de spooling, mas
            # vamos fazer a leitura em chunks para verificar o limite real.
            
            file.file.seek(0, 2)
            file_size = file.file.tell()
            file.file.seek(0)
            
            if file_size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
                raise HTTPException(status_code=413, detail=f"Arquivo excede limite de {settings.MAX_UPLOAD_SIZE_MB}MB")
                
            shutil.copyfileobj(file.file, buffer)
            
    except HTTPException:
        if temp_filepath.exists():
            os.remove(temp_filepath)
        raise
    except Exception as e:
        if temp_filepath.exists():
            os.remove(temp_filepath)
        raise HTTPException(status_code=500, detail=f"Erro ao salvar arquivo: {str(e)}")

    # Gerar Job
    job_id = create_job(str(temp_filepath), file.filename)
    
    # Disparar task de processamento em background (Milestone 1 é apenas inspeção)
    background_tasks.add_task(process_job_background, job_id, str(temp_filepath))
    
    return {"job_id": job_id, "status": "queued"}
