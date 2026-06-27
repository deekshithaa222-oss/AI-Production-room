# SentinelAI - AI Production War Room

SentinelAI is a demo incident command platform for investigating production failures with specialized AI-style agents. It coordinates deployment, metrics, logs, database, and Kubernetes investigations, merges their evidence, scores likely root causes deterministically, and presents a human-approved remediation report.

The backend does not invent incident findings. Agents collect from configured sources. If a source is missing, the agent reports that evidence was not collected instead of returning fake data.

## What This Demo Shows

- A FastAPI backend with `/health`, `/investigate`, and `/investigation/{id}` APIs
- A LangGraph-style parallel investigation workflow
- Deterministic root-cause scoring instead of LLM-only diagnosis
- A React + TypeScript + Tailwind dashboard with live agent status, evidence, scores, and approval controls
- Source-backed collectors for deployment config files, application logs, Prometheus, PostgreSQL, and Kubernetes

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

## Evidence Sources

Configure any of these environment variables before starting the backend:

```bash
export DEPLOYMENT_PREVIOUS_CONFIG_PATH=/path/to/previous.env
export DEPLOYMENT_CURRENT_CONFIG_PATH=/path/to/current.env
export APP_LOG_PATH=/path/to/application.log
export DATABASE_URL=postgresql://user:password@localhost:5432/app
export PROMETHEUS_URL=http://localhost:9090
export KUBE_NAMESPACE=default
export KUBE_SELECTOR=app=checkout-api
```

Deployment config files can be JSON or `KEY=VALUE` text. For example:

```bash
DB_POOL_SIZE=10
```

The database agent uses the local `psql` command for read-only PostgreSQL checks. The Kubernetes agent uses the local `kubectl` command. If these tools or environment variables are absent, SentinelAI reports missing evidence instead of fabricating findings.
