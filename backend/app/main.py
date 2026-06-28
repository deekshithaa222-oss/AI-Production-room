from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .models import Investigation, InvestigationRequest
from .orchestrator import create_investigation, investigations


app = FastAPI(title="SentinelAI Infrastructure Incident Command API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "sentinelai-api"}


@app.post("/investigate", response_model=Investigation)
async def investigate(request: InvestigationRequest) -> Investigation:
    return create_investigation(request.description)


@app.get("/investigation/{investigation_id}", response_model=Investigation)
def get_investigation(investigation_id: str) -> Investigation:
    investigation = investigations.get(investigation_id)
    if not investigation:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation
