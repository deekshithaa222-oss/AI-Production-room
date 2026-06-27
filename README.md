# SentinelAI - AI Production War Room

SentinelAI is a demo incident command platform for investigating production failures with specialized AI-style agents. It coordinates deployment, metrics, logs, SQL/NoSQL databases, DNS, networking, storage, security, Kubernetes, cloud, DevSecOps, and serverless investigations, merges their evidence, surfaces investigation leads, and presents a human-reviewed remediation report.

The backend does not invent incident findings. Agents collect from configured sources. If a source is missing, the agent reports that evidence was not collected instead of returning fake data.

## What This Demo Shows

- A FastAPI backend with `/health`, `/investigate`, and `/investigation/{id}` APIs
- A LangGraph `StateGraph` workflow for planner, agent execution, evidence collection, lead assessment, and report generation
- Uncertainty-first investigation leads instead of predefined root-cause point rules
- A React + TypeScript + Tailwind dashboard with live agent status, evidence, scores, and approval controls
- Full infrastructure sweep that launches every specialist agent for each incident
- Source-backed collectors for deployment config files, application logs, Prometheus, PostgreSQL, Redis, DNS, TCP/UDP networking, storage, TLS/RBAC security, Kubernetes, cloud, DevSecOps, and serverless metadata

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
- `GET /investigation/{id}` - returns investigation status, evidence, scores, and report

Example:

```bash
curl -X POST http://localhost:8000/investigate \
  -H "Content-Type: application/json" \
  -d '{"description":"Checkout API is timing out and returning HTTP 500 errors."}'
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

The planner launches every specialist agent for a full infrastructure sweep. The agent runner executes collectors concurrently. The remaining nodes merge evidence, surface source-backed investigation leads, and generate a report that stays unconfirmed until an engineer validates the cause.

## Evidence Sources

Configure any of these environment variables before starting the backend:

```bash
export DEPLOYMENT_PREVIOUS_CONFIG_PATH=/path/to/previous.env
export DEPLOYMENT_CURRENT_CONFIG_PATH=/path/to/current.env
export APP_LOG_PATH=/path/to/application.log
export DATABASE_URL=postgresql://user:password@localhost:5432/app
export REDIS_URL=redis://localhost:6379
export PROMETHEUS_URL=http://localhost:9090
export DNS_HOST=checkout.example.com
export NETWORK_TARGET_HOST=postgres.internal
export NETWORK_TARGET_PORT=5432
export NETWORK_UDP_HOST=8.8.8.8
export NETWORK_UDP_PORT=53
export STORAGE_PATH=/var/lib/app
export TLS_HOST=checkout.example.com
export KUBE_NAMESPACE=default
export KUBE_SELECTOR=app=checkout-api
export AWS_REGION=us-east-1
export CONTAINER_IMAGE_TAG=checkout-api:latest
export SECURITY_SCAN_PATH=/path/to/security-scan.json
export SERVERLESS_FUNCTION_NAME=checkout-worker
```

Deployment config files can be JSON or `KEY=VALUE` text. For example:

```bash
DB_POOL_SIZE=10
```

The database agent uses the local `psql` command for read-only PostgreSQL checks. Redis uses `redis-cli`. Kubernetes, storage, and security checks use `kubectl` when available. Cloud and serverless checks use configured environment variables and optional cloud CLIs such as `aws`. If these tools or environment variables are absent, SentinelAI reports missing evidence instead of fabricating findings.

Every investigation runs the full specialist-agent set. If a source is missing, that agent reports missing evidence instead of fabricating findings.
