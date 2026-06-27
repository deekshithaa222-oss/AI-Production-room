# SentinelAI - AI Production War Room

SentinelAI is a demo incident command platform for investigating production failures with specialized AI-style agents. It coordinates deployment, metrics, logs, database, and Kubernetes investigations, merges their evidence, scores likely root causes deterministically, and presents a human-approved remediation report.

## What This Demo Shows

- A FastAPI backend with `/health`, `/investigate`, and `/investigation/{id}` APIs
- A simulated LangGraph-style parallel investigation workflow
- Deterministic root-cause scoring instead of LLM-only diagnosis
- A React + TypeScript + Tailwind dashboard with live agent status, evidence, scores, and approval controls
- The incident scenario where `DB_POOL_SIZE` changes from `10` to `2`, causing PostgreSQL connection pool exhaustion and HTTP 500s

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

