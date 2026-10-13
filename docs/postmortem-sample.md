# Postmortem Sample

## Incident Summary

A downstream model endpoint started returning 429 and 504 responses under load. The application did not fail in a controlled manner, and the upstream queue began to back up.

## Detection

Prometheus tracked a sharp increase in the response-time histogram and a falling success ratio. The circuit breaker transitioned to OPEN after repeated 5xx and timeout events.

## Mitigation

- Admission limits were enforced at the ingress layer.
- Requests were routed to a quantized fallback model.
- Automatic retries were delayed with exponential backoff and jitter.
- Tooling was isolated behind schema-bound MCP endpoints.

## Recovery

The service recovered within the configured 30-second cooldown period, after which the breaker re-entered HALF_OPEN and stabilized the route.

## Lessons Learned

- Concurrency must be capped before the model layer.
- Telemetry should be treated as the control plane for failure detection.
- Fallback paths must be deterministic and low-latency.
