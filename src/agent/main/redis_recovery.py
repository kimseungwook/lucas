from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, Callable, TypedDict


class RedisRecoveryFinding(TypedDict, total=False):
    type: str
    workload: str
    namespace: str
    target_pod: str
    health: str
    evidence: list[str]
    likely_cause: str
    suppressed: bool
    suppression_reason: str
    action: str
    action_result: str
    recommended_next_steps: list[str]


class RedisRecoveryResult(TypedDict):
    status: str
    redis_recovery_summary: dict[str, int]
    redis_recovery_findings: list[RedisRecoveryFinding]


def _kubectl_base_command() -> list[str]:
    command = ["kubectl"]
    context = os.environ.get("KUBECTL_CONTEXT", "").strip()
    if context:
        command.extend(["--context", context])
    return command


def _run_kubectl_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(_kubectl_base_command() + args, capture_output=True, text=True, check=True)
    import json
    return json.loads(result.stdout)


def _serviceaccount_namespace() -> str:
    namespace_file = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if namespace_file.exists():
        return namespace_file.read_text().strip()
    return os.environ.get("LUCAS_NAMESPACE", os.environ.get("TARGET_NAMESPACE", "default"))


def _match_selector(pod: dict[str, Any], selector: dict[str, str]) -> bool:
    labels = pod.get("metadata", {}).get("labels", {}) or {}
    return all(labels.get(k) == v for k, v in selector.items())


def _extract_pod_events(events: list[dict[str, Any]], pod_name: str) -> list[str]:
    messages: list[str] = []
    for item in events:
        if item.get("involvedObject", {}).get("name") == pod_name:
            message = item.get("message")
            if message:
                messages.append(str(message))
    return messages


