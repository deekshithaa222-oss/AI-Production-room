import asyncio
import json
import os
import re
import shutil
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from .models import (
    AgentResult,
    AgentState,
    IncidentReport,
    Investigation,
    InvestigationState,
    RootCauseScore,
)


ALL_AGENT_NAMES = [
    "Planner",
    "Deployment",
    "Metrics",
    "Logs",
    "Database",
    "Redis",
    "DNS",
    "Network",
    "Storage",
    "Security",
    "Kubernetes",
    "Cloud",
    "DevSecOps",
    "Serverless",
]
investigations: Dict[str, Investigation] = {}


def create_investigation(description: str) -> Investigation:
    agent_names = plan_agent_names(description)
    investigation = Investigation(
        id=str(uuid.uuid4()),
        description=description,
        status=InvestigationState.queued,
        progress=0,
        agents=[AgentResult(name=name) for name in agent_names],
    )
    investigations[investigation.id] = investigation
    asyncio.create_task(run_investigation(investigation.id))
    return investigation


async def run_investigation(investigation_id: str) -> None:
    investigation = investigations[investigation_id]
    planned_agents = [agent.name for agent in investigation.agents if agent.name != "Planner"]
    investigation.status = InvestigationState.running
    investigation.agents[0] = AgentResult(
        name="Planner",
        status=AgentState.running,
        summary="Creating source-backed investigation plan.",
        findings=["Planner selected source-backed agents from the incident description and available investigation domains."],
    )
    investigation.progress = 8
    await asyncio.sleep(0.2)

    investigation.agents[0] = AgentResult(
        name="Planner",
        status=AgentState.complete,
        summary="Investigation plan created.",
        findings=[
            f"Selected agents: {', '.join(planned_agents)}.",
            "Each selected agent collects from configured tools, files, URLs, or environment context.",
            "Missing sources are reported as missing evidence rather than guessed findings.",
        ],
        evidence={"plan": [name.lower() for name in planned_agents]},
    )
    investigation.progress = 18

    results = await asyncio.gather(*(AGENT_RUNNERS[name](investigation_id) for name in planned_agents))

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


async def redis_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Redis", "Running read-only Redis diagnostics when configured.")
    return await asyncio.to_thread(collect_redis_evidence)


async def dns_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "DNS", "Running forward and reverse DNS lookups.")
    investigation = investigations[investigation_id]
    return await asyncio.to_thread(collect_dns_evidence, investigation.description)


async def network_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Network", "Checking TCP and optional UDP reachability.")
    investigation = investigations[investigation_id]
    return await asyncio.to_thread(collect_network_evidence, investigation.description)


async def storage_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Storage", "Checking filesystem and Kubernetes storage evidence.")
    return await asyncio.to_thread(collect_storage_evidence)


async def security_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Security", "Checking TLS, secrets, and Kubernetes RBAC evidence.")
    investigation = investigations[investigation_id]
    return await asyncio.to_thread(collect_security_evidence, investigation.description)


async def cloud_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Cloud", "Checking cloud CLI and runtime environment evidence.")
    return await asyncio.to_thread(collect_cloud_evidence)


async def devsecops_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "DevSecOps", "Checking git, CI/CD, image, and scan metadata.")
    return await asyncio.to_thread(collect_devsecops_evidence)


async def serverless_agent(investigation_id: str) -> AgentResult:
    mark_running(investigation_id, "Serverless", "Checking serverless runtime or function metadata.")
    return await asyncio.to_thread(collect_serverless_evidence)


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


