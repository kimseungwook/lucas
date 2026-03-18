from __future__ import annotations

import json
import os
import subprocess
from typing import Any, TypedDict


class SecuritySignalBundle(TypedDict):
    enabled: bool
    mode: str
    monitored_namespaces: list[str]
    policy_reports: list[dict[str, Any]]
    events: list[dict[str, Any]]
    workloads: list[dict[str, Any]]


def _kubectl_base_command() -> list[str]:
    command = ["kubectl"]
    context = os.environ.get("KUBECTL_CONTEXT", "").strip()
    if context:
        command.extend(["--context", context])
    return command


def _run_kubectl_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(_kubectl_base_command() + args, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def _run_kubectl_json_or_empty(args: list[str]) -> dict[str, Any]:
    try:
        return _run_kubectl_json(args)
    except subprocess.CalledProcessError:
        return {"items": []}


def _parse_namespaces(namespaces_csv: str) -> list[str]:
    return [value.strip() for value in namespaces_csv.split(",") if value.strip()]


def build_security_signal_inputs(
    *,
    enabled: bool,
    namespaces_csv: str,
    mode: str,
    policy_reports: list[dict[str, Any]],
    events: list[dict[str, Any]],
    deployments: list[dict[str, Any]],
    statefulsets: list[dict[str, Any]],
) -> SecuritySignalBundle:
    monitored_namespaces = _parse_namespaces(namespaces_csv)
    if not enabled or not monitored_namespaces:
        return {
            "enabled": False,
            "mode": mode,
            "monitored_namespaces": [],
            "policy_reports": [],
            "events": [],
            "workloads": [],
        }

    namespace_set = set(monitored_namespaces)

    collected_reports: list[dict[str, Any]] = []
    for report in policy_reports:
        namespace = str(report.get("metadata", {}).get("namespace", ""))
        if namespace not in namespace_set:
            continue
        for result in report.get("results", []) or []:
            collected_reports.append(
                {
                    "namespace": namespace,
                    "report_name": str(report.get("metadata", {}).get("name", "")),
                    "policy": str(result.get("policy", "")),
                    "category": str(result.get("category", "")),
                    "message": str(result.get("message", "")),
                    "severity": str(result.get("severity", "")),
                    "source": str(result.get("source", "")),
                }
            )

    collected_events: list[dict[str, Any]] = []
    for event in events:
        namespace = str(event.get("metadata", {}).get("namespace", ""))
        if namespace not in namespace_set:
            continue
        involved = event.get("involvedObject", {}) or {}
        collected_events.append(
            {
                "namespace": namespace,
                "resource": f"{involved.get('kind', 'Unknown')}/{involved.get('name', 'unknown')}",
                "message": str(event.get("message", "")),
            }
        )

    workloads: list[dict[str, Any]] = []
    for kind, items in (("Deployment", deployments), ("StatefulSet", statefulsets)):
        for item in items:
            namespace = str(item.get("metadata", {}).get("namespace", ""))
            if namespace not in namespace_set:
                continue
            containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []) or []
            image = str(containers[0].get("image", "")) if containers else ""
            workloads.append(
                {
                    "kind": kind,
                    "namespace": namespace,
                    "name": str(item.get("metadata", {}).get("name", "")),
                    "image": image,
                }
            )

    return {
        "enabled": True,
        "mode": mode,
        "monitored_namespaces": monitored_namespaces,
        "policy_reports": collected_reports,
        "events": collected_events,
        "workloads": workloads,
    }


def collect_security_signal_inputs() -> SecuritySignalBundle:
    enabled = os.environ.get("SECURITY_MONITOR_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
    namespaces_csv = os.environ.get("SECURITY_MONITOR_NAMESPACES", "")
    mode = os.environ.get("SECURITY_MONITOR_MODE", "report-only").strip() or "report-only"

    if not enabled or not _parse_namespaces(namespaces_csv):
        return build_security_signal_inputs(
            enabled=False,
            namespaces_csv=namespaces_csv,
            mode=mode,
            policy_reports=[],
            events=[],
            deployments=[],
            statefulsets=[],
        )

    policy_reports: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    deployments: list[dict[str, Any]] = []
    statefulsets: list[dict[str, Any]] = []

    for namespace in _parse_namespaces(namespaces_csv):
        policy_reports.extend(_run_kubectl_json_or_empty(["-n", namespace, "get", "policyreports", "-o", "json"]).get("items", []))
        events.extend(_run_kubectl_json_or_empty(["-n", namespace, "get", "events", "-o", "json"]).get("items", []))
        deployments.extend(_run_kubectl_json_or_empty(["-n", namespace, "get", "deployments", "-o", "json"]).get("items", []))
        statefulsets.extend(_run_kubectl_json_or_empty(["-n", namespace, "get", "statefulsets", "-o", "json"]).get("items", []))

    return build_security_signal_inputs(
        enabled=True,
        namespaces_csv=namespaces_csv,
        mode=mode,
        policy_reports=policy_reports,
        events=events,
        deployments=deployments,
        statefulsets=statefulsets,
    )
