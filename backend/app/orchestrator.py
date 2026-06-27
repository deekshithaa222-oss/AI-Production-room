import asyncio
import uuid
from typing import Any, Dict, List

from .models import (
    AgentResult,
    AgentState,
    IncidentReport,
    Investigation,
    InvestigationState,
    RootCauseScore,
)


AGENT_NAMES = ["Planner", "Deployment", "Metrics", "Logs", "Database", "Kubernetes"]
investigations: Dict[str, Investigation] = {}


def create_investigation(description: str) -> Investigation:
    investigation = Investigation(
        id=str(uuid.uuid4()),
        description=description,
        status=InvestigationState.queued,
        progress=0,
        agents=[AgentResult(name=name) for name in AGENT_NAMES],
    )
    investigations[investigation.id] = investigation
    asyncio.create_task(run_investigation(investigation.id))
    return investigation


async def run_investigation(investigation_id: str) -> None:
    investigation = investigations[investigation_id]
    investigation.status = InvestigationState.running
    investigation.agents[0] = AgentResult(
        name="Planner",
        status=AgentState.running,
        summary="Creating investigation plan.",
        findings=["Incident touches application latency, database connectivity, deployments, and infrastructure."],
    )
    investigation.progress = 8
    await asyncio.sleep(0.8)

    investigation.agents[0] = AgentResult(
        name="Planner",
        status=AgentState.complete,
        summary="Parallel investigation plan created.",
        findings=[
            "Launch deployment, metrics, logs, database, and Kubernetes agents.",
            "Correlate findings against the reported Checkout API timeout window.",
        ],
        evidence={"plan": ["deployment", "metrics", "logs", "database", "kubernetes"]},
    )
    investigation.progress = 18

    results = await asyncio.gather(
        deployment_agent(investigation_id),
        metrics_agent(investigation_id),
        logs_agent(investigation_id),
        database_agent(investigation_id),
        kubernetes_agent(investigation_id),
    )

    for result in results:
        set_agent_result(investigation, result)

    investigation.evidence = collect_evidence(investigation.agents)
    investigation.scores = score_root_causes(investigation.evidence)
    investigation.report = generate_report(investigation.evidence, investigation.scores)
    investigation.status = InvestigationState.complete
    investigation.progress = 100


async def deployment_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Deployment", "Checking rollout history and configuration diffs.")
    await asyncio.sleep(1.6)
    return AgentResult(
        name="Deployment",
        status=AgentState.complete,
        summary="Recent deployment changed the database connection pool size.",
        findings=[
            "Checkout API deployment completed 8 minutes before the first timeout spike.",
            "Configuration diff shows DB_POOL_SIZE changed from 10 to 2.",
            "No application image rollback has occurred yet.",
        ],
        evidence={"recent_deployment": True, "db_pool_size_before": 10, "db_pool_size_after": 2, "minutes_before_incident": 8},
    )


async def metrics_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Metrics", "Reading Prometheus-style application metrics.")
    await asyncio.sleep(2.0)
    return AgentResult(
        name="Metrics",
        status=AgentState.complete,
        summary="Latency and error rate increased while CPU and memory stayed normal.",
        findings=[
            "p95 latency rose from 180ms to 4.8s.",
            "HTTP 500 rate increased to 18%.",
            "CPU remains at 46% and memory remains at 61%.",
        ],
        evidence={"latency_spike": True, "error_rate_spike": True, "cpu_normal": True, "memory_normal": True, "p95_latency_ms": 4800, "error_rate_pct": 18},
    )


async def logs_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Logs", "Scanning application pod logs for timeout signatures.")
    await asyncio.sleep(1.9)
    return AgentResult(
        name="Logs",
        status=AgentState.complete,
        summary="Application logs show PostgreSQL connection acquisition timeouts.",
        findings=[
            "Repeated timeout while acquiring PostgreSQL connection from pool.",
            "Stack traces originate from checkout payment authorization path.",
            "No new uncaught application exception type detected.",
        ],
        evidence={"connection_timeout_logs": True, "stack_trace_present": True, "new_exception_type": False},
    )


async def database_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Database", "Checking PostgreSQL activity, pool usage, locks, and replication.")
    await asyncio.sleep(2.4)
    return AgentResult(
        name="Database",
        status=AgentState.complete,
        summary="Database pool is saturated with waiting application requests.",
        findings=[
            "Connection pool usage is 97%.",
            "Waiting queries increased sharply after deployment.",
            "No deadlocks, lock pileup, or replication lag observed.",
        ],
        evidence={"pool_saturation_pct": 97, "waiting_queries": 42, "deadlocks": False, "replication_lag": False, "slow_queries_primary": False},
    )