def collect_redis_evidence() -> AgentResult:
    redis_url = os.getenv("REDIS_URL")
    evidence: Dict[str, Any] = {"source": {"redis_url_configured": bool(redis_url), "client": "redis-cli"}}
    if not redis_url:
        return unavailable_agent("Redis", "Redis evidence was not collected.", "Set REDIS_URL to run read-only Redis checks.", evidence)
    if not shutil.which("redis-cli"):
        return unavailable_agent("Redis", "Redis evidence was not collected.", "The redis-cli command is not installed or not available on PATH.", evidence)

    ping = run_command(["redis-cli", "-u", redis_url, "PING"])
    info = run_command(["redis-cli", "-u", redis_url, "INFO", "stats"])
    evidence["ping_ok"] = ping["ok"] and "PONG" in ping["stdout"]
    evidence["connected_clients"] = extract_redis_metric(info["stdout"], "connected_clients")
    evidence["keyspace_hits"] = extract_redis_metric(info["stdout"], "keyspace_hits")
    evidence["keyspace_misses"] = extract_redis_metric(info["stdout"], "keyspace_misses")
    hits = evidence.get("keyspace_hits") or 0
    misses = evidence.get("keyspace_misses") or 0
    evidence["cache_miss_rate_pct"] = round((misses / (hits + misses)) * 100, 2) if hits + misses > 0 else None

    findings = [f"Redis PING returned {'PONG' if evidence['ping_ok'] else 'no PONG'}."]
    if evidence["connected_clients"] is not None:
        findings.append(f"Redis connected clients: {evidence['connected_clients']}.")
    if evidence["cache_miss_rate_pct"] is not None:
        findings.append(f"Redis cache miss rate: {evidence['cache_miss_rate_pct']}%.")
    return AgentResult(name="Redis", status=AgentState.complete, summary="Redis evidence collected.", findings=findings, evidence=evidence)


def collect_dns_evidence(description: str) -> AgentResult:
    hostname = os.getenv("DNS_HOST") or extract_hostname(description)
    evidence: Dict[str, Any] = {"source": {"hostname": hostname, "resolver": "system"}}
    if not hostname:
        return unavailable_agent("DNS", "DNS evidence was not collected.", "Set DNS_HOST or include a hostname in the incident description.", evidence)

    try:
        addresses = sorted({item[4][0] for item in socket.getaddrinfo(hostname, None)})
    except socket.gaierror as exc:
        evidence.update({"forward_lookup_ok": False, "error": str(exc)})
        return AgentResult(name="DNS", status=AgentState.complete, summary="DNS forward lookup failed.", findings=[f"Forward lookup for {hostname} failed: {exc}."], evidence=evidence)

    reverse: Dict[str, Optional[str]] = {}
    for address in addresses[:5]:
        try:
            reverse[address] = socket.gethostbyaddr(address)[0]
        except socket.herror:
            reverse[address] = None

    evidence.update({"forward_lookup_ok": True, "addresses": addresses, "reverse_names": reverse, "reverse_lookup_complete": all(reverse.values())})
    findings = [f"Forward lookup for {hostname} returned {len(addresses)} address(es)."]
    if reverse:
        findings.append(f"Reverse lookup completed for {len([value for value in reverse.values() if value])} of {len(reverse)} sampled address(es).")
    return AgentResult(name="DNS", status=AgentState.complete, summary="DNS evidence collected.", findings=findings, evidence=evidence)


def collect_network_evidence(description: str) -> AgentResult:
    host, port = network_target(description)
    udp_host = os.getenv("NETWORK_UDP_HOST")
    udp_port = parse_int(os.getenv("NETWORK_UDP_PORT"))
    evidence: Dict[str, Any] = {"source": {"host": host, "port": port, "udp_host": udp_host, "udp_port": udp_port}}
    if not host or not port:
        return unavailable_agent("Network", "Network evidence was not collected.", "Set NETWORK_TARGET_HOST and NETWORK_TARGET_PORT, or configure DATABASE_URL/DNS_HOST.", evidence)

    tcp_ok = False
    tcp_error = None
    try:
        with socket.create_connection((host, port), timeout=4):
            tcp_ok = True
    except OSError as exc:
        tcp_error = str(exc)

    evidence.update({"tcp_connect_ok": tcp_ok, "tcp_error": tcp_error})
    findings = [f"TCP connection to {host}:{port} {'succeeded' if tcp_ok else 'failed'}."]
    if tcp_error:
        findings.append(f"TCP error: {tcp_error}.")

    if udp_host and udp_port:
        udp_ok, udp_error = udp_probe(udp_host, udp_port)
        evidence.update({"udp_probe_configured": True, "udp_probe_ok": udp_ok, "udp_error": udp_error})
        findings.append(f"UDP probe to {udp_host}:{udp_port} {'sent successfully' if udp_ok else 'failed to send'}.")
    else:
        evidence["udp_probe_configured"] = False
        findings.append("UDP probe was not configured.")

    return AgentResult(name="Network", status=AgentState.complete, summary="Network evidence collected.", findings=findings, evidence=evidence)


