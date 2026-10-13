# Architecture Notes

## Mission

The platform supports a resilient inference runtime that can absorb upstream model failures without dropping important requests. This is achieved through controlled admission, deterministic fault isolation, and graceful degradation to a fallback path.

## Runtime Flow

1. A request enters the ingress layer.
2. Admission control applies a token bucket and concurrency cap.
3. The orchestrator validates the prompt and routes it through the primary model endpoint.
4. If the model fails with a timeout or repeated 5xx rate-limited response, the circuit breaker opens.
5. Requests are routed to a lightweight fallback endpoint or cached response.
6. Telemetry records TTFT, token totals, cost, and breaker state.

## Circuit Breaker State Machine

```text
CLOSED --(failure threshold reached)--> OPEN
OPEN --(cooldown elapsed)--> HALF_OPEN
HALF_OPEN --(success)--> CLOSED
HALF_OPEN --(failure)--> OPEN
```

The policy uses exponential backoff with full jitter to avoid synchronized retries. This reduces thundering-herd behavior when model providers recover after an outage.

## Timeout Rules

- Primary endpoint timeout budget: 8 seconds.
- Fallback invocation occurs immediately after state transition to OPEN.
- Retry probes are sampled only after the cooldown window.
- Tool calls enforce a hard maximum iteration cap so the agent cannot loop indefinitely.

## MCP Guardrails

External tools are isolated behind a schema-bound interface. Tool arguments are validated before execution and rejected if malformed. This keeps tool calls deterministic and prevents invalid JSON or unexpected CLI arguments from destabilizing the runtime.

## Observability

Metrics include:

- `ai_inference_ttft_seconds`
- `ai_inference_tokens_total{direction="input|output"}`
- `ai_inference_cost_estimated_usd`
- `ai_circuit_breaker_state{status="closed|open|half_open"}`

These metrics are exported in Prometheus format and can be scraped by Grafana for SLO dashboards.
