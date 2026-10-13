from __future__ import annotations

from typing import Optional

from prometheus_client import Counter, Gauge, Histogram, generate_latest

ai_inference_ttft_seconds = Histogram(
    "ai_inference_ttft_seconds",
    "Time to first token across inference requests.",
    buckets=(0.05, 0.1, 0.2, 0.5, 1, 2, 5, 10, 20),
)

ai_inference_tokens_total = Counter(
    "ai_inference_tokens_total",
    "Total input and output tokens processed by the runtime.",
    labelnames=("direction",),
)

ai_inference_cost_estimated_usd = Counter(
    "ai_inference_cost_estimated_usd",
    "Estimated inference spend in USD.",
)

ai_circuit_breaker_state = Gauge(
    "ai_circuit_breaker_state",
    "Circuit breaker state mapping 0=closed, 1=open, 2=half_open.",
)


STATE_MAP = {
    "closed": 0,
    "open": 1,
    "half_open": 2,
}


def observe_ttft(seconds: float) -> None:
    ai_inference_ttft_seconds.observe(seconds)


def observe_tokens(direction: str, count: int) -> None:
    ai_inference_tokens_total.labels(direction=direction).inc(count)


def observe_cost(cost_usd: float) -> None:
    ai_inference_cost_estimated_usd.inc(cost_usd)


def set_circuit_breaker_state(state: str) -> None:
    ai_circuit_breaker_state.set(STATE_MAP.get(state, 0))


def render_metrics() -> bytes:
    return generate_latest()

