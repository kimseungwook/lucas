from __future__ import annotations

import json
import os
import re
import subprocess


def _phase_key(phase: str) -> str:
    if phase == "Succeeded":
        return "Completed"
    return phase or "Unknown"


def _reason_key(phase_key: str, reason: str) -> str | None:
    normalized = (reason or "").strip()
    if not normalized or normalized in {"Running", "Succeeded", phase_key}:
        return None
    return normalized


def _severity_score(phase_key: str, reason_key: str | None, restart_count: int) -> tuple[int, int, str]:
    severity_map = {
        "CrashLoopBackOff": 100,
        "ImageInspectError": 95,
        "ErrImagePull": 90,
        "ImagePullBackOff": 90,
        "CreateContainerConfigError": 85,
        "ContainerStatusUnknown": 85,
        "Error": 80,
        "Failed": 75,
        "Pending": 60,
        "ContainerCreating": 50,
        "PodInitializing": 45,
        "Unknown": 40,
        "Running": 10 if restart_count > 0 else 0,
        "Completed": 0,
    }
    key = reason_key or phase_key
    return severity_map.get(key, 20), restart_count, key


def _kubectl_base_command() -> list[str]:
    command = ["kubectl"]
    context = os.environ.get("KUBECTL_CONTEXT", "").strip()
    if context:
        command.extend(["--context", context])
    return command


