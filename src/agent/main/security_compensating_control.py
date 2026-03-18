from __future__ import annotations

from typing import Any, TypedDict, cast


class SecuritySuspicionFinding(TypedDict):
    type: str
    namespace: str
    severity: str
    resource: str
    evidence: list[str]
    likely_scenario: str
    impact_scope: str
    recommended_actions: list[str]
    category: str


class SecuritySuspicionResult(TypedDict):
    status: str
    control_mode: str
    security_suspicion_summary: dict[str, int]
    security_suspicion_findings: list[SecuritySuspicionFinding]


CATEGORY_MAP = {
    "suspicious_outbound_abuse": {
        "keywords": ["egress", "destination", "curl", "wget", "outbound", "external"],
        "likely_scenario": "Possible outbound abuse or payload staging behavior.",
    },
    "suspicious_credential_or_secret_use": {
        "keywords": ["secret", "service account", "serviceaccount", "token", "credential"],
        "likely_scenario": "Possible credential or secret misuse within the workload boundary.",
    },
    "suspicious_control_plane_interaction": {
        "keywords": ["exec", "kubectl", "clusterrole", "rolebinding", "daemonset", "privileged"],
        "likely_scenario": "Possible suspicious control-plane or administrative interaction.",
    },
    "suspicious_data_plane_abuse": {
        "keywords": ["redis", "database", "postgres", "mysql", "bucket", "object storage", "queue", "kafka", "rabbitmq", "cache"],
        "likely_scenario": "Possible suspicious access to downstream data-plane services.",
    },
    "suspicious_rollout_context_mismatch": {
        "keywords": ["image", "tag", "digest", "rollout", "pull secret"],
        "likely_scenario": "Possible suspicious change or mismatch in rollout or image context.",
    },
}


def _classify_text(text: str) -> str | None:
    lowered = text.lower()
    for category, definition in CATEGORY_MAP.items():
        if any(keyword in lowered for keyword in definition["keywords"]):
            return category
    return None


def build_security_suspicion_result(signal_bundle: dict[str, Any]) -> SecuritySuspicionResult:
    summary = {"findings": 0, "high": 0, "medium": 0, "evaluated_namespaces": 0}
    if not signal_bundle.get("enabled"):
        return {
            "status": "ok",
            "control_mode": "compensating_control",
            "security_suspicion_summary": summary,
            "security_suspicion_findings": [],
        }

    summary["evaluated_namespaces"] = len(signal_bundle.get("monitored_namespaces", []))
    grouped: dict[str, dict[str, Any]] = {}

    for report in signal_bundle.get("policy_reports", []):
        text = f"{report.get('category', '')} {report.get('message', '')} {report.get('policy', '')}"
        category = _classify_text(text)
        if not category:
            continue
        key = report["namespace"]
        entry = grouped.setdefault(
            key,
            {
                "namespace": report["namespace"],
                "categories": set(),
                "severity_inputs": [],
                "resource": f"PolicyReport/{report.get('report_name', 'unknown')}",
                "evidence": [],
            },
        )
        entry["categories"].add(category)
        entry["severity_inputs"].append(str(report.get("severity", "medium")).lower())
        if report.get("message"):
            entry["evidence"].append(str(report["message"]))

    for event in signal_bundle.get("events", []):
        category = _classify_text(str(event.get("message", "")))
        if not category:
            continue
        key = event["namespace"]
        entry = grouped.setdefault(
            key,
            {
                "namespace": event["namespace"],
                "categories": set(),
                "severity_inputs": [],
                "resource": event.get("resource", "resource/unknown"),
                "evidence": [],
            },
        )
        entry["categories"].add(category)
        entry["severity_inputs"].append("medium")
        if event.get("message"):
            entry["evidence"].append(str(event["message"]))

    findings: list[SecuritySuspicionFinding] = []
    for _namespace, item in grouped.items():
        evidence = list(dict.fromkeys(item["evidence"]))
        severity = "high" if ("high" in item["severity_inputs"] or len(evidence) >= 2) else "medium"
        categories = sorted(item["categories"])
        primary_category = categories[0] if categories else "suspicious_rollout_context_mismatch"
        likely_scenario = (
            "Possible multi-signal suspicious behavior within the monitored namespace."
            if len(categories) > 1
            else CATEGORY_MAP[primary_category]["likely_scenario"]
        )
        summary["findings"] += 1
        summary[severity] += 1
        findings.append(
            cast(
                SecuritySuspicionFinding,
                cast(
                    object,
                {
                    "type": "security.suspicious_behavior",
                    "namespace": str(item["namespace"]),
                    "severity": severity,
                    "resource": str(item["resource"]),
                    "evidence": evidence,
                    "likely_scenario": str(likely_scenario),
                    "impact_scope": "namespace-scoped workload/data-plane risk",
                    "recommended_actions": [
                        "Review the raw evidence and recent rollout context.",
                        "Validate the workload identity, secret usage, and outbound destinations.",
                        "Apply containment only through an approved operator workflow if the finding is confirmed.",
                    ],
                    "category": ",".join(categories),
                },
                ),
            )
        )

    return {
        "status": "issues_found" if findings else "ok",
        "control_mode": "compensating_control",
        "security_suspicion_summary": summary,
        "security_suspicion_findings": findings,
    }
