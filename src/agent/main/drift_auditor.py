from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, TypedDict


class DriftFinding(TypedDict):
    type: str
    severity: str
    resource: str
    evidence: list[str]
    likely_cause: str
    recommended_actions: list[str]


class DriftAuditResult(TypedDict):
    status: str
    drift_summary: dict[str, int]
    drifts: list[DriftFinding]


def _kubectl_base_command() -> list[str]:
    command = ["kubectl"]
    context = os.environ.get("KUBECTL_CONTEXT", "").strip()
    if context:
        command.extend(["--context", context])
    return command


def _run_kubectl_json(args: list[str]) -> dict[str, Any]:
    result = subprocess.run(
        _kubectl_base_command() + args,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout)


def _safe_run_kubectl_json(args: list[str], resource: str, input_errors: list[str], default: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        return _run_kubectl_json(args)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        input_errors.append(f"{resource}: {detail}")
        return default or {}


def _serviceaccount_namespace() -> str:
    namespace_file = Path("/var/run/secrets/kubernetes.io/serviceaccount/namespace")
    if namespace_file.exists():
        return namespace_file.read_text().strip()
    return os.environ.get("LUCAS_NAMESPACE", os.environ.get("TARGET_NAMESPACE", "default"))


def _get_container_env(resource: dict[str, Any], cronjob: bool = False) -> list[dict[str, Any]]:
    if cronjob:
        containers = (
            resource.get("spec", {})
            .get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
    else:
        containers = (
            resource.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
    return containers[0].get("env", []) if containers else []


def _get_container_image(resource: dict[str, Any], cronjob: bool = False) -> str:
    if cronjob:
        containers = (
            resource.get("spec", {})
            .get("jobTemplate", {})
            .get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
    else:
        containers = (
            resource.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
    return str(containers[0].get("image", "")) if containers else ""


def _extract_env_map(env_list: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    env_map: dict[str, dict[str, str]] = {}
    for item in env_list or []:
        name = item.get("name")
        if not name:
            continue
        value = item.get("value")
        ref = item.get("valueFrom", {}).get("secretKeyRef") or {}
        env_map[str(name)] = {
            "value": str(value) if value is not None else "",
            "secret_name": str(ref.get("name", "")),
            "secret_key": str(ref.get("key", "")),
        }
    return env_map


def _provider_from_env(env_map: dict[str, dict[str, str]]) -> str:
    return env_map.get("LLM_PROVIDER", {}).get("value", "").strip().lower()


def _expected_secret_env(provider: str) -> str:
    return {
        "openrouter": "OPENROUTER_API_KEY",
        "gemini": "GEMINI_API_KEY",
        "groq": "GROQ_API_KEY",
        "kimi": "KIMI_API_KEY",
    }.get(provider, "LLM_API_KEY")


def _selected_nodes(pvcs: list[dict[str, Any]] | None) -> list[str]:
    nodes: list[str] = []
    for pvc in pvcs or []:
        node = pvc.get("metadata", {}).get("annotations", {}).get("volume.kubernetes.io/selected-node")
        if node:
            nodes.append(str(node))
    return nodes


def _event_messages(events: list[dict[str, Any]] | None) -> list[str]:
    messages: list[str] = []
    for event in events or []:
        message = event.get("message")
        if message:
            messages.append(str(message))
    return messages


def _runtime_surface_drift(configmaps: dict[str, dict[str, str]] | None, deployment_image: str, cron_image: str) -> DriftFinding | None:
    configmaps = configmaps or {}
    agent_code = configmaps.get("lucas-agent-code") or {}
    cron_code = configmaps.get("lucas-cron-code") or {}

    if agent_code or cron_code:
        keys_to_compare = ["llm.py", "report_utils.py", "cluster_snapshot.py"]
        evidence: list[str] = []
        for key in keys_to_compare:
            if key in agent_code and key in cron_code and agent_code[key] != cron_code[key]:
                evidence.append(f"ConfigMap content mismatch for {key}")
        if evidence:
            return {
                "type": "code.runtime_surface_mismatch",
                "severity": "medium",
                "resource": "configmap/lucas-agent-code,configmap/lucas-cron-code",
                "evidence": evidence,
                "likely_cause": "Interactive and scheduled Lucas runtimes are mounted from different code surfaces.",
                "recommended_actions": [
                    "Refresh both runtime ConfigMaps from the same repo revision.",
                    "Restart the interactive deployment and rerun a one-off cron smoke job.",
                ],
            }
        return None

    if deployment_image and cron_image and deployment_image != cron_image:
        return {
            "type": "code.runtime_surface_mismatch",
            "severity": "medium",
            "resource": "deployment/a2w-lucas-agent,cronjob/a2w-lucas",
            "evidence": [f"deployment image={deployment_image}", f"cronjob image={cron_image}"],
            "likely_cause": "Interactive and scheduled Lucas runtimes are running different container images.",
            "recommended_actions": [
                "Align the deployment and cronjob image/tag or digest.",
                "Re-run both interactive and cron smoke tests after aligning the images.",
            ],
        }
    return None


def build_drift_audit_result(
    *,
    deployment: dict[str, Any] | None = None,
    cronjob: dict[str, Any] | None = None,
    deployment_pod: dict[str, Any] | None = None,
    cronjob_pod: dict[str, Any] | None = None,
    deployment_events: list[dict[str, Any]] | None = None,
    cronjob_events: list[dict[str, Any]] | None = None,
    pvcs: list[dict[str, Any]] | None = None,
    pvs: list[dict[str, Any]] | None = None,
    nodes: dict[str, dict[str, Any]] | None = None,
    configmaps: dict[str, dict[str, str]] | None = None,
    input_errors: list[str] | None = None,
) -> DriftAuditResult:
    del pvs, nodes
    findings: list[DriftFinding] = []
    summary = {"storage": 0, "code": 0, "runtime": 0}

    if input_errors:
        severity = "high" if any("forbidden" in item.lower() or "not found" in item.lower() for item in input_errors) else "medium"
        findings.append(
            {
                "type": "runtime.input_collection_failed",
                "severity": severity,
                "resource": "runtime-drift-inputs",
                "evidence": list(input_errors[:5]),
                "likely_cause": "The drift auditor could not collect all of the runtime inputs it needs, usually because of RBAC gaps or missing runtime resources.",
                "recommended_actions": [
                    "Verify the Lucas service account can read the runtime resources the drift auditor expects.",
                    "Verify the expected deployment, cronjob, PVC, and ConfigMap objects exist in the target namespace.",
                ],
            }
        )
        summary["runtime"] += 1

    selected_nodes = _selected_nodes(pvcs)
    deployment_node = deployment_pod.get("spec", {}).get("nodeName") if deployment_pod else None
    cron_node = cronjob_pod.get("spec", {}).get("nodeName") if cronjob_pod else None
    storage_messages = _event_messages(deployment_events) + _event_messages(cronjob_events)
    attach_errors = [m for m in storage_messages if "AttachVolume.Attach failed" in m or "paravirtualized" in m.lower()]
    if selected_nodes and attach_errors:
        actual_node = str(deployment_node or cron_node or "")
        selected = str(selected_nodes[0])
        if actual_node and actual_node != selected:
            findings.append(
                {
                    "type": "storage.node_placement_mismatch",
                    "severity": "high",
                    "resource": "deployment/a2w-lucas-agent" if deployment_node else "cronjob/a2w-lucas",
                    "evidence": [attach_errors[0], f"selected-node={selected}", f"scheduled-node={actual_node}"],
                    "likely_cause": "The workload landed on a node that does not match the PVC-selected storage lineage.",
                    "recommended_actions": [
                        "Pin the workload to the validated node pool or matching node label set.",
                        "Recreate the pod after updating placement.",
                        "Avoid changing storage placement and provider config in the same rollout step.",
                    ],
                }
            )
            summary["storage"] += 1
        else:
            findings.append(
                {
                    "type": "storage.attach_failure",
                    "severity": "high",
                    "resource": "deployment/a2w-lucas-agent" if deployment_node else "cronjob/a2w-lucas",
                    "evidence": attach_errors[:2],
                    "likely_cause": "The workload is blocked by an OCI volume attachment failure.",
                    "recommended_actions": [
                        "Inspect the PVC/PV and node placement relationship.",
                        "Confirm the storage class and attachment mode are compatible with the target node pool.",
                    ],
                }
            )
            summary["storage"] += 1

    deployment_env = _extract_env_map(_get_container_env(deployment or {}, cronjob=False))
    cronjob_env = _extract_env_map(_get_container_env(cronjob or {}, cronjob=True))
    deployment_provider = _provider_from_env(deployment_env)
    cronjob_provider = _provider_from_env(cronjob_env)

    deployment_image = _get_container_image(deployment or {}, cronjob=False)
    cronjob_image = _get_container_image(cronjob or {}, cronjob=True)

    code_finding = _runtime_surface_drift(configmaps, deployment_image, cronjob_image)
    if code_finding:
        findings.append(code_finding)
        summary["code"] += 1

    selected_provider = deployment_provider or cronjob_provider
    llm_py = ((configmaps or {}).get("lucas-agent-code") or {}).get("llm.py") or ((configmaps or {}).get("lucas-cron-code") or {}).get("llm.py")
    if selected_provider and llm_py and selected_provider not in llm_py.lower():
        findings.append(
            {
                "type": "code.provider_support_missing",
                "severity": "high",
                "resource": "configmap/lucas-agent-code",
                "evidence": [f"selected provider={selected_provider}", f"mounted llm.py missing branch for {selected_provider}"],
                "likely_cause": "Runtime code does not contain the provider branch required by the selected environment.",
                "recommended_actions": [
                    "Refresh the mounted runtime ConfigMap from the intended repo revision.",
                    "Restart the workload after updating the ConfigMap.",
                ],
            }
        )
        summary["code"] += 1

    if deployment and cronjob:
        mismatches: list[str] = []
        for key in ("LLM_BACKEND", "LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL"):
            dep_value = deployment_env.get(key, {}).get("value", "")
            cron_value = cronjob_env.get(key, {}).get("value", "")
            if dep_value != cron_value:
                mismatches.append(f"{key}: deployment={dep_value or '<empty>'}, cronjob={cron_value or '<empty>'}")
        if mismatches:
            findings.append(
                {
                    "type": "runtime.config_mismatch",
                    "severity": "medium",
                    "resource": "deployment/a2w-lucas-agent,cronjob/a2w-lucas",
                    "evidence": mismatches,
                    "likely_cause": "Interactive and scheduled Lucas runtimes are configured with different provider settings.",
                    "recommended_actions": [
                        "Align deployment and cronjob provider env values.",
                        "Re-run interactive and cron smoke tests after aligning the runtime config.",
                    ],
                }
            )
            summary["runtime"] += 1

    for resource_name, env_map in (("deployment/a2w-lucas-agent", deployment_env), ("cronjob/a2w-lucas", cronjob_env)):
        provider = _provider_from_env(env_map)
        if not provider:
            continue
        expected_env = _expected_secret_env(provider)
        if expected_env in env_map:
            continue
        fallback_present = "LLM_API_KEY" in env_map and provider != "anthropic"
        if fallback_present:
            findings.append(
                {
                    "type": "runtime.secret_ref_mismatch",
                    "severity": "medium",
                    "resource": resource_name,
                    "evidence": [f"provider={provider}", f"expected secret env {expected_env} is missing", "falling back to LLM_API_KEY"],
                    "likely_cause": "The runtime is using a generic API key path instead of the provider-specific secret reference.",
                    "recommended_actions": [
                        f"Mount {expected_env} explicitly for {provider}.",
                        "Keep generic fallback only for compatibility, not as the primary production wiring.",
                    ],
                }
            )
            summary["runtime"] += 1
        elif expected_env != "LLM_API_KEY":
            findings.append(
                {
                    "type": "runtime.secret_ref_mismatch",
                    "severity": "high",
                    "resource": resource_name,
                    "evidence": [f"provider={provider}", f"missing expected secret env {expected_env}"],
                    "likely_cause": "The selected provider does not have a matching secret reference in the workload env.",
                    "recommended_actions": [
                        f"Mount {expected_env} from the appropriate secret.",
                        "Restart the workload and rerun the smoke test after fixing the secret wiring.",
                    ],
                }
            )
            summary["runtime"] += 1

    return {
        "status": "issues_found" if findings else "ok",
        "drift_summary": summary,
        "drifts": findings,
    }


def collect_runtime_drift_inputs(namespace: str | None = None, deployment_name: str = "a2w-lucas-agent", cronjob_name: str = "a2w-lucas") -> dict[str, Any]:
    namespace = namespace or _serviceaccount_namespace()
    input_errors: list[str] = []

    deployment = _safe_run_kubectl_json(["-n", namespace, "get", "deployment", deployment_name, "-o", "json"], f"deployment/{deployment_name}", input_errors)
    cronjob = _safe_run_kubectl_json(["-n", namespace, "get", "cronjob", cronjob_name, "-o", "json"], f"cronjob/{cronjob_name}", input_errors)

    pods_payload = _safe_run_kubectl_json(["-n", namespace, "get", "pods", "-o", "json"], "pods", input_errors, {"items": []})
    deployment_pod = None
    cronjob_pod = None
    for item in pods_payload.get("items", []):
        name = item.get("metadata", {}).get("name", "")
        if name.startswith(f"{deployment_name}-") and deployment_pod is None:
            deployment_pod = item
        elif name.startswith(f"{cronjob_name}-"):
            cronjob_pod = item

    events_payload = _safe_run_kubectl_json(["-n", namespace, "get", "events", "-o", "json"], "events", input_errors, {"items": []})
    event_items = events_payload.get("items", [])

    def matching_events(pod: dict[str, Any] | None) -> list[dict[str, Any]]:
        if not pod:
            return []
        pod_name = pod.get("metadata", {}).get("name")
        return [item for item in event_items if item.get("involvedObject", {}).get("name") == pod_name]

    pvc_payload = _safe_run_kubectl_json(["-n", namespace, "get", "pvc", "-o", "json"], "pvc", input_errors, {"items": []})

    configmaps: dict[str, dict[str, str]] = {}
    for volume in deployment.get("spec", {}).get("template", {}).get("spec", {}).get("volumes", []):
        configmap = volume.get("configMap", {})
        name = configmap.get("name")
        if name and name not in configmaps:
            configmaps[name] = _safe_run_kubectl_json(["-n", namespace, "get", "configmap", name, "-o", "json"], f"configmap/{name}", input_errors, {"data": {}}).get("data", {})
    for volume in cronjob.get("spec", {}).get("jobTemplate", {}).get("spec", {}).get("template", {}).get("spec", {}).get("volumes", []):
        configmap = volume.get("configMap", {})
        name = configmap.get("name")
        if name and name not in configmaps:
            configmaps[name] = _safe_run_kubectl_json(["-n", namespace, "get", "configmap", name, "-o", "json"], f"configmap/{name}", input_errors, {"data": {}}).get("data", {})

    return {
        "deployment": deployment,
        "cronjob": cronjob,
        "deployment_pod": deployment_pod,
        "cronjob_pod": cronjob_pod,
        "deployment_events": matching_events(deployment_pod),
        "cronjob_events": matching_events(cronjob_pod),
        "pvcs": pvc_payload.get("items", []),
        "configmaps": configmaps,
        "input_errors": input_errors,
    }