def _run_kubectl(args: list[str]) -> str:
    result = subprocess.run(
        _kubectl_base_command() + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _pod_reason(pod: dict) -> str:
    statuses = pod.get("status", {}).get("containerStatuses", []) or []
    for status in statuses:
        state = status.get("state", {})
        waiting = state.get("waiting") or {}
        terminated = state.get("terminated") or {}
        if waiting.get("reason"):
            return str(waiting["reason"])
        if terminated.get("reason"):
            return str(terminated["reason"])
    return str(pod.get("status", {}).get("phase", "Unknown"))


def build_namespace_snapshot(namespace: str) -> str:
    sections: list[str] = []

    try:
        payload = json.loads(_run_kubectl(["get", "pods", "-n", namespace, "-o", "json"]))
        pod_lines = []
        for pod in payload.get("items", [])[:30]:
            name = pod.get("metadata", {}).get("name", "unknown")
            phase = pod.get("status", {}).get("phase", "Unknown")
            statuses = pod.get("status", {}).get("containerStatuses", []) or []
            restart_count = sum(status.get("restartCount", 0) for status in statuses)
            reason = _pod_reason(pod)
            pod_lines.append(f"- {name}: phase={phase}, restarts={restart_count}, reason={reason}")
        sections.append("Pods:\n" + ("\n".join(pod_lines) if pod_lines else "- no pods found"))
    except Exception as exc:
        sections.append(f"Pods:\n- failed to collect pod snapshot: {exc}")

    try:
        events = _run_kubectl(["get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "--no-headers"])
        event_lines = [line for line in events.splitlines() if line.strip()][:20]
        sections.append("Recent events:\n" + ("\n".join(f"- {line}" for line in event_lines) if event_lines else "- no recent events"))
    except Exception as exc:
        sections.append(f"Recent events:\n- failed to collect events: {exc}")

    return "\n\n".join(sections)


def summarize_namespace_pods(namespace: str) -> dict:
    payload = json.loads(_run_kubectl(["get", "pods", "-n", namespace, "-o", "json"]))
    summary = {
        "namespace": namespace,
        "pods": 0,
        "issues": 0,
        "restarts": 0,
        "pods_with_restarts": 0,
        "status_breakdown": {},
        "reason_breakdown": {},
        "problematic": [],
    }

    for item in payload.get("items", []):
        phase = item.get("status", {}).get("phase", "Unknown")
        container_statuses = item.get("status", {}).get("containerStatuses", []) or []
        restart_count = sum(cs.get("restartCount", 0) for cs in container_statuses)
        reason = _pod_reason(item)
        phase_key = _phase_key(phase)
        reason_key = _reason_key(phase_key, reason)

        summary["pods"] += 1
        summary["restarts"] += restart_count
        summary["status_breakdown"][phase_key] = summary["status_breakdown"].get(phase_key, 0) + 1
        if reason_key:
            summary["reason_breakdown"][reason_key] = summary["reason_breakdown"].get(reason_key, 0) + 1
        if restart_count > 0:
            summary["pods_with_restarts"] += 1

        has_issue = phase_key != "Completed" and (phase_key != "Running" or restart_count > 0 or reason_key is not None)
        if has_issue:
            summary["issues"] += 1
            name = item.get("metadata", {}).get("name", "unknown")
            summary["problematic"].append(
                {
                    "namespace": namespace,
                    "pod": name,
                    "phase": phase_key,
                    "restarts": restart_count,
                    "reason": reason_key or phase_key,
                    "status_key": phase_key,
                }
            )

    summary["problematic"].sort(
        key=lambda item: _severity_score(str(item["phase"]), str(item.get("reason")), int(item["restarts"])),
        reverse=True,
    )

    return summary


def list_namespaces() -> list[str]:
    payload = json.loads(_run_kubectl(["get", "namespaces", "-o", "json"]))
    return [item.get("metadata", {}).get("name", "") for item in payload.get("items", []) if item.get("metadata", {}).get("name")]


def resolve_target_namespaces(default_namespace: str, target_namespaces: str) -> list[str]:
    raw = (target_namespaces or "").strip()
    if not raw:
        return [default_namespace]
    if raw.lower() in {"all", "*"}:
        return list_namespaces()
    return [value.strip() for value in raw.split(",") if value.strip()]


def build_multi_namespace_snapshot(namespaces: list[str]) -> str:
    if len(namespaces) > 1:
        return build_cluster_overview_snapshot(namespaces)

    sections: list[str] = []
    for namespace in namespaces:
        sections.append(f"Namespace: {namespace}\n{build_namespace_snapshot(namespace)}")
    return "\n\n".join(sections)


def summarize_cluster_overview(namespaces: list[str]) -> dict:
    summary: dict[str, dict[str, int]] = {}
    problematic_lines: list[str] = []
    total_pods = 0
    total_issues = 0
    total_pods_with_restarts = 0
    status_breakdown: dict[str, int] = {}
    reason_breakdown: dict[str, int] = {}
    top_problematic_pods: list[dict] = []

    for namespace in namespaces:
        ns_summary = summarize_namespace_pods(namespace)
        summary[namespace] = {
            "pods": ns_summary["pods"],
            "issues": ns_summary["issues"],
            "restarts": ns_summary["restarts"],
        }
        total_pods += ns_summary["pods"]
        total_issues += ns_summary["issues"]
        total_pods_with_restarts += ns_summary["pods_with_restarts"]
        for status_key, count in ns_summary["status_breakdown"].items():
            status_breakdown[status_key] = status_breakdown.get(status_key, 0) + count
        for reason_key, count in ns_summary["reason_breakdown"].items():
            reason_breakdown[reason_key] = reason_breakdown.get(reason_key, 0) + count
        for item in ns_summary["problematic"]:
            top_problematic_pods.append(item)
            problematic_lines.append(
                f"- {item['namespace']}/{item['pod']}: phase={item['phase']}, restarts={item['restarts']}, reason={item['reason']}"
            )

    top_problematic_pods.sort(
        key=lambda item: _severity_score(str(item["phase"]), str(item.get("reason")), int(item["restarts"])),
        reverse=True,
    )

    return {
        "namespaces": namespaces,
        "summary": summary,
        "problematic_lines": problematic_lines,
        "pod_count": total_pods,
        "issue_count": total_issues,
        "pods_with_restarts": total_pods_with_restarts,
        "status_breakdown": status_breakdown,
        "reason_breakdown": reason_breakdown,
        "top_problematic_pods": top_problematic_pods,
    }


def build_cluster_overview_snapshot(namespaces: list[str]) -> str:
    overview = summarize_cluster_overview(namespaces)
    summary_lines = [f"- {ns}: pods={stats['pods']}, issues={stats['issues']}, restarts={stats['restarts']}" for ns, stats in sorted(overview['summary'].items())]
    issue_lines = overview["problematic_lines"][:40] if overview["problematic_lines"] else ["- no obvious unhealthy pods detected"]
    breakdown_lines = [f"- {status}: {count}" for status, count in sorted(overview["status_breakdown"].items())]
    reason_lines = [f"- {reason}: {count}" for reason, count in sorted(overview["reason_breakdown"].items())]

    return "\n\n".join(
        [
            "Namespaces scanned:\n" + "\n".join(f"- {ns}" for ns in sorted(overview['namespaces'])),
            f"Totals:\n- total_pods={overview['pod_count']}\n- issues={overview['issue_count']}\n- pods_with_restarts={overview['pods_with_restarts']}",
            "Status breakdown:\n" + ("\n".join(breakdown_lines) if breakdown_lines else "- no pod statuses recorded"),
            "Reason breakdown:\n" + ("\n".join(reason_lines) if reason_lines else "- no specific pod reasons recorded"),
            "Namespace summary:\n" + ("\n".join(summary_lines) if summary_lines else "- no pods found"),
            "Problematic pods:\n" + "\n".join(issue_lines),
        ]
    )


def _extract_namespace_from_query(query: str, default_namespace: str) -> str:
    lowered = query.lower()
    patterns = [
        r"namespace\s+([a-z0-9-]+)",
        r"([a-z0-9-]+)\s+namespace",
        r"([a-z0-9-]+)\s*네임스페이스",
        r"([a-z0-9-]+)의\s*(?:pod|pods|파드|deployment|deployments|서비스|service|namespace|네임스페이스)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return default_namespace


def _safe_section(title: str, args: list[str]) -> str:
    try:
        output = _run_kubectl(args).strip()
        return f"{title}:\n{output or '(no output)'}"
    except Exception as exc:
        return f"{title}:\nfailed to collect data: {exc}"


def build_interactive_snapshot(query: str, default_namespace: str) -> str:
    lowered = query.lower()
    namespace = _extract_namespace_from_query(query, default_namespace)
    sections: list[str] = []

    if "namespace" in lowered:
        sections.append(_safe_section("Namespaces", ["get", "namespaces", "-o", "wide"]))

    needs_pods = any(token in lowered for token in ["pod", "pods", "restart", "restarts", "crash", "error", "issue", "log", "logs", "deployment"])
    if needs_pods or not sections:
        sections.append(_safe_section(f"Pods in namespace {namespace}", ["get", "pods", "-n", namespace, "-o", "wide"]))

    needs_events = any(token in lowered for token in ["event", "events", "crash", "error", "issue", "restart"])
    if needs_events:
        sections.append(_safe_section(f"Recent events in namespace {namespace}", ["get", "events", "-n", namespace, "--sort-by=.lastTimestamp", "--no-headers"]))

    return "\n\n".join(sections)
