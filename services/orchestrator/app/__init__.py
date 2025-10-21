from fastapi import FastAPI
from .routes import router

app = FastAPI(title="IntelliMaint Orchestrator")
app.include_router(router, prefix="/api/v1")

