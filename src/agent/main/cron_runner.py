from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import aiohttp

try:
    from .cluster_snapshot import build_multi_namespace_snapshot, build_namespace_snapshot, resolve_target_namespaces, summarize_cluster_overview
    from .llm import calculate_cost, create_backend, resolve_llm_config, validate_llm_config
    from .report_utils import extract_report_payload, format_slack_scan_message, parse_run_report
    from .sessions import RunStore
except ImportError:
    from cluster_snapshot import build_multi_namespace_snapshot, build_namespace_snapshot, resolve_target_namespaces, summarize_cluster_overview
    from llm import calculate_cost, create_backend, resolve_llm_config, validate_llm_config
    from report_utils import extract_report_payload, format_slack_scan_message, parse_run_report
    from sessions import RunStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def load_prompt(prompt_file: str, replacements: dict[str, str]) -> str:
    prompt = Path(prompt_file).read_text()
    for key, value in replacements.items():
        prompt = prompt.replace(key, value)
    return prompt


async def send_slack_webhook(message: str) -> None:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "")
    if not webhook:
        logger.info("Slack notifications disabled (SLACK_WEBHOOK_URL not set)")
        return

    payload = {"text": message[:1500]}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(webhook, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Slack webhook failed: {response.status} {body[:500]}")


async def main() -> None:
    target_namespace = os.environ.get("TARGET_NAMESPACE", "default")
    target_namespaces = resolve_target_namespaces(target_namespace, os.environ.get("TARGET_NAMESPACES", ""))
    cluster_overview = summarize_cluster_overview(target_namespaces) if len(target_namespaces) > 1 else None
    sqlite_path = os.environ.get("SQLITE_PATH", "/data/lucas.db")
    sre_mode = os.environ.get("SRE_MODE", "autonomous")

    config = resolve_llm_config()
    validate_llm_config(config)
    backend = create_backend(config)

    logger.info("Starting Lucas cron runner")
    logger.info("Backend=%s provider=%s model=%s", config.backend, config.provider, config.model)
    logger.info("Target namespaces=%s sqlite=%s", target_namespaces, sqlite_path)

    run_store = RunStore(db_path=sqlite_path)
    await run_store.connect()

    run_scope = ",".join(target_namespaces) if len(target_namespaces) <= 5 else "all"
    run_id = await run_store.create_run(run_scope, mode=sre_mode)
    logger.info("Created run #%s", run_id)

    try:
        prompt_file = os.environ.get(
            "PROMPT_FILE",
            "/app/master-prompt-report.md" if sre_mode == "report" else "/app/master-prompt-autonomous.md",
        )
        last_run_time = ""
        if run_store._db is not None:
            async with run_store._db.execute(
                "SELECT COALESCE(MAX(ended_at), '') FROM runs WHERE namespace = ? AND status != 'running' AND id != ?",
                (run_scope, run_id),
            ) as cursor:
                row = await cursor.fetchone()
                last_run_time = row[0] if row and row[0] else ""

        prompt = load_prompt(
            prompt_file,
            {
                "$TARGET_NAMESPACE": target_namespace,
                "$SQLITE_PATH": sqlite_path,
                "$RUN_ID": str(run_id),
                "$LAST_RUN_TIME": last_run_time,
            },
        )

        if config.backend == "openai-compatible":
            snapshot = build_multi_namespace_snapshot(target_namespaces) if len(target_namespaces) > 1 else build_namespace_snapshot(target_namespace)
            prompt = (
                prompt
                + "\n\nUse the following Kubernetes snapshot as ground truth for your analysis. "
                + "Do not claim you ran tools that are not available in this backend. "
                + "Output only the required JSON report. Do not include shell transcripts, command echoes, or markdown code fences outside the report block. "
                + "Write the summary, issue descriptions, and recommendations in Korean.\n\n"
                + snapshot
            )

        if config.backend == "openai-compatible" and cluster_overview is not None:
            pod_count = cluster_overview["pod_count"]
            error_count = cluster_overview["issue_count"]
            fix_count = 0
            status = "issues_found" if error_count > 0 else "ok"
            pods_with_restarts = cluster_overview["pods_with_restarts"]
            status_breakdown = cluster_overview["status_breakdown"]
            reason_breakdown = cluster_overview["reason_breakdown"]
            top_problematic_pods = cluster_overview["top_problematic_pods"][:5]
            summary = (
                f"주의가 필요한 파드가 {error_count}건 있습니다."
                if error_count > 0
                else "조치가 필요한 이슈가 발견되지 않았습니다."
            )
            details = []
            for item in top_problematic_pods[:3]:
                details.append(
                    {
                        "pod": f"{item.get('namespace', '')}/{item.get('pod', '')}".strip("/"),
                        "issue": f"phase={item.get('phase', '')}, reason={item.get('reason', '')}, restarts={item.get('restarts', 0)}",
                    }
                )
            import json

            report = json.dumps(
                {
                    "scope": run_scope,
                    "run_id": run_id,
                    "status": status,
                    "total_pods": pod_count,
                    "pod_count": pod_count,
                    "issues": error_count,
                    "error_count": error_count,
                    "fix_count": 0,
                    "pods_with_restarts": pods_with_restarts,
                    "status_breakdown": status_breakdown,
                    "reason_breakdown": reason_breakdown,
                    "top_problematic_pods": top_problematic_pods,
                    "summary": summary,
                    "details": details,
                },
                ensure_ascii=False,
            )
            full_log = report
            result = {"input_tokens": 0, "output_tokens": 0, "model": config.model, "cost": 0.0}
        else:
            result = await backend.run(
                prompt=prompt,
                system_prompt="You are Lucas, an agent. Help monitor and fix Kubernetes issues.",
                session_id=None,
                context={"namespace": target_namespace},
            )

            report, full_log = extract_report_payload(result["text"])
            parsed_report = parse_run_report(report)
            pod_count = int(parsed_report["pod_count"])
            error_count = int(parsed_report["error_count"])
            fix_count = int(parsed_report["fix_count"])
            status = str(parsed_report["status"])
            summary = str(parsed_report["summary"])
            details = parsed_report["details"] if isinstance(parsed_report["details"], list) else []
            pods_with_restarts = int(parsed_report.get("pods_with_restarts", 0) or 0)
            status_breakdown = parsed_report.get("status_breakdown") if isinstance(parsed_report.get("status_breakdown"), dict) else {}
            reason_breakdown = parsed_report.get("reason_breakdown") if isinstance(parsed_report.get("reason_breakdown"), dict) else {}
            top_problematic_pods = parsed_report.get("top_problematic_pods") if isinstance(parsed_report.get("top_problematic_pods"), list) else []

        if cluster_overview is not None and config.backend != "openai-compatible":
            pod_count = cluster_overview["pod_count"]
            error_count = cluster_overview["issue_count"]
            pods_with_restarts = cluster_overview["pods_with_restarts"]
            status_breakdown = cluster_overview["status_breakdown"]
            reason_breakdown = cluster_overview["reason_breakdown"]
            top_problematic_pods = cluster_overview["top_problematic_pods"][:5]
            if error_count > 0:
                status = "issues_found"
                if not details:
                    details = []
                    for item in top_problematic_pods[:3]:
                        details.append(
                            {
                                "pod": f"{item.get('namespace', '')}/{item.get('pod', '')}".strip("/"),
                                "issue": f"phase={item.get('phase', '')}, reason={item.get('reason', '')}, restarts={item.get('restarts', 0)}",
                            }
                        )
                if not summary:
                    summary = f"주의가 필요한 파드가 {error_count}건 있습니다."
            elif status == "ok" and not summary:
                summary = "조치가 필요한 이슈가 발견되지 않았습니다."
        elif config.backend != "openai-compatible":
            pods_with_restarts = int(locals().get("pods_with_restarts", 0) or 0)
            status_breakdown = locals().get("status_breakdown", {}) if isinstance(locals().get("status_breakdown", {}), dict) else {}
            reason_breakdown = locals().get("reason_breakdown", {}) if isinstance(locals().get("reason_breakdown", {}), dict) else {}
            top_problematic_pods = locals().get("top_problematic_pods", []) if isinstance(locals().get("top_problematic_pods", []), list) else []

        cost = result.get("cost", 0.0)
        if not cost and config.backend == "claude-code":
            cost = calculate_cost(
                result.get("model", config.model),
                result.get("input_tokens", 0),
                result.get("output_tokens", 0),
            )

        if result.get("input_tokens") or result.get("output_tokens"):
            await run_store.record_token_usage(
                run_id=run_id,
                namespace=run_scope,
                model=result.get("model", config.model),
                input_tokens=result.get("input_tokens", 0),
                output_tokens=result.get("output_tokens", 0),
                cost=cost,
            )

        await run_store.update_run(
            run_id=run_id,
            status=status,
            pod_count=pod_count,
            error_count=error_count,
            fix_count=fix_count,
            report=report[:5000] if report else None,
            log=full_log[:100000] if full_log else None,
        )

        await send_slack_webhook(
            format_slack_scan_message(
                status=status,
                namespace=run_scope,
                run_id=run_id,
                summary=summary,
                pod_count=pod_count,
                error_count=error_count,
                details=details,
                pods_with_restarts=pods_with_restarts,
                status_breakdown=status_breakdown,
                reason_breakdown=reason_breakdown,
                top_problematic_pods=top_problematic_pods,
            )
        )
        logger.info("Run #%s completed with status=%s", run_id, status)
    except Exception as exc:
        logger.error("Cron runner failed: %s", exc, exc_info=True)
        await run_store.update_run(run_id=run_id, status="failed", report=str(exc))
        raise
    finally:
        await run_store.close()


if __name__ == "__main__":
    asyncio.run(main())
