from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass

try:
    from .cluster_snapshot import _kubectl_base_command
except ImportError:
    from cluster_snapshot import _kubectl_base_command


NAME_PATTERN = r"[a-z0-9][a-z0-9.-]*"


@dataclass(frozen=True)
class SlackKubeAction:
    verb: str
    kind: str
    name: str
    namespace: str
    replicas: int | None = None

    @property
    def is_mutating(self) -> bool:
        return self.verb in {"restart", "delete", "undo", "scale"}


@dataclass(frozen=True)
class SlackActionParseResult:
    matched: bool
    action: SlackKubeAction | None = None
    error: str | None = None


def _extract_namespace(text: str, default_namespace: str) -> str:
    lowered = text.lower()
    patterns = [
        rf"namespace\s+({NAME_PATTERN})",
        rf"({NAME_PATTERN})\s+namespace",
        rf"({NAME_PATTERN})\s*네임스페이스",
        rf"({NAME_PATTERN})의\s*(?:deployment|statefulset|pod|pods|파드|네임스페이스)",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return default_namespace


def _extract_resource_name(text: str, kind: str) -> str | None:
    lowered = text.lower()
    patterns = [
        rf"{kind}\s+({NAME_PATTERN})",
        rf"({NAME_PATTERN})\s+{kind}(?:를|을)?",
        rf"({NAME_PATTERN})의\s+{kind}",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return None


def _extract_pod_name_for_logs(text: str) -> str | None:
    lowered = text.lower()
    patterns = [
        rf"logs?\s+for\s+pod\s+({NAME_PATTERN})",
        rf"pod\s+logs?\s+({NAME_PATTERN})",
        rf"pod\s+({NAME_PATTERN})\s+logs?",
        rf"({NAME_PATTERN})\s+pod\s+logs?",
        rf"({NAME_PATTERN})의\s+pod\s+로그",
        rf"({NAME_PATTERN})\s+pod\s+로그",
    ]
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(1)
    return _extract_resource_name(text, "pod")


def _contains_any(text: str, keywords: list[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)


def parse_slack_kube_action(text: str, default_namespace: str) -> SlackActionParseResult:
    lowered = text.lower().strip()

    action_keywords = [
        "restart", "rollout status", "rollout undo", "delete pod", "scale", "describe pod", "pod log", "logs for pod",
        "재시작", "삭제", "지워", "상태", "롤백", "scale", "describe", "log", "logs", "로그", "설명",
    ]
    if not any(keyword in lowered for keyword in action_keywords):
        return SlackActionParseResult(matched=False)

    namespace = _extract_namespace(text, default_namespace)

    if _contains_any(lowered, ["restart", "재시작", "다시 시작"]):
        for kind in ["deployment", "statefulset"]:
            name = _extract_resource_name(text, kind)
            if name:
                return SlackActionParseResult(matched=True, action=SlackKubeAction("restart", kind, name, namespace))
        pod_name = _extract_resource_name(text, "pod")
        if pod_name:
            return SlackActionParseResult(
                matched=True,
                error="`restart pod`는 지원하지 않습니다. `delete pod ...` 또는 `restart deployment/statefulset ...`을 사용하세요.",
            )

    if _contains_any(lowered, ["delete pod", "pod 삭제", "pod를 삭제", "파드 삭제", "파드를 삭제", "지워"]):
        pod_name = _extract_resource_name(text, "pod")
        if pod_name:
            return SlackActionParseResult(matched=True, action=SlackKubeAction("delete", "pod", pod_name, namespace))

    if _contains_any(lowered, ["describe pod", "pod describe", "pod 설명", "pod를 설명", "파드 설명"]):
        pod_name = _extract_resource_name(text, "pod")
        if pod_name:
            return SlackActionParseResult(matched=True, action=SlackKubeAction("describe", "pod", pod_name, namespace))

    if _contains_any(lowered, ["pod log", "logs for pod", "pod logs", "로그", "log 보여", "logs 보여"]):
        pod_name = _extract_pod_name_for_logs(text)
        if pod_name:
            return SlackActionParseResult(matched=True, action=SlackKubeAction("logs", "pod", pod_name, namespace))

    if _contains_any(lowered, ["rollout status", "상태", "상태 확인"]):
        for kind in ["deployment", "statefulset"]:
            name = _extract_resource_name(text, kind)
            if name:
                return SlackActionParseResult(matched=True, action=SlackKubeAction("status", kind, name, namespace))

    if _contains_any(lowered, ["rollout undo", "undo", "롤백"]):
        name = _extract_resource_name(text, "deployment")
        if name:
            return SlackActionParseResult(matched=True, action=SlackKubeAction("undo", "deployment", name, namespace))

    if _contains_any(lowered, ["scale", "스케일"]):
        replicas_match = re.search(r"(?:to|replicas?\s*=?)\s*(\d+)", lowered) or re.search(r"(\d+)\s*개로", lowered)
        replicas = int(replicas_match.group(1)) if replicas_match else None
        for kind in ["deployment", "statefulset"]:
            name = _extract_resource_name(text, kind)
            if name:
                if replicas is None:
                    return SlackActionParseResult(matched=True, error="`scale` 명령에는 replica 수가 필요합니다. 예: `scale deployment api to 2 in namespace default`")
                if replicas < 0 or replicas > 20:
                    return SlackActionParseResult(matched=True, error="`scale`은 0에서 20 사이 replica 수만 허용합니다.")
                return SlackActionParseResult(matched=True, action=SlackKubeAction("scale", kind, name, namespace, replicas=replicas))

    return SlackActionParseResult(matched=True, error="지원되는 명령 형식을 이해하지 못했습니다.")


def slack_actions_enabled() -> bool:
    return os.environ.get("SLACK_EMERGENCY_ACTIONS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def slack_action_allowed(channel: str, user_id: str, namespace: str) -> tuple[bool, str | None]:
    allowed_channels = [value.strip() for value in os.environ.get("SLACK_ACTION_ALLOWED_CHANNELS", "").split(",") if value.strip()]
    allowed_users = [value.strip() for value in os.environ.get("SLACK_ACTION_ALLOWED_USERS", "").split(",") if value.strip()]
    allowed_namespaces = [value.strip() for value in os.environ.get("SLACK_ACTION_ALLOWED_NAMESPACES", "").split(",") if value.strip()]

    if not slack_actions_enabled():
        return False, "Slack 긴급 조치 기능이 비활성화되어 있습니다."
    if allowed_channels and channel not in allowed_channels:
        return False, "이 채널에서는 긴급 조치 명령을 실행할 수 없습니다."
    if allowed_users and user_id not in allowed_users:
        return False, "이 계정은 긴급 조치 명령 권한이 없습니다."
    if allowed_namespaces and namespace not in allowed_namespaces:
        return False, f"namespace `{namespace}` 에 대해서는 긴급 조치 명령을 실행할 수 없습니다."
    return True, None


def confirmation_prompt(action: SlackKubeAction) -> str:
    if action.verb == "scale":
        return f"다음 작업을 실행할까요? `{action.kind} {action.name}`을 namespace `{action.namespace}`에서 replicas={action.replicas}로 조정합니다. 진행하려면 `yes` 또는 `예`라고 답하세요."
    return f"다음 작업을 실행할까요? `{action.verb} {action.kind} {action.name}` in namespace `{action.namespace}`. 진행하려면 `yes` 또는 `예`라고 답하세요."


def confirmation_accepted(reply: str) -> bool:
    normalized = (reply or "").strip().lower()
    return normalized in {"y", "yes", "예", "네", "ㅇㅇ", "진행"}


def execute_slack_kube_action(action: SlackKubeAction) -> str:
    base = _kubectl_base_command()

    if action.verb == "restart":
        cmd = base + ["rollout", "restart", f"{action.kind}/{action.name}", "-n", action.namespace]
    elif action.verb == "delete":
        cmd = base + ["delete", "pod", action.name, "-n", action.namespace]
    elif action.verb == "describe":
        cmd = base + ["describe", "pod", action.name, "-n", action.namespace]
    elif action.verb == "logs":
        cmd = base + ["logs", action.name, "-n", action.namespace, "--tail=100"]
    elif action.verb == "status":
        cmd = base + ["rollout", "status", f"{action.kind}/{action.name}", "-n", action.namespace, "--timeout=180s"]
    elif action.verb == "undo":
        cmd = base + ["rollout", "undo", f"deployment/{action.name}", "-n", action.namespace]
    elif action.verb == "scale":
        replicas = action.replicas if action.replicas is not None else 0
        cmd = base + ["scale", f"{action.kind}/{action.name}", f"--replicas={replicas}", "-n", action.namespace]
    else:
        raise ValueError(f"Unsupported action verb: {action.verb}")

    result = subprocess.run(cmd, capture_output=True, text=True)
    combined = "\n".join(part for part in [result.stdout.strip(), result.stderr.strip()] if part).strip()
    if result.returncode != 0:
        raise RuntimeError(combined or f"kubectl failed with exit code {result.returncode}")

    if action.verb == "status":
        return combined or f"{action.kind} {action.name} rollout status succeeded."
    if action.verb == "describe":
        return f"pod 설명 결과입니다.\n{combined or f'pod {action.name} describe completed.'}"[:3900]
    if action.verb == "logs":
        return f"최근 pod 로그입니다.\n{combined or f'pod {action.name} log retrieval completed.'}"[:3900]
    if action.verb == "restart":
        return f"재시작 요청을 실행했습니다.\n{combined or f'{action.kind} {action.name} restarted.'}"
    if action.verb == "delete":
        return f"pod 삭제를 실행했습니다.\n{combined or f'pod {action.name} deleted.'}"
    if action.verb == "undo":
        return f"deployment 롤백을 실행했습니다.\n{combined or f'deployment {action.name} rolled back.'}"
    if action.verb == "scale":
        return f"scale 작업을 실행했습니다.\n{combined or f'{action.kind} {action.name} scaled.'}"
    return combined


def format_action_audit_line(action: SlackKubeAction) -> str:
    suffix = f" replicas={action.replicas}" if action.replicas is not None else ""
    return f"verb={action.verb} kind={action.kind} name={action.name} namespace={action.namespace}{suffix}"
