from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .core.config import settings
from .api import upload, jobs

app = FastAPI(title=settings.PROJECT_NAME)

# Adicionar CORS para o Nuxt futuramente
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Trocar por domínios específicos em prod
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router, prefix=settings.API_V1_STR, tags=["Upload"])
app.include_router(jobs.router, prefix=f"{settings.API_V1_STR}/jobs", tags=["Jobs"])

@app.get("/")
def root():
    return {"message": "AuriMold API is running."}
