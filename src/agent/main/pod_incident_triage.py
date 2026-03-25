from __future__ import annotations

import importlib
import json
import os
import subprocess
from typing import Any

try:
    from .cluster_snapshot import _kubectl_base_command, _phase_key, _pod_reason, _reason_key, _severity_score, resolve_target_namespaces
except ImportError:
    cluster_snapshot = importlib.import_module("cluster_snapshot")
    _kubectl_base_command = cluster_snapshot._kubectl_base_command
    _phase_key = cluster_snapshot._phase_key
    _pod_reason = cluster_snapshot._pod_reason
    _reason_key = cluster_snapshot._reason_key
    _severity_score = cluster_snapshot._severity_score
    resolve_target_namespaces = cluster_snapshot.resolve_target_namespaces


def _run_kubectl_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        _kubectl_base_command() + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _run_kubectl_json_or_empty(args: list[str]) -> dict[str, Any]:
    try:
        return _run_kubectl_json(args)
    except subprocess.CalledProcessError:
        return {"items": []}


def _parse_csv(raw: str) -> list[str]:
    return [value.strip() for value in raw.split(",") if value.strip()]


def resolve_pod_incident_target_namespaces() -> list[str]:
    default_namespace = os.environ.get("TARGET_NAMESPACE", "default")
    raw = os.environ.get("POD_INCIDENT_TARGET_NAMESPACES", "").strip() or os.environ.get("TARGET_NAMESPACES", "")
    return resolve_target_namespaces(default_namespace, raw)


def resolve_pod_incident_target_workloads() -> list[str]:
    return [value.lower() for value in _parse_csv(os.environ.get("POD_INCIDENT_TARGET_WORKLOADS", ""))]


def _restart_count(pod: dict[str, Any]) -> int:
    statuses = pod.get("status", {}).get("containerStatuses", []) or []
    return sum(int(status.get("restartCount", 0) or 0) for status in statuses)


def _last_state_reason(pod: dict[str, Any]) -> str | None:
    statuses = pod.get("status", {}).get("containerStatuses", []) or []
    for status in statuses:
        last_state = status.get("lastState") or {}
        terminated = last_state.get("terminated") or {}
        if terminated.get("reason"):
            return str(terminated["reason"])
    return None


def _owner_ref(pod: dict[str, Any]) -> tuple[str, str]:
    owner_refs = pod.get("metadata", {}).get("ownerReferences", []) or []
    if owner_refs:
        owner = owner_refs[0] or {}
        return str(owner.get("kind") or "Pod"), str(owner.get("name") or pod.get("metadata", {}).get("name") or "unknown")
    return "Pod", str(pod.get("metadata", {}).get("name") or "unknown")


def _owner_lookup(payload: dict[str, Any], owner_kind: str) -> dict[str, tuple[str, str]]:
    mapping: dict[str, tuple[str, str]] = {}
    for item in payload.get("items", []) or []:
        metadata = item.get("metadata", {}) or {}
        name = str(metadata.get("name") or "")
        if not name:
            continue
        owner_refs = item.get("ownerReferences", []) or metadata.get("ownerReferences", []) or []
        resolved_kind = owner_kind
        resolved_name = name
        if owner_refs:
            owner = owner_refs[0] or {}
            resolved_kind = str(owner.get("kind") or owner_kind)
            resolved_name = str(owner.get("name") or name)
        mapping[name] = (resolved_kind, resolved_name)
    return mapping


def _logical_workload_ref(
    pod: dict[str, Any],
    *,
    replicaset_owners: dict[str, tuple[str, str]],
    job_owners: dict[str, tuple[str, str]],
) -> tuple[str, str, str]:
    owner_kind, owner_name = _owner_ref(pod)
    if owner_kind == "ReplicaSet" and owner_name in replicaset_owners:
        owner_kind, owner_name = replicaset_owners[owner_name]
    elif owner_kind == "Job" and owner_name in job_owners:
        owner_kind, owner_name = job_owners[owner_name]

    normalized_kind = owner_kind.lower()
    return owner_kind, owner_name, f"{normalized_kind}/{owner_name}".lower()