def collect_storage_evidence() -> AgentResult:
    storage_path = os.getenv("STORAGE_PATH")
    namespace = os.getenv("KUBE_NAMESPACE", "default")
    evidence: Dict[str, Any] = {"source": {"storage_path": storage_path, "namespace": namespace}}
    findings: List[str] = []

    if storage_path:
        path = Path(storage_path)
        if path.exists():
            stats = os.statvfs(path)
            total = stats.f_blocks * stats.f_frsize
            free = stats.f_bavail * stats.f_frsize
            used_pct = round(((total - free) / total) * 100, 2) if total else None
            evidence.update({"path_exists": True, "disk_total_bytes": total, "disk_free_bytes": free, "disk_used_pct": used_pct})
            findings.append(f"Filesystem usage for {storage_path}: {used_pct}%.")
        else:
            evidence["path_exists"] = False
            findings.append(f"STORAGE_PATH does not exist: {storage_path}.")

    if shutil.which("kubectl"):
        pvc = run_command(["kubectl", "get", "pvc", "-n", namespace, "-o", "json"])
        if pvc["ok"]:
            payload = json.loads(pvc["stdout"])
            items = payload.get("items", [])
            evidence["pvc_count"] = len(items)
            evidence["pvc_pending"] = len([item for item in items if item.get("status", {}).get("phase") != "Bound"])
            findings.append(f"Kubernetes reports {len(items)} PVC(s), {evidence['pvc_pending']} not Bound.")
        else:
            evidence["kubectl_pvc_error"] = pvc["stderr"]

    if not findings:
        return unavailable_agent("Storage", "Storage evidence was not collected.", "Set STORAGE_PATH or configure kubectl access to inspect PVC status.", evidence)
    return AgentResult(name="Storage", status=AgentState.complete, summary="Storage evidence collected.", findings=findings, evidence=evidence)


def collect_security_evidence(description: str) -> AgentResult:
    tls_host = os.getenv("TLS_HOST") or extract_hostname(description)
    namespace = os.getenv("KUBE_NAMESPACE", "default")
    evidence: Dict[str, Any] = {"source": {"tls_host": tls_host, "namespace": namespace}}
    findings: List[str] = []

    if tls_host:
        cert = tls_certificate_expiry(tls_host)
        evidence.update(cert)
        if cert.get("tls_days_remaining") is not None:
            findings.append(f"TLS certificate for {tls_host} expires in {cert['tls_days_remaining']} day(s).")
        elif cert.get("tls_error"):
            findings.append(f"TLS check for {tls_host} failed: {cert['tls_error']}.")

    if shutil.which("kubectl"):
        can_get_pods = run_command(["kubectl", "auth", "can-i", "get", "pods", "-n", namespace])
        can_get_secrets = run_command(["kubectl", "auth", "can-i", "get", "secrets", "-n", namespace])
        evidence["rbac_can_get_pods"] = can_get_pods["ok"] and can_get_pods["stdout"].strip() == "yes"
        evidence["rbac_can_get_secrets"] = can_get_secrets["ok"] and can_get_secrets["stdout"].strip() == "yes"
        findings.append(f"RBAC can get pods: {evidence['rbac_can_get_pods']}.")
        findings.append(f"RBAC can get secrets: {evidence['rbac_can_get_secrets']}.")

    if not findings:
        return unavailable_agent("Security", "Security evidence was not collected.", "Set TLS_HOST or configure kubectl access for RBAC checks.", evidence)
    return AgentResult(name="Security", status=AgentState.complete, summary="Security evidence collected.", findings=findings, evidence=evidence)


