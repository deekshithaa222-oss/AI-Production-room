# SentinelAI - AI Infrastructure War Room

SentinelAI is a demo infrastructure incident command platform for investigating production failures with specialized AI-style agents. It coordinates deployment, observability, SQL/NoSQL databases, payment services, DNS, TCP/UDP networking, storage, security, Kubernetes, cloud, DevSecOps, and serverless investigations, merges their evidence, surfaces investigation leads, and presents a human-reviewed remediation report.

The backend does not invent incident findings. Agents collect from configured sources. If a source is missing, the agent reports that evidence was not collected instead of returning fake data.

## What This Demo Shows

- A FastAPI backend with `/health`, `/investigate`, and `/investigation/{id}` APIs
- A LangGraph `StateGraph` workflow for planner, agent execution, evidence collection, lead assessment, and report generation
- Planner-based routing that selects specialist agents from the incident description and configured evidence sources
- Uncertainty-first investigation leads instead of predefined root-cause point rules
- A React + TypeScript + Tailwind dashboard with live agent status, evidence, investigation leads, and approval controls
- Source-backed collectors for deployment config files, service logs, Prometheus, PostgreSQL, payment health/logs, Redis, DNS, TCP/UDP networking, storage, TLS/RBAC security, Kubernetes, cloud, DevSecOps, and serverless metadata

For presentation Q&A prep, see [PRESENTATION_DEFENSE.md](./PRESENTATION_DEFENSE.md).

## Run Locally

Backend:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Open the Vite URL shown in the terminal, usually `http://localhost:5173`.

## API

- `GET /health` - backend health
- `POST /investigate` - starts a new incident investigation
- `GET /investigation/{id}` - returns investigation status, evidence, investigation leads, and report

Example:

```bash
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"description":"Production ingress latency increased after a Kubernetes deployment; database port 5432 intermittently times out."}'
```

## LangGraph Flow

The backend uses LangGraph to run the investigation workflow:

```text
START
  -> planner
  -> agent_runner
  -> evidence_collector
  -> lead_assessor
  -> report_generator
  -> END
```

The planner selects likely specialist agents from the incident description and any configured evidence sources. The agent runner executes the selected collectors concurrently. The remaining nodes merge evidence, surface source-backed investigation leads, and generate a report that stays unconfirmed until an engineer validates the cause.

## Evidence Sources

Configure any of these environment variables before starting the backend:

```bash
export DEPLOYMENT_PREVIOUS_CONFIG_PATH=/path/to/previous.env
export DEPLOYMENT_CURRENT_CONFIG_PATH=/path/to/current.env
export APP_LOG_PATH=/path/to/service.log
export DATABASE_URL=postgresql://user:password@localhost:5432/platform
export PAYMENT_HEALTH_URL=https://payments.example.com/health
export PAYMENT_LOG_PATH=/path/to/payment-service.log
export PAYMENT_LATENCY_THRESHOLD_MS=1000
export REDIS_URL=redis://localhost:6379
export PROMETHEUS_URL=http://localhost:9090
export DNS_HOST=api.example.com
export NETWORK_TARGET_HOST=postgres.platform.internal
export NETWORK_TARGET_PORT=5432
export NETWORK_UDP_HOST=8.8.8.8
export NETWORK_UDP_PORT=53
export STORAGE_PATH=/var/lib/platform
export TLS_HOST=api.example.com
export KUBE_NAMESPACE=default
export KUBE_SELECTOR=app=target-service
export AWS_REGION=us-east-1
export CONTAINER_IMAGE_TAG=target-service:latest
export SECURITY_SCAN_PATH=/path/to/security-scan.json
export SERVERLESS_FUNCTION_NAME=infra-worker
```

Deployment config files can be JSON or `KEY=VALUE` text. For example:

```bash
DATABASE_POOL_SIZE=10
```

The database agent uses the local `psql` command for read-only PostgreSQL checks. Redis uses `redis-cli`. Kubernetes, storage, and security checks use `kubectl` when available. Cloud and serverless checks use configured environment variables and optional cloud CLIs such as `aws`. If these tools or environment variables are absent, SentinelAI reports missing evidence instead of fabricating findings.

The planner can route directly to relevant specialists, such as logs, metrics, database, network, Kubernetes, and payment checks for a checkout-latency incident. If a selected source is missing, that agent reports missing evidence instead of fabricating findings.
