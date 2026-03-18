from __future__ import annotations

from typing import Any


def build_namespace_summary_rows(parent_run_id: int, cluster_overview: dict[str, Any], *, mode: str) -> list[dict[str, Any]]:
    summary = cluster_overview.get("summary", {}) if isinstance(cluster_overview, dict) else {}
    rows: list[dict[str, Any]] = []
    for namespace in sorted(summary):
        stats = summary[namespace]
        issues = int(stats.get("issues", 0) or 0)
        rows.append(
            {
                "parent_run_id": parent_run_id,
                "namespace": namespace,
                "mode": mode,
                "status": "issues_found" if issues > 0 else "ok",
                "pod_count": int(stats.get("pods", 0) or 0),
                "error_count": issues,
                "fix_count": 0,
                "summary": (
                    f"주의가 필요한 파드가 {issues}건 있습니다."
                    if issues > 0
                    else "조치가 필요한 이슈가 발견되지 않았습니다."
                ),
            }
        )
    return rows
