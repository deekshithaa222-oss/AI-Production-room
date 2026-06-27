import asyncio
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode
from urllib.request import urlopen

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
        summary="Creating source-backed investigation plan.",
        findings=["Agents will collect evidence from configured files, Prometheus, PostgreSQL, and kubectl when available."],
    )
    investigation.progress = 8
    await asyncio.sleep(0.2)

    investigation.agents[0] = AgentResult(
        name="Planner",
        status=AgentState.complete,
        summary="Investigation plan created.",
        findings=[
            "Deployment agent reads previous/current configuration files.",
            "Metrics agent queries Prometheus when PROMETHEUS_URL is configured.",
            "Logs agent reads APP_LOG_PATH or kubectl logs.",
            "Database agent runs read-only PostgreSQL checks through psql when DATABASE_URL is configured.",
            "Kubernetes agent runs read-only kubectl checks when kubectl is available.",
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
    mark_running(investigation_id, "Deployment", "Reading deployment configuration sources.")
    return await asyncio.to_thread(collect_deployment_evidence)


async def metrics_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Metrics", "Querying Prometheus metrics when configured.")
    return await asyncio.to_thread(collect_metrics_evidence)


async def logs_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Logs", "Reading application logs from file or kubectl.")
    return await asyncio.to_thread(collect_log_evidence)


async def database_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Database", "Running read-only PostgreSQL diagnostics when configured.")
    return await asyncio.to_thread(collect_database_evidence)


async def kubernetes_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Kubernetes", "Running read-only kubectl diagnostics when available.")
    return await asyncio.to_thread(collect_kubernetes_evidence)


def collect_deployment_evidence() -> AgentResult:
    previous_path = os.getenv("DEPLOYMENT_PREVIOUS_CONFIG_PATH")
    current_path = os.getenv("DEPLOYMENT_CURRENT_CONFIG_PATH")
    previous = read_config_file(previous_path)
    current = read_config_file(current_path)
    findings: List[str] = []
    evidence: Dict[str, Any] = {
        "source": {
            "previous_config": previous_path,
            "current_config": current_path,
        }
    }

    if not previous_path or not current_path:
        return unavailable_agent(
            "Deployment",
            "Deployment config evidence was not collected.",
            "Set DEPLOYMENT_PREVIOUS_CONFIG_PATH and DEPLOYMENT_CURRENT_CONFIG_PATH to compare real deployment configuration.",
            evidence,
        )

    if previous is None or current is None:
        return unavailable_agent(
            "Deployment",
            "Deployment config evidence was not collected.",
            "One or both deployment config files could not be read as JSON or KEY=VALUE text.",
            evidence,
        )

    before = parse_int(previous.get("DB_POOL_SIZE"))
    after = parse_int(current.get("DB_POOL_SIZE"))
    evidence.update(
        {
            "db_pool_size_before": before,
            "db_pool_size_after": after,
            "db_pool_size_changed": before is not None and after is not None and before != after,
            "db_pool_size_decreased": before is not None and after is not None and after < before,
        }
    )

    if evidence["db_pool_size_changed"]:
        findings.append(f"DB_POOL_SIZE changed from {before} to {after}.")
    else:
        findings.append("No DB_POOL_SIZE change was found in the configured deployment files.")

    return AgentResult(
        name="Deployment",
        status=AgentState.complete,
        summary="Deployment evidence collected from configured files.",
        findings=findings,
        evidence=evidence,
    )


def collect_metrics_evidence() -> AgentResult:
    prometheus_url = os.getenv("PROMETHEUS_URL")
    evidence: Dict[str, Any] = {"source": {"prometheus_url": prometheus_url}}
    if not prometheus_url:
        return unavailable_agent(
            "Metrics",
            "Prometheus evidence was not collected.",
            "Set PROMETHEUS_URL to query live metrics.",
            evidence,
        )

    queries = {
        "p95_latency_ms": os.getenv("PROMETHEUS_LATENCY_QUERY", "histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m])) * 1000"),
        "error_rate_pct": os.getenv("PROMETHEUS_ERROR_RATE_QUERY", "sum(rate(http_requests_total{status=~\"5..\"}[5m])) / sum(rate(http_requests_total[5m])) * 100"),
        "cpu_usage_pct": os.getenv("PROMETHEUS_CPU_QUERY", "avg(rate(process_cpu_seconds_total[5m])) * 100"),
        "memory_usage_bytes": os.getenv("PROMETHEUS_MEMORY_QUERY", "process_resident_memory_bytes"),
    }

    findings: List[str] = []
    for key, query in queries.items():
        value = prometheus_query(prometheus_url, query)
        evidence[key] = value
        if value is not None:
            findings.append(f"{key} is {round(value, 2)}.")

    evidence["latency_spike"] = evidence.get("p95_latency_ms") is not None and evidence["p95_latency_ms"] >= 1000
    evidence["error_rate_spike"] = evidence.get("error_rate_pct") is not None and evidence["error_rate_pct"] >= 5
    evidence["cpu_normal"] = evidence.get("cpu_usage_pct") is not None and evidence["cpu_usage_pct"] < 80

    return AgentResult(
        name="Metrics",
        status=AgentState.complete,
        summary="Prometheus evidence collected." if findings else "Prometheus returned no metric samples.",
        findings=findings or ["Prometheus queries completed, but no numeric samples were returned."],
        evidence=evidence,
    )


def collect_log_evidence() -> AgentResult:
    log_path = os.getenv("APP_LOG_PATH")
    namespace = os.getenv("KUBE_NAMESPACE", "default")
    selector = os.getenv("KUBE_SELECTOR", "app=checkout-api")
    evidence: Dict[str, Any] = {"source": {"app_log_path": log_path, "namespace": namespace, "selector": selector}}

    logs: Optional[str] = None
    if log_path:
        path = Path(log_path)
        if path.exists():
            logs = path.read_text(errors="replace")
            evidence["source"]["mode"] = "file"
    elif shutil.which("kubectl"):
        command = ["kubectl", "logs", "-n", namespace, "-l", selector, "--tail=500"]
        completed = run_command(command)
        if completed["ok"]:
            logs = completed["stdout"]
            evidence["source"]["mode"] = "kubectl"
        else:
            evidence["kubectl_error"] = completed["stderr"]

    if logs is None:
        return unavailable_agent(
            "Logs",
            "Application log evidence was not collected.",
            "Set APP_LOG_PATH or configure kubectl access to read pod logs.",
            evidence,
        )

    timeout_matches = count_matches(logs, [r"timeout.*connection", r"connection.*timeout", r"acquir.*connection"])
    stack_traces = count_matches(logs, [r"Traceback", r"Exception", r"ERROR"])
    evidence.update(
        {
            "lines_scanned": len(logs.splitlines()),
            "connection_timeout_logs": timeout_matches > 0,
            "connection_timeout_count": timeout_matches,
            "stack_trace_present": stack_traces > 0,
            "error_count": stack_traces,
        }
    )

    findings = [
        f"Scanned {evidence['lines_scanned']} log lines.",
        f"Found {timeout_matches} connection-timeout log matches.",
        f"Found {stack_traces} error or stack-trace markers.",
    ]
    return AgentResult(name="Logs", status=AgentState.complete, summary="Application log evidence collected.", findings=findings, evidence=evidence)


def collect_database_evidence() -> AgentResult:
    database_url = os.getenv("DATABASE_URL")
    evidence: Dict[str, Any] = {"source": {"database_url_configured": bool(database_url), "client": "psql"}}
    if not database_url:
        return unavailable_agent(
            "Database",
            "PostgreSQL evidence was not collected.",
            "Set DATABASE_URL to run read-only pg_stat_activity and pg_stat_database checks.",
            evidence,
        )

    if not shutil.which("psql"):
        return unavailable_agent(
            "Database",
            "PostgreSQL evidence was not collected.",
            "The psql command is not installed or not available on PATH.",
            evidence,
        )

    active = psql_scalar(database_url, "select count(*) from pg_stat_activity where state = 'active';")
    waiting = psql_scalar(database_url, "select count(*) from pg_stat_activity where wait_event is not null;")
    deadlocks = psql_scalar(database_url, "select coalesce(sum(deadlocks), 0) from pg_stat_database;")
    current_config = read_config_file(os.getenv("DEPLOYMENT_CURRENT_CONFIG_PATH"))
    pool_size = parse_int((current_config or {}).get("DB_POOL_SIZE"))
    pool_saturation_pct = None
    if active is not None and pool_size and pool_size > 0:
        pool_saturation_pct = round((active / pool_size) * 100, 2)

    evidence.update(
        {
            "active_connections": active,
            "waiting_queries": waiting,
            "deadlocks": deadlocks,
            "configured_pool_size": pool_size,
            "pool_saturation_pct": pool_saturation_pct,
        }
    )

    findings = []
    if active is not None:
        findings.append(f"Active PostgreSQL connections: {active}.")
    if waiting is not None:
        findings.append(f"Sessions with wait events: {waiting}.")
    if deadlocks is not None:
        findings.append(f"Total database deadlocks: {deadlocks}.")
    if pool_saturation_pct is not None:
        findings.append(f"Estimated pool saturation from active connections and DB_POOL_SIZE: {pool_saturation_pct}%.")

    return AgentResult(
        name="Database",
        status=AgentState.complete,
        summary="PostgreSQL evidence collected." if findings else "PostgreSQL checks returned no usable values.",
        findings=findings or ["psql ran, but no numeric diagnostics were collected."],
        evidence=evidence,
    )


def collect_kubernetes_evidence() -> AgentResult:
    namespace = os.getenv("KUBE_NAMESPACE", "default")
    selector = os.getenv("KUBE_SELECTOR", "app=checkout-api")
    evidence: Dict[str, Any] = {"source": {"namespace": namespace, "selector": selector}}
    if not shutil.which("kubectl"):
        return unavailable_agent(
            "Kubernetes",
            "Kubernetes evidence was not collected.",
            "Install kubectl and configure cluster access to collect pod status and events.",
            evidence,
        )

    pods = run_command(["kubectl", "get", "pods", "-n", namespace, "-l", selector, "-o", "json"])
    if not pods["ok"]:
        evidence["kubectl_error"] = pods["stderr"]
        return unavailable_agent("Kubernetes", "Kubernetes evidence was not collected.", "kubectl could not read pods for the configured selector.", evidence)

    payload = json.loads(pods["stdout"])
    items = payload.get("items", [])
    restart_count = 0
    ready_count = 0
    crash_loop = False
    oom_killed = False

    for pod in items:
        statuses = pod.get("status", {}).get("containerStatuses", [])
        if all(status.get("ready") for status in statuses) and statuses:
            ready_count += 1
        for status in statuses:
            restart_count += int(status.get("restartCount", 0))
            waiting = status.get("state", {}).get("waiting", {})
            terminated = status.get("lastState", {}).get("terminated", {})
            crash_loop = crash_loop or waiting.get("reason") == "CrashLoopBackOff"
            oom_killed = oom_killed or terminated.get("reason") == "OOMKilled"

    evidence.update(
        {
            "pod_count": len(items),
            "ready_pods": ready_count,
            "pods_ready": len(items) > 0 and ready_count == len(items),
            "restart_count": restart_count,
            "restart_spike": restart_count > 0,
            "crash_loop": crash_loop,
            "oom_killed": oom_killed,
        }
    )

    findings = [
        f"Found {len(items)} pods for selector {selector}.",
        f"{ready_count} pods are ready.",
        f"Total restart count is {restart_count}.",
    ]
    if crash_loop:
        findings.append("At least one pod is in CrashLoopBackOff.")
    if oom_killed:
        findings.append("At least one pod has an OOMKilled termination.")

    return AgentResult(name="Kubernetes", status=AgentState.complete, summary="Kubernetes evidence collected.", findings=findings, evidence=evidence)


def unavailable_agent(name: str, summary: str, finding: str, evidence: Dict[str, Any]) -> AgentResult:
    evidence["available"] = False
    return AgentResult(name=name, status=AgentState.complete, summary=summary, findings=[finding], evidence=evidence)


def read_config_file(path_value: Optional[str]) -> Optional[Dict[str, Any]]:
    if not path_value:
        return None
    path = Path(path_value)
    if not path.exists():
        return None
    raw = path.read_text()
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        values: Dict[str, Any] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values


def prometheus_query(base_url: str, query: str) -> Optional[float]:
    url = base_url.rstrip("/") + "/api/v1/query?" + urlencode({"query": query})
    try:
        with urlopen(url, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception:
        return None

    result = payload.get("data", {}).get("result", [])
    if not result:
        return None
    value = result[0].get("value", [])
    if len(value) < 2:
        return None
    return parse_float(value[1])


def psql_scalar(database_url: str, sql: str) -> Optional[float]:
    completed = run_command(["psql", database_url, "-tAc", sql])
    if not completed["ok"]:
        return None
    return parse_float(completed["stdout"].strip())


def run_command(command: List[str]) -> Dict[str, Any]:
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
    except Exception as exc:
        return {"ok": False, "stdout": "", "stderr": str(exc)}
    return {"ok": completed.returncode == 0, "stdout": completed.stdout, "stderr": completed.stderr}


def count_matches(text: str, patterns: List[str]) -> int:
    return sum(len(re.findall(pattern, text, flags=re.IGNORECASE)) for pattern in patterns)


def parse_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(float(str(value)))
    except ValueError:
        return None


def parse_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(str(value))
    except ValueError:
        return None


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
    return {agent.name.lower(): agent.evidence for agent in agents}


def score_root_causes(evidence: Dict[str, Any]) -> List[RootCauseScore]:
    deployment = evidence.get("deployment", {})
    metrics = evidence.get("metrics", {})
    logs = evidence.get("logs", {})
    database = evidence.get("database", {})
    kubernetes = evidence.get("kubernetes", {})

    db_score = 0
    db_reasons: List[str] = []

    saturation = database.get("pool_saturation_pct")
    if saturation is not None and saturation >= 90:
        db_score += 40
        db_reasons.append(f"Estimated database pool saturation is {saturation}%.")
    if logs.get("connection_timeout_logs"):
        db_score += 25
        db_reasons.append(f"Logs contain {logs.get('connection_timeout_count', 0)} connection-timeout matches.")
    if deployment.get("db_pool_size_decreased"):
        db_score += 20
        db_reasons.append(f"DB_POOL_SIZE decreased from {deployment.get('db_pool_size_before')} to {deployment.get('db_pool_size_after')}.")
    if metrics.get("latency_spike") and metrics.get("error_rate_spike"):
        db_score += 10
        db_reasons.append("Prometheus shows both latency and error-rate symptoms.")
    if kubernetes.get("pods_ready") and not kubernetes.get("restart_spike"):
        db_score += 5
        db_reasons.append("Kubernetes pods are ready with no restart spike.")

    app_score = 0
    app_reasons: List[str] = []
    if logs.get("stack_trace_present"):
        app_score += 15
        app_reasons.append(f"Logs contain {logs.get('error_count', 0)} error or stack-trace markers.")
    if not app_reasons:
        app_reasons.append("No source-backed application-bug evidence was collected.")

    network_score = 0
    network_reasons = ["No source-backed network evidence was collected."]
    if metrics.get("error_rate_spike") and not logs.get("connection_timeout_logs"):
        network_score += 5
        network_reasons = ["Error rate is elevated, but logs did not identify database connection timeouts."]

    kube_score = 0
    kube_reasons: List[str] = []
    if kubernetes.get("crash_loop"):
        kube_score += 35
        kube_reasons.append("At least one pod is in CrashLoopBackOff.")
    if kubernetes.get("oom_killed"):
        kube_score += 30
        kube_reasons.append("At least one pod has an OOMKilled termination.")
    if kubernetes.get("restart_spike"):
        kube_score += 15
        kube_reasons.append("Pod restart count is above zero.")
    if not kube_reasons:
        kube_reasons.append("No source-backed Kubernetes failure evidence was collected.")

    return sorted(
        [
            RootCauseScore(hypothesis="Database connection pool exhaustion", score=db_score, reasons=db_reasons or ["No source-backed database-pool evidence was collected."]),
            RootCauseScore(hypothesis="Application bug", score=app_score, reasons=app_reasons),
            RootCauseScore(hypothesis="Network issue", score=network_score, reasons=network_reasons),
            RootCauseScore(hypothesis="Kubernetes capacity issue", score=kube_score, reasons=kube_reasons),
        ],
        key=lambda item: item.score,
        reverse=True,
    )


def generate_report(evidence: Dict[str, Any], scores: List[RootCauseScore]) -> IncidentReport:
    top = max(scores, key=lambda item: item.score)
    collected_evidence = build_report_evidence(evidence)

    if top.score == 0:
        return IncidentReport(
            summary="The investigation completed, but no configured data source provided enough evidence to identify a root cause.",
            root_cause="Insufficient evidence. Configure real sources before relying on a diagnosis.",
            evidence=collected_evidence or ["No source-backed evidence was collected."],
            immediate_actions=[
                "Configure DEPLOYMENT_PREVIOUS_CONFIG_PATH and DEPLOYMENT_CURRENT_CONFIG_PATH.",
                "Set APP_LOG_PATH or configure kubectl log access.",
                "Set DATABASE_URL for read-only PostgreSQL diagnostics.",
                "Set PROMETHEUS_URL for live metric queries.",
            ],
            long_term_recommendations=[
                "Connect SentinelAI to production read-only observability sources.",
                "Keep remediation human-approved until evidence coverage is complete.",
            ],
        )

    return IncidentReport(
        summary="SentinelAI completed a source-backed investigation using the configured data sources.",
        root_cause=f"Most likely root cause: {top.hypothesis} with score {top.score}.",
        evidence=collected_evidence,
        immediate_actions=build_immediate_actions(top, evidence),
        long_term_recommendations=[
            "Add alerts for the strongest evidence signals found in this investigation.",
            "Add deployment validation for risky database connection-pool changes.",
            "Keep remediation read-only until an engineer approves the recommended action.",
        ],
    )


def build_report_evidence(evidence: Dict[str, Any]) -> List[str]:
    items: List[str] = []
    deployment = evidence.get("deployment", {})
    database = evidence.get("database", {})
    logs = evidence.get("logs", {})
    metrics = evidence.get("metrics", {})
    kubernetes = evidence.get("kubernetes", {})

    if deployment.get("db_pool_size_changed"):
        items.append(f"Deployment config shows DB_POOL_SIZE changed from {deployment.get('db_pool_size_before')} to {deployment.get('db_pool_size_after')}.")
    if database.get("pool_saturation_pct") is not None:
        items.append(f"PostgreSQL diagnostics estimate pool saturation at {database.get('pool_saturation_pct')}%.")
    if database.get("waiting_queries") is not None:
        items.append(f"PostgreSQL reports {database.get('waiting_queries')} sessions with wait events.")
    if logs.get("connection_timeout_logs"):
        items.append(f"Application logs contain {logs.get('connection_timeout_count')} connection-timeout matches.")
    if metrics.get("p95_latency_ms") is not None:
        items.append(f"Prometheus p95 latency query returned {round(metrics.get('p95_latency_ms'), 2)} ms.")
    if metrics.get("error_rate_pct") is not None:
        items.append(f"Prometheus error-rate query returned {round(metrics.get('error_rate_pct'), 2)}%.")
    if kubernetes.get("pod_count") is not None:
        items.append(f"Kubernetes reports {kubernetes.get('ready_pods')} of {kubernetes.get('pod_count')} pods ready.")
    return items


def build_immediate_actions(top: RootCauseScore, evidence: Dict[str, Any]) -> List[str]:
    if top.hypothesis == "Database connection pool exhaustion":
        return [
            "Review the DB_POOL_SIZE deployment change before rollback or redeploy.",
            "Restore DB_POOL_SIZE only after an engineer confirms the collected evidence.",
            "Watch database wait events, latency, and HTTP 500 rate after the approved change.",
        ]
    if top.hypothesis == "Kubernetes capacity issue":
        return [
            "Inspect unhealthy pods and recent Kubernetes events.",
            "Restart or scale only after an engineer approves the remediation.",
        ]
    return [
        "Review the collected evidence with the owning engineering team.",
        "Do not execute remediation automatically; require human approval.",
    ]
