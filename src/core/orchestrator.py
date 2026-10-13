from __future__ import annotations

import time
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from src.core.admission import AdmissionController
from src.core.circuit_breaker import CircuitBreaker, CircuitBreakerError


class InferenceRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    max_tokens: int = Field(default=256, ge=1, le=4096)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class Orchestrator:
    def __init__(
        self,
        primary_endpoint: str,
        fallback_endpoint: Optional[str] = None,
        max_concurrency: int = 8,
        requests_per_second: float = 12.0,
        breaker: Optional[CircuitBreaker] = None,
    ):
        self.primary_endpoint = primary_endpoint
        self.fallback_endpoint = fallback_endpoint
        self.admission = AdmissionController(rate_limit_per_second=requests_per_second, bucket_capacity=max_concurrency * 2, max_concurrency=max_concurrency)
        self.breaker = breaker or CircuitBreaker(failure_threshold=5, timeout_seconds=8.0, cooldown_seconds=30.0)

    def _primary(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "provider": "primary",
            "endpoint": self.primary_endpoint,
            "latency_ms": 420,
        }

    def _fallback(self) -> Dict[str, Any]:
        return {
            "status": "degraded",
            "provider": "fallback",
            "endpoint": self.fallback_endpoint or "local-quantized-model",
            "latency_ms": 700,
            "warning": "Primary endpoint unavailable; fallback path activated.",
        }

    def handle(self, request: InferenceRequest) -> Dict[str, Any]:
        with self.admission:
            start = time.monotonic()

            def operation():
                if request.prompt.strip() == "":
                    raise ValueError("Prompt cannot be empty")
                return self._primary()

            def fallback():
                return self._fallback()

            try:
                result = self.breaker.call(operation, fallback=fallback, allowed_exceptions=(ValueError, TimeoutError, RuntimeError))
                ttft_seconds = time.monotonic() - start
                return {**result, "ttft_seconds": round(ttft_seconds, 4), "request": request.prompt[:80]}
            except CircuitBreakerError:
                return {
                    "status": "rejected",
                    "provider": "none",
                    "warning": "Circuit is open and requests are being throttled.",
                    "ttft_seconds": 0.0,
                }