async def kubernetes_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Kubernetes", "Verifying pod health, restarts, rollout status, and events.")
    await asyncio.sleep(1.4)
    return AgentResult(
        name="Kubernetes",
        status=AgentState.complete,
        summary="Kubernetes infrastructure is healthy and the rollout completed.",
        findings=[
            "Pods are Running and Ready.",
            "No CrashLoopBackOff, OOMKilled, or elevated restart count detected.",
            "Deployment rollout completed successfully.",
        ],
        evidence={"pods_ready": True, "crash_loop": False, "oom_killed": False, "restart_spike": False, "rollout_complete": True},
    )


def mark_running(investigation_id: str, agent_name: str, summary: str) -> None:
    investigation = investigations[investigation_id]
    for index, agent in enumerate(investigation.agents):
        if agent.name == agent_name:
            investigation.agents[index] = AgentResult(name=agent_name, status=AgentState.running, summary=summary)
            completed = len([item for item in investigation.agents if item.status == AgentState.complete])
            running = len([item for item in investigation.agents if item.status == AgentState.running])
            investigation.progress = min(92, 18 + completed * 12 + running * 4)
            break


def set_agent_result(investigation: Investigation, result: AgentResult) -> None:
    for index, agent in enumerate(investigation.agents):
        if agent.name == result.name:
            investigation.agents[index] = result
            break


def collect_evidence(agents: List[AgentResult]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for agent in agents:
        merged[agent.name.lower()] = agent.evidence
    return merged


def score_root_causes(evidence: Dict[str, Any]) -> List[RootCauseScore]:
    db_reasons: List[str] = []
    db_score = 0

    if evidence["database"].get("pool_saturation_pct", 0) >= 90:
        db_score += 40
        db_reasons.append("PostgreSQL connection pool usage reached 97%.")
    if evidence["logs"].get("connection_timeout_logs"):
        db_score += 25
        db_reasons.append("Application logs show connection acquisition timeouts.")
    if evidence["deployment"].get("recent_deployment") and evidence["deployment"].get("db_pool_size_after", 10) < evidence["deployment"].get("db_pool_size_before", 10):
        db_score += 20
        db_reasons.append("A recent deployment reduced DB_POOL_SIZE from 10 to 2.")
    if evidence["metrics"].get("cpu_normal") and evidence["metrics"].get("memory_normal"):
        db_score += 10
        db_reasons.append("CPU and memory are normal, making compute saturation unlikely.")
    if evidence["kubernetes"].get("pods_ready") and not evidence["kubernetes"].get("restart_spike"):
        db_score += 5
        db_reasons.append("Kubernetes pods are healthy with no restart spike.")

    return [
        RootCauseScore(hypothesis="Database connection pool exhaustion", score=db_score, reasons=db_reasons),
        RootCauseScore(hypothesis="Application bug", score=15, reasons=["Stack traces are present, but they point to database connection timeouts."]),
        RootCauseScore(hypothesis="Network issue", score=5, reasons=["No Kubernetes events or infrastructure symptoms indicate networking failure."]),
        RootCauseScore(hypothesis="Kubernetes capacity issue", score=3, reasons=["Pods are ready and no CrashLoopBackOff or OOMKilled events were found."]),
    ]


def generate_report(evidence: Dict[str, Any], scores: List[RootCauseScore]) -> IncidentReport:
    top = max(scores, key=lambda item: item.score)
    return IncidentReport(
        summary="Checkout API requests are timing out and returning HTTP 500 errors after a recent deployment.",
        root_cause=f"{top.hypothesis} caused by a deployment configuration change that reduced DB_POOL_SIZE from 10 to 2.",
        evidence=[
            "Deployment occurred 8 minutes before the incident and changed DB_POOL_SIZE from 10 to 2.",
            "Database pool saturation reached 97% with 42 waiting queries.",
            "Application logs repeatedly show PostgreSQL connection acquisition timeouts.",
            "Latency and HTTP 500s increased while CPU, memory, and Kubernetes health stayed normal.",
        ],
        immediate_actions=[
            "Roll back the Checkout API deployment or restore DB_POOL_SIZE to 10.",
            "Restart affected application pods after configuration correction.",
            "Watch pool usage, p95 latency, and HTTP 500 rate until they return to baseline.",
        ],
        long_term_recommendations=[
            "Add deployment validation for database pool configuration.",
            "Alert when connection pool utilization exceeds 80%.",
            "Load test checkout traffic against production-like pool settings.",
            "Require human approval before automated rollback execution.",
        ],
    )