def collect_cloud_evidence() -> AgentResult:
    evidence: Dict[str, Any] = {
        "source": {
            "aws_region": os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION"),
            "gcp_project": os.getenv("GOOGLE_CLOUD_PROJECT"),
            "azure_client": bool(os.getenv("AZURE_CLIENT_ID")),
        }
    }
    findings: List[str] = []

    if evidence["source"]["aws_region"]:
        findings.append(f"AWS region configured: {evidence['source']['aws_region']}.")
    if evidence["source"]["gcp_project"]:
        findings.append(f"GCP project configured: {evidence['source']['gcp_project']}.")
    if evidence["source"]["azure_client"]:
        findings.append("Azure client environment variables are configured.")

    if shutil.which("aws"):
        identity = run_command(["aws", "sts", "get-caller-identity", "--output", "json"])
        evidence["aws_sts_ok"] = identity["ok"]
        if identity["ok"]:
            payload = json.loads(identity["stdout"])
            evidence["aws_account"] = payload.get("Account")
            findings.append("AWS STS caller identity is available.")
        else:
            evidence["aws_sts_error"] = identity["stderr"]

    if not findings:
        return unavailable_agent("Cloud", "Cloud evidence was not collected.", "Configure cloud environment variables or install/authenticate a cloud CLI such as aws.", evidence)
    return AgentResult(name="Cloud", status=AgentState.complete, summary="Cloud evidence collected.", findings=findings, evidence=evidence)


def collect_devsecops_evidence() -> AgentResult:
    evidence: Dict[str, Any] = {
        "source": {
            "github_run_id": os.getenv("GITHUB_RUN_ID"),
            "image_tag": os.getenv("CONTAINER_IMAGE_TAG"),
            "image_digest": os.getenv("CONTAINER_IMAGE_DIGEST"),
            "security_scan_path": os.getenv("SECURITY_SCAN_PATH"),
        }
    }
    findings: List[str] = []

    git_head = run_command(["git", "rev-parse", "--short", "HEAD"])
    git_dirty = run_command(["git", "status", "--short"])
    if git_head["ok"]:
        evidence["git_head"] = git_head["stdout"].strip()
        evidence["git_dirty"] = bool(git_dirty["stdout"].strip()) if git_dirty["ok"] else None
        findings.append(f"Current git commit: {evidence['git_head']}.")
        findings.append(f"Working tree has uncommitted changes: {evidence['git_dirty']}.")

    if evidence["source"]["github_run_id"]:
        findings.append(f"GitHub Actions run ID: {evidence['source']['github_run_id']}.")
    if evidence["source"]["image_tag"]:
        findings.append(f"Container image tag: {evidence['source']['image_tag']}.")

    scan_path = evidence["source"]["security_scan_path"]
    if scan_path and Path(scan_path).exists():
        scan = read_config_file(scan_path)
        evidence["security_scan_loaded"] = scan is not None
        findings.append(f"Security scan metadata loaded from {scan_path}.")

    return AgentResult(
        name="DevSecOps",
        status=AgentState.complete,
        summary="DevSecOps evidence collected." if findings else "DevSecOps evidence was not collected.",
        findings=findings or ["Run inside a git checkout or configure CI/image/security scan environment variables."],
        evidence=evidence,
    )