def _probe_redis(namespace: str, pod_name: str) -> dict[str, Any]:
    cmd = _kubectl_base_command() + [
        "exec",
        pod_name,
        "-n",
        namespace,
        "--",
        "sh",
        "-lc",
        "redis-cli ping",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    output = (result.stdout or result.stderr or "").strip()
    ok = result.returncode == 0 and "PONG" in output
    evidence = output or f"redis-cli ping exited {result.returncode}"
    return {"ok": ok, "evidence": evidence[:300]}


def _workload_key(workload: dict[str, Any]) -> str:
    return f"{workload.get('namespace','')}/{workload.get('kind','')}/{workload.get('name','')}"


def _classify_pod_health(pod: dict[str, Any]) -> tuple[str, list[str]]:
    evidence: list[str] = []
    k8s_signals = 0
    phase = str(pod.get("phase", ""))
    ready = bool(pod.get("ready", False))
    restarts = int(pod.get("restarts", 0) or 0)
    ping = pod.get("ping", {}) or {}
    ping_ok = ping.get("ok")

    if phase and phase != "Running":
        k8s_signals += 1
        evidence.append(f"phase={phase}")
    if not ready:
        k8s_signals += 1
        evidence.append("ready=false")
    if restarts >= 3:
        k8s_signals += 1
        evidence.append(f"restarts={restarts}")

    if ping_ok is False:
        evidence.append(str(ping.get("evidence") or "PING failed"))
        if k8s_signals >= 1:
            return "not_serving", evidence
        return "unknown", evidence

    if k8s_signals:
        return "degraded_but_serving", evidence
    return "healthy", evidence


def _suppression_reason(observation: dict[str, Any], unhealthy_pods: list[dict[str, Any]], recent_action: dict[str, Any] | None, cooldown_seconds: int, now_ts: int | None) -> tuple[str | None, list[str]]:
    evidence: list[str] = []
    status = observation.get("status", {}) or {}
    generation = int(status.get("generation", 0) or 0)
    observed = int(status.get("observedGeneration", generation) or generation)
    updated = int(status.get("updatedReplicas", status.get("replicas", 0)) or 0)
    replicas = int(status.get("replicas", updated) or updated)
    annotations = observation.get("workload", {}).get("annotations", {}) or {}
    workload_events = [str(e) for e in observation.get("workload_events", [])]
    all_pod_events = [msg for pod in observation.get("pods", []) for msg in pod.get("events", [])]

    if annotations.get("lucas.a2w/recovery-disabled", "").lower() == "true":
        return "maintenance", ["recovery-disabled annotation present"]

    if generation > observed or updated < replicas or any("rollout" in e.lower() or "scal" in e.lower() for e in workload_events):
        if generation > observed:
            evidence.append(f"generation={generation} observedGeneration={observed}")
        if updated < replicas:
            evidence.append(f"updatedReplicas={updated} replicas={replicas}")
        return "rollout_in_progress", evidence or ["recent rollout/update event present"]

    infra_terms = ("AttachVolume.Attach failed", "FailedScheduling", "node affinity", "volume node affinity", "paravirtualized")
    for message in all_pod_events:
        if any(term.lower() in message.lower() for term in infra_terms):
            evidence.append(message)
    if len(unhealthy_pods) > 1:
        evidence.append(f"multiple_unhealthy_pods={len(unhealthy_pods)}")
    if evidence:
        return "infra_correlated", evidence

    if recent_action and now_ts is not None:
        ts = int(recent_action.get("timestamp", 0) or 0)
        if ts and now_ts - ts < cooldown_seconds:
            return "cooldown_active", [f"last_action_ts={ts}", f"cooldown_seconds={cooldown_seconds}"]

    return None, []


def build_redis_recovery_result(
    observations: list[dict[str, Any]],
    *,
    auto_delete_enabled: bool = False,
    mutations_allowed: bool = False,
    current_environment: str = "",
    allowed_environments: list[str] | None = None,
    cooldown_seconds: int = 600,
    now_ts: int | None = None,
    recent_actions: dict[str, dict[str, Any]] | None = None,
    action_executor: Callable[[str, str], str] | None = None,
) -> RedisRecoveryResult:
    summary = {"evaluated": 0, "not_serving": 0, "suppressed": 0, "actions_taken": 0}
    findings: list[RedisRecoveryFinding] = []
    allowed_environments = allowed_environments or []
    recent_actions = recent_actions or {}

    for observation in observations:
        workload = observation.get("workload", {}) or {}
        summary["evaluated"] += 1
        workload_key = _workload_key(workload)
        workload_label = f"{workload.get('kind','workload')}/{workload.get('name','unknown')}"
        opted_in = workload.get("annotations", {}).get("lucas.a2w/recovery-mode") == "redis-safe-restart"

        unhealthy_pods = []
        candidate_finding: RedisRecoveryFinding | None = None
        for pod in observation.get("pods", []) or []:
            health, evidence = _classify_pod_health(pod)
            if health == "not_serving":
                unhealthy_pods.append({"pod": pod, "evidence": evidence})
            if candidate_finding is None:
                candidate_finding = {
                    "type": "redis.safe_self_recovery",
                    "workload": workload_label,
                    "namespace": str(workload.get("namespace", "")),
                    "target_pod": str(pod.get("name", "")),
                    "health": health,
                    "evidence": evidence,
                    "likely_cause": "Redis serveability degradation detected." if health != "healthy" else "Redis is healthy.",
                    "suppressed": False,
                    "action": "none",
                    "recommended_next_steps": [],
                }

        if candidate_finding is None:
            continue

        if unhealthy_pods:
            summary["not_serving"] += 1
            candidate = unhealthy_pods[0]
            candidate_finding["target_pod"] = str(candidate["pod"].get("name", ""))
            candidate_finding["health"] = "not_serving"
            candidate_finding["evidence"] = list(candidate["evidence"])
            candidate_finding["likely_cause"] = "Redis appears to be not serving traffic from the target pod."

        suppression_reason, suppression_evidence = _suppression_reason(
            observation,
            unhealthy_pods,
            recent_actions.get(workload_key),
            cooldown_seconds,
            now_ts,
        )

        if suppression_reason:
            candidate_finding["suppressed"] = True
            candidate_finding["suppression_reason"] = suppression_reason
            candidate_finding["action"] = "skipped"
            candidate_finding["evidence"] = candidate_finding["evidence"] + suppression_evidence
            candidate_finding["recommended_next_steps"] = [
                "Wait until suppression conditions clear.",
                "Re-run health evaluation before taking any mutating action.",
            ]
            summary["suppressed"] += 1
            findings.append(candidate_finding)
            continue

        if not unhealthy_pods:
            findings.append(candidate_finding)
            continue

        if not opted_in or not auto_delete_enabled:
            candidate_finding["action"] = "skipped"
            candidate_finding["suppressed"] = True
            candidate_finding["suppression_reason"] = "feature_disabled" if auto_delete_enabled is False else "not_opted_in"
            candidate_finding["recommended_next_steps"] = [
                "Enable the feature flag and workload opt-in only after validation.",
            ]
            summary["suppressed"] += 1
            findings.append(candidate_finding)
            continue

        if not mutations_allowed or current_environment not in allowed_environments:
            candidate_finding["action"] = "skipped"
            candidate_finding["suppressed"] = True
            candidate_finding["suppression_reason"] = "environment_not_allowed"
            candidate_finding["recommended_next_steps"] = [
                "Keep Redis self-recovery in report-only mode outside explicitly allowed environments.",
            ]
            summary["suppressed"] += 1
            findings.append(candidate_finding)
            continue

        if action_executor is None:
            candidate_finding["action"] = "skipped"
            candidate_finding["suppressed"] = True
            candidate_finding["suppression_reason"] = "missing_executor"
            summary["suppressed"] += 1
            findings.append(candidate_finding)
            continue

        action_result = action_executor(str(workload.get("namespace", "")), candidate_finding["target_pod"])
        candidate_finding["action"] = "delete_pod"
        candidate_finding["action_result"] = action_result
        candidate_finding["recommended_next_steps"] = [
            "Observe the replacement pod for stabilization.",
            "Escalate if the same workload becomes unhealthy again during cooldown.",
        ]
        summary["actions_taken"] += 1
        findings.append(candidate_finding)

    status = "issues_found" if findings else "ok"
    return {
        "status": status,
        "redis_recovery_summary": summary,
        "redis_recovery_findings": findings,
    }


def collect_redis_recovery_inputs(target_namespaces: list[str]) -> list[dict[str, Any]]:
    namespaces_filter = {ns for ns in target_namespaces if ns and ns != "all"}
    if not namespaces_filter:
        namespaces_filter = {_serviceaccount_namespace()}

    deployments = _run_kubectl_json(["get", "deployments", "-A", "-o", "json"]).get("items", [])
    statefulsets = _run_kubectl_json(["get", "statefulsets", "-A", "-o", "json"]).get("items", [])
    pods = _run_kubectl_json(["get", "pods", "-A", "-o", "json"]).get("items", [])
    events = _run_kubectl_json(["get", "events", "-A", "-o", "json"]).get("items", [])

    observations: list[dict[str, Any]] = []
    resources = [("Deployment", item) for item in deployments] + [("StatefulSet", item) for item in statefulsets]
    for kind, item in resources:
        namespace = item.get("metadata", {}).get("namespace", "")
        if namespace not in namespaces_filter:
            continue
        annotations = item.get("metadata", {}).get("annotations", {}) or {}
        if annotations.get("lucas.a2w/recovery-mode") != "redis-safe-restart":
            continue
        selector = item.get("spec", {}).get("selector", {}).get("matchLabels", {}) or {}
        matched_pods = []
        for pod in pods:
            if pod.get("metadata", {}).get("namespace") != namespace:
                continue
            if selector and not _match_selector(pod, selector):
                continue
            pod_name = str(pod.get("metadata", {}).get("name", ""))
            container_statuses = pod.get("status", {}).get("containerStatuses", []) or []
            restart_count = sum(int(status.get("restartCount", 0) or 0) for status in container_statuses)
            ready = all(bool(status.get("ready", False)) for status in container_statuses) if container_statuses else False
            matched_pods.append(
                {
                    "name": pod_name,
                    "phase": str(pod.get("status", {}).get("phase", "")),
                    "ready": ready,
                    "restarts": restart_count,
                    "events": _extract_pod_events(events, pod_name),
                    "ping": _probe_redis(namespace, pod_name),
                }
            )

        observations.append(
            {
                "workload": {
                    "kind": kind,
                    "name": item.get("metadata", {}).get("name", ""),
                    "namespace": namespace,
                    "annotations": annotations,
                },
                "status": {
                    "generation": item.get("metadata", {}).get("generation", 0),
                    "observedGeneration": item.get("status", {}).get("observedGeneration", 0),
                    "updatedReplicas": item.get("status", {}).get("updatedReplicas", item.get("status", {}).get("readyReplicas", 0)),
                    "replicas": item.get("spec", {}).get("replicas", 0),
                },
                "workload_events": [
                    str(evt.get("message", ""))
                    for evt in events
                    if evt.get("involvedObject", {}).get("kind") == kind and evt.get("involvedObject", {}).get("name") == item.get("metadata", {}).get("name") and evt.get("metadata", {}).get("namespace") == namespace
                ],
                "pods": matched_pods,
            }
        )

    return observations
