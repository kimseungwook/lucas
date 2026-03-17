from __future__ import annotations

import asyncio
import importlib
import logging
import os
import json
from pathlib import Path
from typing import Any, cast

try:
    from .cluster_snapshot import build_multi_namespace_snapshot, build_namespace_snapshot, resolve_target_namespaces, summarize_cluster_overview
    from .drift_auditor import build_drift_audit_result, collect_runtime_drift_inputs
    from .redis_recovery import build_redis_recovery_result, collect_redis_recovery_inputs
    from .llm import calculate_cost, create_backend, resolve_llm_config, validate_llm_config
    from .report_utils import extract_report_payload, format_slack_scan_message, parse_run_report
    from .sessions import RunStore
except ImportError:
    cluster_snapshot = importlib.import_module("cluster_snapshot")
    drift_auditor = importlib.import_module("drift_auditor")
    redis_recovery = importlib.import_module("redis_recovery")
    llm = importlib.import_module("llm")
    report_utils = importlib.import_module("report_utils")
    sessions = importlib.import_module("sessions")

    build_multi_namespace_snapshot = cluster_snapshot.build_multi_namespace_snapshot
    build_namespace_snapshot = cluster_snapshot.build_namespace_snapshot
    resolve_target_namespaces = cluster_snapshot.resolve_target_namespaces
    summarize_cluster_overview = cluster_snapshot.summarize_cluster_overview

    build_drift_audit_result = drift_auditor.build_drift_audit_result
    collect_runtime_drift_inputs = drift_auditor.collect_runtime_drift_inputs

    build_redis_recovery_result = redis_recovery.build_redis_recovery_result
    collect_redis_recovery_inputs = redis_recovery.collect_redis_recovery_inputs

    calculate_cost = llm.calculate_cost
    create_backend = llm.create_backend
    resolve_llm_config = llm.resolve_llm_config
    validate_llm_config = llm.validate_llm_config

    extract_report_payload = report_utils.extract_report_payload
    format_slack_scan_message = report_utils.format_slack_scan_message
    parse_run_report = report_utils.parse_run_report

    RunStore = sessions.RunStore

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
    aiohttp = importlib.import_module("aiohttp")

    payload = {"text": message[:1500]}
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        async with session.post(webhook, json=payload) as response:
            if response.status >= 400:
                body = await response.text()
                raise RuntimeError(f"Slack webhook failed: {response.status} {body[:500]}")


