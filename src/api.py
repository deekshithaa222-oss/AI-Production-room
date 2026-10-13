from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import Response

from src.core.admission import AdmissionController
from src.core.circuit_breaker import CircuitBreaker
from src.core.orchestrator import InferenceRequest, Orchestrator
from src.telemetry.metrics import render_metrics

app = FastAPI(title="AI Production Room", version="0.1.0")

admission = AdmissionController(rate_limit_per_second=15.0, bucket_capacity=30, max_concurrency=10)
breaker = CircuitBreaker(failure_threshold=3, timeout_seconds=8.0, cooldown_seconds=10.0)

orchestrator = Orchestrator(
    primary_endpoint="https://primary.example.com/infer",
    fallback_endpoint="https://secondary.example.com/infer",
    max_concurrency=10,
    requests_per_second=15.0,
    breaker=breaker,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=render_metrics(), media_type="text/plain; version=0.7.0")


@app.post("/infer")
def infer(request: dict[str, str]) -> dict[str, object]:
    prompt = request.get("prompt", "")
    response = orchestrator.handle(InferenceRequest(prompt=prompt, max_tokens=256, metadata={"source": "api"}))
    return response