def collect_serverless_evidence() -> AgentResult:
    function_name = os.getenv("SERVERLESS_FUNCTION_NAME") or os.getenv("AWS_LAMBDA_FUNCTION_NAME")
    evidence: Dict[str, Any] = {
        "source": {
            "function_name": function_name,
            "aws_lambda_runtime": os.getenv("AWS_EXECUTION_ENV"),
            "cloud_run_service": os.getenv("K_SERVICE"),
        }
    }
    findings: List[str] = []
    if evidence["source"]["aws_lambda_runtime"]:
        findings.append(f"AWS Lambda runtime detected: {evidence['source']['aws_lambda_runtime']}.")
    if evidence["source"]["cloud_run_service"]:
        findings.append(f"Cloud Run service detected: {evidence['source']['cloud_run_service']}.")

    if function_name and shutil.which("aws"):
        config = run_command(["aws", "lambda", "get-function-configuration", "--function-name", function_name, "--output", "json"])
        evidence["lambda_config_ok"] = config["ok"]
        if config["ok"]:
            payload = json.loads(config["stdout"])
            evidence["lambda_runtime"] = payload.get("Runtime")
            evidence["lambda_timeout"] = payload.get("Timeout")
            findings.append(f"Lambda configuration loaded for {function_name}.")
        else:
            evidence["lambda_error"] = config["stderr"]

    if not findings:
        return unavailable_agent("Serverless", "Serverless evidence was not collected.", "Set SERVERLESS_FUNCTION_NAME/AWS_LAMBDA_FUNCTION_NAME or run inside a serverless runtime.", evidence)
    return AgentResult(name="Serverless", status=AgentState.complete, summary="Serverless evidence collected.", findings=findings, evidence=evidence)


def plan_agent_names(description: str) -> List[str]:
    if os.getenv("SENTINEL_RUN_ALL_AGENTS") == "1":
        return ALL_AGENT_NAMES

    text = description.lower()
    selected = ["Planner", "Deployment", "Metrics", "Logs"]

    rules = [
        ("Database", ["database", "postgres", "postgresql", "sql", "db ", "connection pool", "checkout", "timeout"]),
        ("Redis", ["redis", "cache", "nosql", "keyspace"]),
        ("DNS", ["dns", "domain", "hostname", "lookup", "resolve", ".com", ".net", ".org", "cannot reach"]),
        ("Network", ["network", "tcp", "udp", "port", "firewall", "unreachable", "timeout", "connection refused"]),
        ("Storage", ["storage", "disk", "volume", "pvc", "persistentvolume", "mount", "read-only", "iops"]),
        ("Security", ["security", "iam", "rbac", "secret", "certificate", "cert", "tls", "permission", "access denied"]),
        ("Kubernetes", ["kubernetes", "k8s", "pod", "container", "deployment", "crashloop", "oom", "checkout", "timeout"]),
        ("Cloud", ["cloud", "aws", "gcp", "azure", "load balancer", "region", "iam"]),
        ("DevSecOps", ["deploy", "deployment", "pipeline", "ci", "cd", "image", "rollback", "scan"]),
        ("Serverless", ["lambda", "serverless", "cloud run", "function"]),
    ]

    for agent, keywords in rules:
        if any(keyword in text for keyword in keywords):
            selected.append(agent)

    for env_name, agent in [
        ("REDIS_URL", "Redis"),
        ("DNS_HOST", "DNS"),
        ("NETWORK_TARGET_HOST", "Network"),
        ("STORAGE_PATH", "Storage"),
        ("TLS_HOST", "Security"),
        ("DATABASE_URL", "Database"),
        ("PROMETHEUS_URL", "Metrics"),
        ("SERVERLESS_FUNCTION_NAME", "Serverless"),
    ]:
        if os.getenv(env_name):
            selected.append(agent)

    return dedupe([name for name in selected if name in ALL_AGENT_NAMES])


AGENT_RUNNERS = {
    "Deployment": deployment_agent,
    "Metrics": metrics_agent,
    "Logs": logs_agent,
    "Database": database_agent,
    "Redis": redis_agent,
    "DNS": dns_agent,
    "Network": network_agent,
    "Storage": storage_agent,
    "Security": security_agent,
    "Kubernetes": kubernetes_agent,
    "Cloud": cloud_agent,
    "DevSecOps": devsecops_agent,
    "Serverless": serverless_agent,
}