def build_stored_report_payload(
    *,
    run_scope: str,
    run_id: int,
    status: str,
    pod_count: int,
    error_count: int,
    fix_count: int,
    summary: str,
    details: list[dict[str, Any]],
    pods_with_restarts: int,
    status_breakdown: dict[str, Any],
    reason_breakdown: dict[str, Any],
    top_problematic_pods: list[dict[str, Any]],
    drift_audit: dict[str, Any] | None = None,
    redis_recovery: dict[str, Any] | None = None,
) -> str:
    drift_audit = drift_audit or {"drift_summary": {}, "drifts": []}
    redis_recovery = redis_recovery or {"redis_recovery_summary": {}, "redis_recovery_findings": []}
    return json.dumps(
        {
            "scope": run_scope,
            "run_id": run_id,
            "status": status,
            "total_pods": pod_count,
            "pod_count": pod_count,
            "issues": error_count,
            "error_count": error_count,
            "fix_count": fix_count,
            "pods_with_restarts": pods_with_restarts,
            "status_breakdown": status_breakdown,
            "reason_breakdown": reason_breakdown,
            "top_problematic_pods": top_problematic_pods,
            "summary": summary,
            "details": details,
            "drift_summary": drift_audit.get("drift_summary", {}),
            "drifts": drift_audit.get("drifts", []),
            "redis_recovery_summary": redis_recovery.get("redis_recovery_summary", {}),
            "redis_recovery_findings": redis_recovery.get("redis_recovery_findings", []),
        },
        ensure_ascii=False,
    )


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

        try:
            drift_inputs = collect_runtime_drift_inputs()
            drift_audit = build_drift_audit_result(**drift_inputs)
        except Exception as drift_exc:
            logger.warning("Drift audit skipped: %s", drift_exc)
            drift_audit = {"status": "ok", "drift_summary": {}, "drifts": []}

        raw_drift_summary = drift_audit.get("drift_summary", {}) if isinstance(drift_audit, dict) else {}
        raw_drifts = drift_audit.get("drifts", []) if isinstance(drift_audit, dict) else []
        drift_summary: dict[str, Any] = raw_drift_summary if isinstance(raw_drift_summary, dict) else {}
        drifts: list[Any] = list(raw_drifts) if isinstance(raw_drifts, list) else []

        redis_self_heal_enabled = os.environ.get("REDIS_SELF_HEAL_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}
        redis_self_heal_mutations_allowed = os.environ.get("REDIS_SELF_HEAL_MUTATIONS_ALLOWED", "false").strip().lower() in {"1", "true", "yes", "on"}
        redis_allowed_environments = [value.strip() for value in os.environ.get("REDIS_SELF_HEAL_ALLOWED_ENVIRONMENTS", "dev").split(",") if value.strip()]
        current_environment = os.environ.get("LUCAS_ENVIRONMENT", "")
        redis_cooldown_seconds = int(os.environ.get("REDIS_SELF_HEAL_COOLDOWN_SECONDS", "600") or "600")

        redis_inputs = collect_redis_recovery_inputs(target_namespaces)
        recent_actions: dict[str, dict[str, Any]] = {}
        for item in redis_inputs:
            workload = item.get("workload", {})
            latest_action = await run_store.get_latest_recovery_action(
                str(workload.get("namespace", "")),
                str(workload.get("kind", "")),
                str(workload.get("name", "")),
            )
            if latest_action:
                from datetime import datetime, timezone
                try:
                    ts = int(datetime.strptime(latest_action["created_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp())
                except Exception:
                    ts = 0
                recent_actions[f"{workload.get('namespace','')}/{workload.get('kind','')}/{workload.get('name','')}"] = {"timestamp": ts, **latest_action}

        def execute_delete(namespace: str, pod_name: str) -> str:
            import subprocess
            command = ["kubectl"]
            context = os.environ.get("KUBECTL_CONTEXT", "").strip()
            if context:
                command.extend(["--context", context])
            command.extend(["delete", "pod", pod_name, "-n", namespace])
            result = subprocess.run(command, capture_output=True, text=True)
            output = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
            if result.returncode != 0:
                raise RuntimeError(output or f"kubectl failed with exit code {result.returncode}")
            return output or f"Deleted pod {namespace}/{pod_name}"

        redis_recovery = build_redis_recovery_result(
            redis_inputs,
            auto_delete_enabled=redis_self_heal_enabled,
            mutations_allowed=redis_self_heal_mutations_allowed,
            current_environment=current_environment,
            allowed_environments=redis_allowed_environments,
            cooldown_seconds=redis_cooldown_seconds,
            recent_actions=recent_actions,
            action_executor=execute_delete,
        )
        for finding in redis_recovery.get("redis_recovery_findings", []):
            if finding.get("action") == "delete_pod":
                workload_text = str(finding.get("workload", "unknown/unknown"))
                workload_kind, workload_name = (workload_text.split("/", 1) + [""])[:2]
                await run_store.record_recovery_action(
                    namespace=str(finding.get("namespace", "")),
                    workload_kind=workload_kind,
                    workload_name=workload_name,
                    pod_name=str(finding.get("target_pod", "")) or None,
                    action="delete_pod",
                    status="executed",
                    reason=str(finding.get("likely_cause", "")) or None,
                )

        raw_redis_summary = redis_recovery.get("redis_recovery_summary", {}) if isinstance(redis_recovery, dict) else {}
        raw_redis_findings = redis_recovery.get("redis_recovery_findings", []) if isinstance(redis_recovery, dict) else []
        redis_recovery_summary: dict[str, Any] = raw_redis_summary if isinstance(raw_redis_summary, dict) else {}
        redis_recovery_findings: list[Any] = list(raw_redis_findings) if isinstance(raw_redis_findings, list) else []

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
            report = build_stored_report_payload(
                run_scope=run_scope,
                run_id=run_id,
                status=status,
                pod_count=pod_count,
                error_count=error_count,
                fix_count=0,
                summary=summary,
                details=details,
                pods_with_restarts=pods_with_restarts,
                status_breakdown=status_breakdown,
                reason_breakdown=reason_breakdown,
                top_problematic_pods=top_problematic_pods,
                drift_audit=cast(dict[str, Any], drift_audit),
                redis_recovery=cast(dict[str, Any], redis_recovery),
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
            parsed_drift_summary = parsed_report.get("drift_summary")
            parsed_drifts = parsed_report.get("drifts")
            drift_summary = parsed_drift_summary if isinstance(parsed_drift_summary, dict) else drift_summary
            drifts = list(parsed_drifts) if isinstance(parsed_drifts, list) else drifts
            parsed_redis_summary = parsed_report.get("redis_recovery_summary")
            parsed_redis_findings = parsed_report.get("redis_recovery_findings")
            redis_recovery_summary = parsed_redis_summary if isinstance(parsed_redis_summary, dict) else redis_recovery_summary
            redis_recovery_findings = list(parsed_redis_findings) if isinstance(parsed_redis_findings, list) else redis_recovery_findings

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

        if config.backend == "openai-compatible":
            raw_drift_summary = drift_audit.get("drift_summary", {}) if isinstance(drift_audit, dict) else {}
            raw_drifts = drift_audit.get("drifts", []) if isinstance(drift_audit, dict) else []
            drift_summary = raw_drift_summary if isinstance(raw_drift_summary, dict) else {}
            drifts = list(raw_drifts) if isinstance(raw_drifts, list) else []

        status_breakdown = status_breakdown if isinstance(status_breakdown, dict) else {}
        reason_breakdown = reason_breakdown if isinstance(reason_breakdown, dict) else {}
        top_problematic_pods = top_problematic_pods if isinstance(top_problematic_pods, list) else []
        drift_summary = drift_summary if isinstance(drift_summary, dict) else {}
        drifts = drifts if isinstance(drifts, list) else []
        redis_recovery_summary = redis_recovery_summary if isinstance(redis_recovery_summary, dict) else {}
        redis_recovery_findings = redis_recovery_findings if isinstance(redis_recovery_findings, list) else []

        report = build_stored_report_payload(
            run_scope=run_scope,
            run_id=run_id,
            status=status,
            pod_count=pod_count,
            error_count=error_count,
            fix_count=fix_count,
            summary=summary,
            details=details,
            pods_with_restarts=pods_with_restarts,
            status_breakdown=status_breakdown,
            reason_breakdown=reason_breakdown,
            top_problematic_pods=top_problematic_pods,
            drift_audit={"drift_summary": drift_summary, "drifts": drifts},
            redis_recovery={"redis_recovery_summary": redis_recovery_summary, "redis_recovery_findings": redis_recovery_findings},
        )

        cost = result.get("cost", 0.0)
        if not cost and config.backend == "claude-code":
            cost = calculate_cost(
                str(result.get("model", config.model)),
                int(result.get("input_tokens", 0) or 0),
                int(result.get("output_tokens", 0) or 0),
            )

        model_name = str(result.get("model", config.model))
        input_tokens = int(result.get("input_tokens", 0) or 0)
        output_tokens = int(result.get("output_tokens", 0) or 0)
        numeric_cost = float(cost or 0.0)

        if input_tokens or output_tokens:
            await run_store.record_token_usage(
                run_id=run_id,
                namespace=run_scope,
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=numeric_cost,
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
                drift_summary=drift_summary,
                drifts=cast(list[dict[str, Any]], drifts),
                redis_recovery_summary=cast(dict[str, int], redis_recovery_summary),
                redis_recovery_findings=cast(list[dict[str, Any]], redis_recovery_findings),
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