def _event_messages(events_payload: dict[str, Any], pod_name: str) -> list[str]:
    messages: list[str] = []
    for item in events_payload.get("items", []):
        involved = item.get("involvedObject", {}) or {}
        if involved.get("name") == pod_name:
            message = str(item.get("message") or "").strip()
            if message:
                messages.append(message)
    return messages[:3]


def _has_issue(pod: dict[str, Any]) -> tuple[bool, str, str | None, int]:
    phase = str(pod.get("status", {}).get("phase", "Unknown"))
    phase_key = _phase_key(phase)
    reason = _pod_reason(pod)
    reason_key = _reason_key(phase_key, reason)
    restart_count = _restart_count(pod)
    has_issue = phase_key != "Completed" and (phase_key != "Running" or restart_count > 0 or reason_key is not None)
    return has_issue, phase_key, reason_key, restart_count


def _severity_label(phase_key: str, reason_key: str | None, restart_count: int) -> str:
    score, _, _ = _severity_score(phase_key, reason_key, restart_count)
    if score >= 80:
        return "high"
    if score >= 50:
        return "medium"
    return "low"


def _classify_incident(
    *,
    phase: str,
    reason: str,
    last_state_reason: str | None,
    events: list[str],
    blast_radius: str,
) -> tuple[str, list[str], str, list[str]]:
    lowered_events = [event.lower() for event in events]
    lowered_reason = reason.lower()
    lowered_last_state = (last_state_reason or "").lower()

    def with_context(primary: str, cause: str, actions: list[str], extra: list[str] | None = None) -> tuple[list[str], str, list[str]]:
        evidence = [primary]
        if extra:
            evidence.extend(extra)
        return evidence[:4], cause, actions

    infra_markers = [
        "attachvolume.attach failed",
        "failedmount",
        "failedattachvolume",
        "failedscheduling",
        "node affinity",
        "unbound immediate persistentvolumeclaims",
        "volume node affinity conflict",
    ]
    infra_match = next((event for event, lowered in zip(events, lowered_events) if any(marker in lowered for marker in infra_markers)), None)
    if infra_match:
        evidence, likely_cause, actions = with_context(
            infra_match,
            "The pod appears blocked by storage, scheduling, or node-placement infrastructure conditions.",
            [
                "Inspect PVC/PV attachment and node-placement evidence.",
                "Verify the workload is scheduled onto a compatible node pool or zone.",
                "Escalate to the platform owner if multiple workloads show the same infra symptom.",
            ],
            [f"blast_radius={blast_radius}", f"phase={phase} reason={reason}"],
        )
        return "infra_or_placement_failure", evidence, likely_cause, actions

    config_markers = ["secret", "configmap", "createcontainerconfigerror", "invalid env", "not found"]
    config_match = next((event for event, lowered in zip(events, lowered_events) if any(marker in lowered for marker in config_markers)), None)
    if lowered_reason == "createcontainerconfigerror" or config_match:
        primary = config_match or f"reason={reason}"
        evidence, likely_cause, actions = with_context(
            primary,
            "The workload is failing before normal startup because required configuration or secret wiring is missing or invalid.",
            [
                "Verify secret, ConfigMap, and environment reference wiring for the workload.",
                "Compare the live manifest against the expected config contract with the owning team.",
                "Escalate to the manifest or configuration owner instead of recycling pods repeatedly.",
            ],
            [f"phase={phase}", f"blast_radius={blast_radius}"],
        )
        return "config_or_secret_failure", evidence, likely_cause, actions

    image_markers = ["failed to pull image", "back-off pulling image", "errimagepull", "imagepullbackoff"]
    image_match = next((event for event, lowered in zip(events, lowered_events) if any(marker in lowered for marker in image_markers)), None)
    if lowered_reason in {"imagepullbackoff", "errimagepull", "imageinspecterror"} or image_match:
        primary = image_match or f"reason={reason}"
        evidence, likely_cause, actions = with_context(
            primary,
            f"Image retrieval or startup artifact failure is preventing the workload from starting: {primary}",
            [
                "Verify image tag, digest, registry reachability, and pull credentials.",
                "Confirm whether a recent rollout introduced a new image reference.",
                "Escalate to the image or release owner if the same image fails across replicas.",
            ],
            [f"phase={phase}", f"blast_radius={blast_radius}"],
        )
        return "image_or_startup_failure", evidence, likely_cause, actions

    probe_markers = ["oomkilled", "liveness probe failed", "readiness probe failed", "startup probe failed"]
    probe_match = next((event for event, lowered in zip(events, lowered_events) if any(marker in lowered for marker in probe_markers)), None)
    if lowered_last_state == "oomkilled" or probe_match:
        primary = probe_match or f"last_state_reason={last_state_reason or reason}"
        evidence, likely_cause, actions = with_context(
            primary,
            "The workload is restarting because it exceeded resource limits or repeatedly failed health probes.",
            [
                "Verify memory/CPU limits and current probe settings before taking action.",
                "Check whether the workload has enough warm-up time to satisfy startup or readiness probes.",
                "Escalate to the owning team if limit or probe tuning requires a manifest change.",
            ],
            [f"phase={phase} reason={reason}", f"blast_radius={blast_radius}"],
        )
        return "resource_or_probe_failure", evidence, likely_cause, actions

    dependency_markers = [
        "connection refused",
        "i/o timeout",
        "context deadline exceeded",
        "tls",
        "no such host",
        "dial tcp",
        "authentication failed",
    ]
    dependency_match = next((event for event, lowered in zip(events, lowered_events) if any(marker in lowered for marker in dependency_markers)), None)
    if dependency_match:
        evidence, likely_cause, actions = with_context(
            dependency_match,
            "The pod appears healthy enough to start but is failing against an external dependency or network path.",
            [
                "Verify reachability and credentials for the dependent service before restarting more pods.",
                "Check whether the same dependency symptom appears in sibling workloads.",
                "Escalate to the dependency owner if the backend itself is degraded.",
            ],
            [f"blast_radius={blast_radius}", f"phase={phase} reason={reason}"],
        )
        return "dependency_connectivity_failure", evidence, likely_cause, actions

    primary = f"phase={phase} reason={reason} restarts-observed"
    evidence, likely_cause, actions = with_context(
        primary,
        "The failure currently looks pod-local and transient, but it still needs current and previous log inspection.",
        [
            "Inspect current and previous container logs for a repeating crash signature.",
            "If the failure is isolated and no rollout or infra signal exists, consider one shallow pod recycle.",
            "Escalate if sibling replicas begin failing with the same pattern.",
        ],
        [f"blast_radius={blast_radius}", f"last_state_reason={last_state_reason or 'none'}"],
    )
    return "pod_local_transient_failure", evidence, likely_cause, actions


