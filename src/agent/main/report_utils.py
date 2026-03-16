from __future__ import annotations

import json
import re
from typing import Any


def extract_report_payload(response: str) -> tuple[str, str]:
    full_log = response.strip()
    if "===REPORT_START===" in response and "===REPORT_END===" in response:
        report = response.split("===REPORT_START===", 1)[1].split("===REPORT_END===", 1)[0].strip()
        report = report.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return report, full_log
    return full_log, full_log


def _sanitize_summary(summary: str) -> str:
    compact = re.sub(r"\s+", " ", summary or "").strip()
    if not compact:
        return ""

    if compact.startswith("{") and '"pod_count"' in compact:
        return ""

    suspicious = ["bash ", "kubectl ", "sqlite3 ", "output:", "first, we'll", "###", "```"]
    if any(token in compact.lower() for token in suspicious):
        return ""
    return compact[:300]


def parse_run_report(report: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {
        "pod_count": 0,
        "error_count": 0,
        "fix_count": 0,
        "status": "ok",
        "summary": report.strip(),
        "details": [],
        "pods_with_restarts": 0,
        "status_breakdown": {},
        "reason_breakdown": {},
        "top_problematic_pods": [],
        "drift_summary": {},
        "drifts": [],
    }

    try:
        payload = json.loads(report)
        parsed["pod_count"] = int(payload.get("pod_count", 0) or 0)
        parsed["error_count"] = int(payload.get("error_count", 0) or 0)
        parsed["fix_count"] = int(payload.get("fix_count", 0) or 0)
        parsed["status"] = str(payload.get("status", "ok") or "ok")
        if "summary" in payload:
            parsed["summary"] = str(payload.get("summary") or "")
        details = payload.get("details") or []
        parsed["details"] = details if isinstance(details, list) else []
        parsed["pods_with_restarts"] = int(payload.get("pods_with_restarts", 0) or 0)
        status_breakdown = payload.get("status_breakdown") or {}
        parsed["status_breakdown"] = status_breakdown if isinstance(status_breakdown, dict) else {}
        reason_breakdown = payload.get("reason_breakdown") or {}
        parsed["reason_breakdown"] = reason_breakdown if isinstance(reason_breakdown, dict) else {}
        top_problematic = payload.get("top_problematic_pods") or []
        parsed["top_problematic_pods"] = top_problematic if isinstance(top_problematic, list) else []
        drift_summary = payload.get("drift_summary") or {}
        parsed["drift_summary"] = drift_summary if isinstance(drift_summary, dict) else {}
        drifts = payload.get("drifts") or []
        parsed["drifts"] = drifts if isinstance(drifts, list) else []
        if not parsed["details"] and parsed["top_problematic_pods"]:
            parsed["details"] = [
                {
                    "pod": f"{item.get('namespace', '')}/{item.get('pod', '')}".strip("/"),
                    "issue": f"phase={item.get('phase', '')}, reason={item.get('reason', '')}, restarts={item.get('restarts', 0)}",
                }
                for item in parsed["top_problematic_pods"][:3]
                if isinstance(item, dict)
            ]
        return parsed
    except json.JSONDecodeError:
        pass

    lowered = report.lower()
    if any(pattern in lowered for pattern in ["crashloopbackoff", "imagepullbackoff", "oomkilled", "critical", "urgent", "failed"]):
        parsed["error_count"] = 1
        parsed["status"] = "issues_found"

    pod_match = re.search(r"(\d+)\s*pods?", lowered)
    if pod_match:
        parsed["pod_count"] = int(pod_match.group(1))

    return parsed


def format_slack_scan_message(
    *,
    status: str,
    namespace: str,
    run_id: int,
    summary: str,
    pod_count: int,
    error_count: int,
    details: list[dict[str, Any]],
    pods_with_restarts: int = 0,
    status_breakdown: dict[str, int] | None = None,
    reason_breakdown: dict[str, int] | None = None,
    top_problematic_pods: list[dict[str, Any]] | None = None,
    drift_summary: dict[str, int] | None = None,
    drifts: list[dict[str, Any]] | None = None,
) -> str:
    lines = [
        "*Lucas 정기 점검*",
        f"scope={namespace} run={run_id}",
    ]

    if pod_count:
        stats_line = f"total_pods={pod_count} issues={error_count}"
        if pods_with_restarts:
            stats_line += f" pods_with_restarts={pods_with_restarts}"
        lines.append(stats_line)

    if status_breakdown:
        lines.append("status_breakdown")
        preferred_order = ["Running", "Pending", "Failed", "Completed", "Unknown"]
        ordered_keys = [key for key in preferred_order if key in status_breakdown] + [key for key in sorted(status_breakdown) if key not in preferred_order]
        for key in ordered_keys:
            value = status_breakdown[key]
            lines.append(f"- {key}: {value}")

    if reason_breakdown:
        lines.append("reason_breakdown")
        for key in sorted(reason_breakdown):
            lines.append(f"- {key}: {reason_breakdown[key]}")

    if drift_summary:
        lines.append("drift_summary")
        for key in sorted(drift_summary):
            lines.append(f"- {key}: {drift_summary[key]}")

    drift_items = drifts or []
    if drift_items:
        lines.append("top_drifts")
        for item in drift_items[:3]:
            if not isinstance(item, dict):
                continue
            drift_type = str(item.get("type") or "unknown-drift")
            severity = str(item.get("severity") or "")
            resource = str(item.get("resource") or "")
            likely_cause = str(item.get("likely_cause") or "")
            prefix = f"- [{severity}] {drift_type}" if severity else f"- {drift_type}"
            if resource:
                prefix += f" @ {resource}"
            if likely_cause:
                prefix += f": {likely_cause}"
            lines.append(prefix[:300])

    clean_summary = _sanitize_summary(summary)
    problematic = top_problematic_pods or []
    if problematic:
        lines.append("top_problematic_pods")
        for item in problematic[:5]:
            if not isinstance(item, dict):
                continue
            namespace_name = str(item.get("namespace") or "")
            pod = str(item.get("pod") or "unknown-pod")
            phase = str(item.get("phase") or "")
            reason = str(item.get("reason") or "")
            restarts = int(item.get("restarts", 0) or 0)
            lines.append(f"- {namespace_name}/{pod}: {phase} / {reason} / restarts={restarts}")

    elif details:
        lines.append("top_problematic_pods")
        for detail in details[:3]:
            if not isinstance(detail, dict):
                continue
            pod = str(detail.get("pod") or "unknown-pod")
            issue = str(detail.get("issue") or "Issue detected")
            severity = str(detail.get("severity") or "")
            recommendation = str(detail.get("recommendation") or "")
            line = f"- {pod}: {issue}"
            if severity:
                line += f" [{severity}]"
            if recommendation:
                line += f" | 조치: {recommendation}"
            lines.append(line[:300])

    lines.append("summary")
    if clean_summary:
        lines.append(clean_summary)
    elif status == "ok":
        lines.append("조치가 필요한 이슈가 발견되지 않았습니다.")
    elif error_count:
        lines.append(f"주의가 필요한 파드가 {error_count}건 있습니다.")
    else:
        lines.append("자세한 내용은 Lucas 대시보드를 확인하세요.")

    return "\n".join(lines)[:1500]