def dedupe(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def extract_hostname(text: str) -> Optional[str]:
    match = re.search(r"\b((?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,})\b", text)
    return match.group(1) if match else None


def network_target(description: str) -> tuple[Optional[str], Optional[int]]:
    host = os.getenv("NETWORK_TARGET_HOST")
    port = parse_int(os.getenv("NETWORK_TARGET_PORT"))
    if host and port:
        return host, port

    database_url = os.getenv("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        if parsed.hostname:
            return parsed.hostname, parsed.port or 5432

    hostname = os.getenv("DNS_HOST") or extract_hostname(description)
    if hostname:
        return hostname, parse_int(os.getenv("NETWORK_TARGET_PORT")) or 443

    return None, None


def udp_probe(host: str, port: int) -> tuple[bool, Optional[str]]:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(3)
            sock.sendto(b"", (host, port))
        return True, None
    except OSError as exc:
        return False, str(exc)


def tls_certificate_expiry(host: str) -> Dict[str, Any]:
    try:
        import ssl
        from datetime import datetime, timezone

        context = ssl.create_default_context()
        with socket.create_connection((host, 443), timeout=4) as sock:
            with context.wrap_socket(sock, server_hostname=host) as secure:
                cert = secure.getpeercert()
        not_after = cert.get("notAfter")
        expires = datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc) if not_after else None
        days = (expires - datetime.now(timezone.utc)).days if expires else None
        return {"tls_cert_present": True, "tls_expires_at": not_after, "tls_days_remaining": days}
    except Exception as exc:
        return {"tls_cert_present": False, "tls_error": str(exc)}


def extract_redis_metric(info_text: str, key: str) -> Optional[int]:
    match = re.search(rf"^{re.escape(key)}:(\d+)", info_text, flags=re.MULTILINE)
    return parse_int(match.group(1)) if match else None


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
    redis = evidence.get("redis", {})
    dns = evidence.get("dns", {})
    network = evidence.get("network", {})
    storage = evidence.get("storage", {})
    security = evidence.get("security", {})
    kubernetes = evidence.get("kubernetes", {})
    cloud = evidence.get("cloud", {})
    serverless = evidence.get("serverless", {})

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
    if network.get("tcp_connect_ok") is False:
        network_score += 35
        network_reasons = [f"TCP connection to {network.get('source', {}).get('host')}:{network.get('source', {}).get('port')} failed."]
    if metrics.get("error_rate_spike") and not logs.get("connection_timeout_logs"):
        network_score += 5
        if network_reasons == ["No source-backed network evidence was collected."]:
            network_reasons = []
        network_reasons.append("Error rate is elevated, but logs did not identify database connection timeouts.")

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

    dns_score = 0
    dns_reasons: List[str] = []
    if dns.get("forward_lookup_ok") is False:
        dns_score += 45
        dns_reasons.append("DNS forward lookup failed for the target hostname.")
    if dns.get("forward_lookup_ok") and not dns.get("reverse_lookup_complete"):
        dns_score += 10
        dns_reasons.append("One or more reverse DNS lookups did not return hostnames.")
    if not dns_reasons:
        dns_reasons.append("No source-backed DNS failure evidence was collected.")

    redis_score = 0
    redis_reasons: List[str] = []
    if redis.get("ping_ok") is False:
        redis_score += 35
        redis_reasons.append("Redis PING did not return PONG.")
    miss_rate = redis.get("cache_miss_rate_pct")
    if miss_rate is not None and miss_rate >= 50:
        redis_score += 20
        redis_reasons.append(f"Redis cache miss rate is {miss_rate}%.")
    if not redis_reasons:
        redis_reasons.append("No source-backed Redis or NoSQL failure evidence was collected.")

    storage_score = 0
    storage_reasons: List[str] = []
    if storage.get("disk_used_pct") is not None and storage["disk_used_pct"] >= 90:
        storage_score += 35
        storage_reasons.append(f"Filesystem usage is {storage['disk_used_pct']}%.")
    if storage.get("pvc_pending", 0) > 0:
        storage_score += 30
        storage_reasons.append(f"{storage.get('pvc_pending')} Kubernetes PVC(s) are not Bound.")
    if not storage_reasons:
        storage_reasons.append("No source-backed storage failure evidence was collected.")

    security_score = 0
    security_reasons: List[str] = []
    if security.get("tls_cert_present") is False and security.get("tls_error"):
        security_score += 20
        security_reasons.append("TLS certificate check failed.")
    if security.get("tls_days_remaining") is not None and security["tls_days_remaining"] <= 14:
        security_score += 30
        security_reasons.append(f"TLS certificate expires in {security['tls_days_remaining']} day(s).")
    if security.get("rbac_can_get_pods") is False:
        security_score += 15
        security_reasons.append("Kubernetes RBAC cannot read pods in the target namespace.")
    if not security_reasons:
        security_reasons.append("No source-backed security failure evidence was collected.")

    cloud_score = 0
    cloud_reasons: List[str] = []
    if cloud.get("aws_sts_ok") is False:
        cloud_score += 10
        cloud_reasons.append("AWS STS identity check failed.")
    if not cloud_reasons:
        cloud_reasons.append("No source-backed cloud control-plane failure evidence was collected.")

    serverless_score = 0
    serverless_reasons: List[str] = []
    if serverless.get("lambda_config_ok") is False:
        serverless_score += 10
        serverless_reasons.append("Lambda function configuration check failed.")
    if not serverless_reasons:
        serverless_reasons.append("No source-backed serverless failure evidence was collected.")

    return sorted(
        [
            RootCauseScore(hypothesis="Database connection pool exhaustion", score=db_score, reasons=db_reasons or ["No source-backed database-pool evidence was collected."]),
            RootCauseScore(hypothesis="Redis or NoSQL cache issue", score=redis_score, reasons=redis_reasons),
            RootCauseScore(hypothesis="DNS resolution issue", score=dns_score, reasons=dns_reasons),
            RootCauseScore(hypothesis="Application bug", score=app_score, reasons=app_reasons),
            RootCauseScore(hypothesis="Network issue", score=network_score, reasons=network_reasons),
            RootCauseScore(hypothesis="Storage capacity or mount issue", score=storage_score, reasons=storage_reasons),
            RootCauseScore(hypothesis="Security, certificate, or RBAC issue", score=security_score, reasons=security_reasons),
            RootCauseScore(hypothesis="Kubernetes capacity issue", score=kube_score, reasons=kube_reasons),
            RootCauseScore(hypothesis="Cloud control-plane or account issue", score=cloud_score, reasons=cloud_reasons),
            RootCauseScore(hypothesis="Serverless runtime or function issue", score=serverless_score, reasons=serverless_reasons),
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
                "Set DNS_HOST, NETWORK_TARGET_HOST/PORT, REDIS_URL, STORAGE_PATH, TLS_HOST, or cloud/serverless metadata for broader infrastructure checks.",
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
    redis = evidence.get("redis", {})
    dns = evidence.get("dns", {})
    network = evidence.get("network", {})
    storage = evidence.get("storage", {})
    security = evidence.get("security", {})
    logs = evidence.get("logs", {})
    metrics = evidence.get("metrics", {})
    kubernetes = evidence.get("kubernetes", {})
    cloud = evidence.get("cloud", {})
    devsecops = evidence.get("devsecops", {})
    serverless = evidence.get("serverless", {})

    if deployment.get("db_pool_size_changed"):
        items.append(f"Deployment config shows DB_POOL_SIZE changed from {deployment.get('db_pool_size_before')} to {deployment.get('db_pool_size_after')}.")
    if database.get("pool_saturation_pct") is not None:
        items.append(f"PostgreSQL diagnostics estimate pool saturation at {database.get('pool_saturation_pct')}%.")
    if database.get("waiting_queries") is not None:
        items.append(f"PostgreSQL reports {database.get('waiting_queries')} sessions with wait events.")
    if redis.get("ping_ok") is not None:
        items.append(f"Redis PING status: {'ok' if redis.get('ping_ok') else 'failed'}.")
    if redis.get("cache_miss_rate_pct") is not None:
        items.append(f"Redis cache miss rate is {redis.get('cache_miss_rate_pct')}%.")
    if dns.get("forward_lookup_ok") is not None:
        items.append(f"DNS forward lookup for {dns.get('source', {}).get('hostname')} {'succeeded' if dns.get('forward_lookup_ok') else 'failed'}.")
    if network.get("tcp_connect_ok") is not None:
        source = network.get("source", {})
        items.append(f"TCP connection to {source.get('host')}:{source.get('port')} {'succeeded' if network.get('tcp_connect_ok') else 'failed'}.")
    if storage.get("disk_used_pct") is not None:
        items.append(f"Filesystem usage for {storage.get('source', {}).get('storage_path')} is {storage.get('disk_used_pct')}%.")
    if storage.get("pvc_count") is not None:
        items.append(f"Kubernetes storage reports {storage.get('pvc_count')} PVC(s), {storage.get('pvc_pending')} not Bound.")
    if security.get("tls_days_remaining") is not None:
        items.append(f"TLS certificate for {security.get('source', {}).get('tls_host')} expires in {security.get('tls_days_remaining')} day(s).")
    if security.get("rbac_can_get_pods") is not None:
        items.append(f"Kubernetes RBAC can get pods: {security.get('rbac_can_get_pods')}.")
    if logs.get("connection_timeout_logs"):
        items.append(f"Application logs contain {logs.get('connection_timeout_count')} connection-timeout matches.")
    if metrics.get("p95_latency_ms") is not None:
        items.append(f"Prometheus p95 latency query returned {round(metrics.get('p95_latency_ms'), 2)} ms.")
    if metrics.get("error_rate_pct") is not None:
        items.append(f"Prometheus error-rate query returned {round(metrics.get('error_rate_pct'), 2)}%.")
    if kubernetes.get("pod_count") is not None:
        items.append(f"Kubernetes reports {kubernetes.get('ready_pods')} of {kubernetes.get('pod_count')} pods ready.")
    if cloud.get("aws_account"):
        items.append(f"AWS STS identity is available for account {cloud.get('aws_account')}.")
    if devsecops.get("git_head"):
        items.append(f"DevSecOps evidence found git commit {devsecops.get('git_head')}.")
    if serverless.get("lambda_runtime"):
        items.append(f"Serverless Lambda runtime is {serverless.get('lambda_runtime')}.")
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
    if top.hypothesis == "DNS resolution issue":
        return [
            "Verify authoritative DNS records, TTL, and recent DNS changes.",
            "Update records only after an engineer confirms the expected target.",
        ]
    if top.hypothesis == "Network issue":
        return [
            "Check firewall rules, security groups, load balancer target health, and route tables.",
            "Change network policy only after human approval.",
        ]
    if top.hypothesis == "Storage capacity or mount issue":
        return [
            "Inspect disk usage, PVC binding, mount status, and volume permissions.",
            "Expand or remount storage only after an engineer approves the action.",
        ]
    if top.hypothesis == "Security, certificate, or RBAC issue":
        return [
            "Inspect TLS certificate validity, Kubernetes RBAC, service accounts, and secrets.",
            "Rotate credentials or modify permissions only after human approval.",
        ]
    if top.hypothesis == "Redis or NoSQL cache issue":
        return [
            "Inspect Redis availability, latency, memory, connected clients, and cache miss rate.",
            "Flush, restart, or resize cache infrastructure only after human approval.",
        ]
    return [
        "Review the collected evidence with the owning engineering team.",
        "Do not execute remediation automatically; require human approval.",
    ]