def build_pod_incident_inputs(
    *,
    namespace: str,
    pods_payload: dict[str, Any],
    events_payload: dict[str, Any],
    replicasets_payload: dict[str, Any] | None = None,
    jobs_payload: dict[str, Any] | None = None,
    target_workloads: list[str] | None = None,
) -> dict[str, Any]:
    pods = list(pods_payload.get("items", []) or [])
    incidents: list[dict[str, Any]] = []
    status_breakdown: dict[str, int] = {}
    reason_breakdown: dict[str, int] = {}
    pods_with_restarts = 0
    monitored_pod_count = 0

    owner_totals: dict[tuple[str, str], int] = {}
    owner_healthy: dict[tuple[str, str], int] = {}
    owner_problematic: dict[tuple[str, str], int] = {}
    replicaset_owners = _owner_lookup(replicasets_payload or {"items": []}, "ReplicaSet")
    job_owners = _owner_lookup(jobs_payload or {"items": []}, "Job")
    target_workload_set = {value.lower() for value in (target_workloads or [])}

    prepared: list[dict[str, Any]] = []

    for pod in pods:
        owner_kind, owner_name, workload_ref = _logical_workload_ref(
            pod,
            replicaset_owners=replicaset_owners,
            job_owners=job_owners,
        )
        if target_workload_set and workload_ref not in target_workload_set:
            continue
        monitored_pod_count += 1
        owner_key = (owner_kind, owner_name)
        has_issue, phase_key, reason_key, restart_count = _has_issue(pod)
        status_breakdown[phase_key] = status_breakdown.get(phase_key, 0) + 1
        if reason_key:
            reason_breakdown[reason_key] = reason_breakdown.get(reason_key, 0) + 1
        if restart_count > 0:
            pods_with_restarts += 1

        owner_totals[owner_key] = owner_totals.get(owner_key, 0) + 1
        if has_issue:
            owner_problematic[owner_key] = owner_problematic.get(owner_key, 0) + 1
        else:
            owner_healthy[owner_key] = owner_healthy.get(owner_key, 0) + 1

        prepared.append(
            {
                "pod": pod,
                "owner_kind": owner_kind,
                "owner_name": owner_name,
                "workload_ref": workload_ref,
                "owner_key": owner_key,
                "has_issue": has_issue,
                "phase_key": phase_key,
                "reason_key": reason_key,
                "restart_count": restart_count,
            }
        )

    affected_owners = sum(1 for count in owner_problematic.values() if count > 0)

    for item in prepared:
        if not item["has_issue"]:
            continue

        pod = item["pod"]
        owner_key = item["owner_key"]
        healthy_peers = max(owner_healthy.get(owner_key, 0), 0)
        problematic_count = owner_problematic.get(owner_key, 0)

        if affected_owners > 1:
            blast_radius = "multi_workload"
        elif problematic_count == 1 and healthy_peers > 0:
            blast_radius = "isolated_pod"
        else:
            blast_radius = "single_workload"

        pod_name = str(pod.get("metadata", {}).get("name") or "unknown")
        phase = item["phase_key"]
        reason = item["reason_key"] or item["phase_key"]
        last_state_reason = _last_state_reason(pod)
        events = _event_messages(events_payload, pod_name)
        category, evidence, likely_cause, recommended_actions = _classify_incident(
            phase=phase,
            reason=reason,
            last_state_reason=last_state_reason,
            events=events,
            blast_radius=blast_radius,
        )
        incidents.append(
            {
                "namespace": namespace,
                "pod": pod_name,
                "resource": f"pod/{pod_name}",
                "type": "runtime.pod_incident",
                "owner_kind": item["owner_kind"],
                "owner_name": item["owner_name"],
                "workload_ref": item["workload_ref"],
                "phase": phase,
                "reason": reason,
                "restarts": item["restart_count"],
                "severity": _severity_label(item["phase_key"], item["reason_key"], item["restart_count"]),
                "node": str(pod.get("spec", {}).get("nodeName") or ""),
                "last_state_reason": last_state_reason,
                "healthy_peer_count": healthy_peers,
                "needs_previous_logs": item["restart_count"] > 0,
                "blast_radius": blast_radius,
                "events": events,
                "category": category,
                "evidence": evidence,
                "likely_cause": likely_cause,
                "recommended_actions": recommended_actions,
            }
        )

    incidents.sort(
        key=lambda incident: _severity_score(
            str(incident["phase"]),
            None if str(incident["reason"]) == str(incident["phase"]) else str(incident["reason"]),
            int(incident["restarts"]),
        ),
        reverse=True,
    )

    return {
        "status": "issues_found" if incidents else "ok",
        "incident_summary": {
            "pod_count": monitored_pod_count,
            "issue_count": len(incidents),
            "pods_with_restarts": pods_with_restarts,
            "status_breakdown": status_breakdown,
            "reason_breakdown": reason_breakdown,
            "affected_owners": affected_owners,
        },
        "incidents": incidents,
    }


def collect_pod_incident_inputs(namespace: str) -> dict[str, Any]:
    target_workloads = resolve_pod_incident_target_workloads()
    pods_payload = _run_kubectl_json_or_empty(["-n", namespace, "get", "pods", "-o", "json"])
    events_payload = _run_kubectl_json_or_empty(["-n", namespace, "get", "events", "-o", "json"])
    replicasets_payload = _run_kubectl_json_or_empty(["-n", namespace, "get", "replicasets", "-o", "json"]) if target_workloads else {"items": []}
    jobs_payload = _run_kubectl_json_or_empty(["-n", namespace, "get", "jobs", "-o", "json"]) if target_workloads else {"items": []}
    return build_pod_incident_inputs(
        namespace=namespace,
        pods_payload=pods_payload,
        events_payload=events_payload,
        replicasets_payload=replicasets_payload,
        jobs_payload=jobs_payload,
        target_workloads=target_workloads,
    )
