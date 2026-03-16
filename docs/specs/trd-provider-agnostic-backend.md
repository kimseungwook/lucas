# TRD: Provider-Agnostic Backend

## Objective

Replace the current Claude-specific execution path with a backend abstraction that supports both Claude Code and OpenAI-compatible providers without rewriting Lucas operational flows.

OpenViking context guardrail:

OpenViking can provide memory or context support in supported environments, but Lucas must not assume OpenViking tools, long-term memory, or Claude-style resume are always available. When that support is absent, Lucas should rely only on the current prompt, explicit context, and live Kubernetes data.

## Current state

Lucas currently depends on Claude-specific runtime behavior:

- `src/agent/main/main.py` shells out to `claude` and parses Claude CLI JSON output.
- `src/agent/entrypoint/entrypoint.sh` invokes `claude` directly in CronJob mode.
- `Dockerfile.agent` and `Dockerfile.lucas` install `@anthropic-ai/claude-code`.
- Kubernetes manifests and docs use Anthropic-specific env vars and secret names.

## Implemented state

The development branch now includes these runtime elements:

- `src/agent/main/llm.py`: `ClaudeCodeBackend` and `OpenAICompatibleBackend` with provider-neutral config resolution.
- `src/agent/main/cluster_snapshot.py`: scheduled and interactive snapshot builders for non-Claude execution.
- `src/agent/main/report_utils.py`: extraction, parsing, and Slack-safe formatting of scheduled scan reports.
- `src/agent/main/cron_runner.py`: shared Python CronJob runtime that persists structured run data and emits concise webhook alerts.
- `src/agent/main/main.py`: interactive Slack path routed through the backend abstraction with snapshot-driven non-Claude behavior.

The live `goyo-dev` cluster currently runs:

- A Groq-backed scheduled CronJob in namespace `a2w-lucas`.
- A Groq-backed interactive Slack agent in namespace `a2w-lucas`.
- The dashboard in namespace `a2w-lucas`.

## Current next-scope status

The limited Slack emergency-action path is now implemented in development with deterministic parsing, allowlisted Kubernetes operations, confirmation, and audit logging.

## Target architecture

### Backend abstraction

Introduce a backend interface in the agent runtime with a stable result contract.

Suggested result shape:

```python
class AgentResult(TypedDict):
    text: str
    session_id: str | None
    model: str
    input_tokens: int
    output_tokens: int
    cost: float
```

Suggested backend interface:

```python
class AgentBackend(Protocol):
    async def run(
        self,
        prompt: str,
        system_prompt: str,
        session_id: str | None,
        context: dict,
    ) -> AgentResult:
        ...
```

### Backend implementations

#### ClaudeCodeBackend

Wrap existing `claude` CLI behavior with minimal functional change.

Responsibilities:

- Build Claude CLI command.
- Handle `--resume` behavior.
- Parse JSON output.
- Normalize usage and cost fields.

#### OpenAICompatibleBackend

Add an HTTP or SDK-based path that targets OpenAI-compatible providers such as Groq and Kimi.

Responsibilities:

- Build chat-completions style requests.
- Map Lucas prompt and context into request messages.
- Normalize response text, model, usage, and cost fields.
- Define how session continuity behaves when backend-native resume is unavailable.

Validated defaults:

- Groq: `https://api.groq.com/openai/v1`, model `llama-3.3-70b-versatile`
- Kimi: `https://api.moonshot.ai/v1`, model `kimi-k2.5`
- OpenRouter: `https://openrouter.ai/api/v1`, model `stepfun/step-3.5-flash:free`

## Configuration model

### New variables

- `LLM_BACKEND`: `claude-code` or `openai-compatible`
- `LLM_PROVIDER`: `anthropic`, `groq`, `kimi`, `gemini`, `openrouter`, or future values
- `LLM_MODEL`: concrete model identifier
- `LLM_API_KEY`: provider API key
- `LLM_BASE_URL`: optional override for OpenAI-compatible providers
- `SLACK_EMERGENCY_ACTIONS_ENABLED`: feature flag for Slack-triggered Kubernetes mutations.
- `SLACK_ACTION_ALLOWED_CHANNELS`: comma-separated allowlist of Slack channel IDs.
- `SLACK_ACTION_ALLOWED_USERS`: optional comma-separated allowlist of Slack user IDs.
- `SLACK_ACTION_ALLOWED_NAMESPACES`: optional comma-separated namespace allowlist; empty means all namespaces are currently allowed.

Example secret handling:

- Use `LLM_API_KEY` as a runtime-injected secret, not a checked-in literal value.
- Use `LLM_BASE_URL` for provider-specific OpenAI-compatible endpoints, for example Groq at `https://api.groq.com/openai/v1`.
- OpenRouter canonical envs: `OPENROUTER_API_KEY`, `OPENROUTER_MODEL`, `OPENROUTER_BASE_URL`.
- Keep provider examples in docs as placeholders only.

### Compatibility layer

Keep the current Claude variables during migration:

- `CLAUDE_MODEL`
- `ANTHROPIC_API_KEY`
- `AUTH_MODE`

Migration behavior:

- If new neutral variables are present, prefer them.
- If only Claude-specific variables are present, map them to the Claude backend.
- Emit clear startup logs describing which path was selected.

## Runtime behavior

### Interactive Slack flow

`main.py` should stop calling `run_claude_agent()` directly and instead call a generic backend runner. Session storage in SQLite stays unchanged, but backend-specific session semantics are normalized before persistence.

Implemented behavior:

- Claude keeps the CLI-driven session flow.
- OpenAI-compatible interactive replies use a Kubernetes snapshot built from the user's query context.
- The non-Claude path is designed to answer with results, not shell commands, but it still does not provide full Claude-style tool execution parity.

### Slack emergency-action flow

Implemented behavior:

- Slack text is parsed deterministically into a narrow internal command object.
- Only the documented allowlist can bypass the normal LLM reply path.
- `describe pod` and `pod log` are read-only actions.
- `rollout status` is read-only.
- `restart deployment`, `restart statefulset`, `delete pod`, `rollout undo deployment`, and `scale deployment/statefulset` are mutating actions and require explicit confirmation.
- Unsupported or ambiguous commands are refused without side effects.
- Every request is logged with Slack user, channel, parsed action, target resource, execution result, and failure details.

### Scheduled scan flow

CronJob mode should use the same backend abstraction as the interactive agent so behavior does not diverge by runtime path.

Implemented behavior:

- The CronJob uses a Python runtime with `cron_runner.py`.
- Non-Claude scheduled scans use `build_namespace_snapshot()` and are expected to emit a strict JSON report.
- `report_utils.py` strips report blocks and formats concise Slack summaries so pseudo-command transcripts are not forwarded as alerts.
- All-namespaces scheduled scans now use a deterministic aggregate snapshot path to avoid token-limit failures and to preserve issue counts even when the model output is weak.

Implemented expansion:

- Scheduler and CronJob paths support comma-separated namespace sets and an explicit all-namespaces mode.
- Aggregated scheduled reports summarize results across namespaces without reverting to raw tool transcripts.

### Validation environment

- Kubernetes validation targets the development OKE cluster selected by `kubectl` context `goyo-dev`.
- All pre-release deployment verification should run against this development cluster before any broader rollout.
- The design assumes this cluster is available for 24x7 development and on-call validation workflows.

### Usage and cost normalization

Rules:

- Store provider-returned model names when available.
- Store zero usage fields only when provider data is unavailable.
- Allow static cost tables as a fallback when a provider does not return cost.
- Keep SQLite schema unchanged unless a gap is confirmed.

## Tooling implications

The largest technical risk is tool execution parity. Claude Code currently combines LLM inference with tool orchestration. An OpenAI-compatible backend may only provide text generation.

Release strategy should therefore support one of these explicit outcomes:

1. Full parity path: Lucas implements its own tool loop for non-Claude backends.
2. Reduced-capability path: non-Claude backends are initially limited to report-oriented tasks.

The release must declare which path is chosen.

Chosen path for the current development release:

- Reduced-capability non-Claude runtime with snapshot-driven monitoring and replies.
- No claim of full tool parity for Groq or Kimi.

Chosen path for Slack emergency actions:

- Do not expose arbitrary command execution.
- Use deterministic parsing plus allowlisted kubectl mappings only.
- Keep mutating actions behind explicit confirmation and channel/user authorization.

## File-level change plan

- `src/agent/main/main.py`: extract backend selection, config parsing, result normalization, and existing Claude execution.
- `src/agent/entrypoint/entrypoint.sh`: remove direct Claude invocation and route through shared runtime entry.
- `src/agent/main/requirements.txt`: add required dependency if OpenAI-compatible SDK is used.
- `Dockerfile.agent`: install only the dependencies required for enabled backends.
- `Dockerfile.lucas`: same for CronJob runtime.
- `k8s/agent-deployment.yaml`: generalize env vars and secret references.
- `k8s/cronjob.yaml`: same for scheduled mode.
- `README.md` and `docs/guide/configuration.md`: update operator-facing setup.

Slack emergency-action implementation targets:

- `src/agent/main/main.py`: detect and route allowlisted Slack commands before the generic LLM path.
- `src/agent/main/cluster_snapshot.py` or a sibling execution module: shared kubectl base command and deterministic action execution helpers, including `describe pod` and `pod log`.
- `src/agent/main/tools.py`: reuse Slack ask/reply utilities for confirmations and result delivery.
- `k8s/rbac.yaml`: add only the verbs/resources required by the allowlist.
- `tests/agent/*`: parser, policy, executor, and routing tests.

## Rollout design

### Phase 1

Introduce abstraction and preserve Claude behavior.

### Phase 2

Add OpenAI-compatible backend for scheduled scans and report-oriented flows.

### Phase 3

Add or improve interactive Slack continuity for non-Claude providers if required.

## Implemented dev rollout notes

- `goyo-dev` could not pull `ghcr.io/a2wio/*` images due `403 Forbidden`.
- The development rollout therefore uses public bootstrap containers that install dependencies at startup and mount runtime files from ConfigMaps.
- The Slack webhook secret in `a2w-lucas` now targets the dedicated `k8s-ai-alert-analysis` channel.

## Implemented rollout notes for Slack emergency actions

- Enabled in `goyo-dev` only.
- Limited to designated Slack channels via `SLACK_ACTION_ALLOWED_CHANNELS`.
- Validated with disposable test resources before broader use.
- Mutating actions require explicit confirmation.

## Risks and mitigations

### Risk: session mismatch

Mitigation: define a backend capability flag for resumable sessions and degrade explicitly when unsupported.

### Risk: tool-use mismatch

Mitigation: scope non-Claude release to supported behaviors and document gaps.

### Risk: config ambiguity

Mitigation: define precedence rules and fail fast on conflicting variables.

### Risk: deployment drift

Mitigation: update manifests, secrets, docs, and examples in the same change set.

### Risk: bootstrap runtime drift

Mitigation: treat the current public bootstrap deployment as a dev-only workaround and replace it with pullable prebuilt images before production hardening.

### Risk: alert destination drift

Mitigation: keep the scheduled webhook explicitly documented and verify the target channel during rollout.

### Risk: over-broad Slack action execution

Mitigation: allowlist exact verbs/resources, reject free-form commands, and require confirmation before mutation.

### Risk: privilege drift in RBAC

Mitigation: add only the minimal verbs/resources needed for the documented Slack command set.

### Risk: all-namespace alert noise

Mitigation: aggregate scheduled findings by namespace and keep Slack summaries concise.

## Technical acceptance criteria

- Shared backend interface exists and both runtime paths use it.
- Claude backend remains functional.
- OpenAI-compatible backend can target Groq or Kimi through config.
- Startup configuration resolution is deterministic and documented.
- Usage and cost recording remain compatible with the dashboard.
- Slack emergency actions, once implemented, are restricted to the documented allowlist and produce auditable outputs.

## Current validation evidence

- Groq live call passed.
- Kimi live call passed with official Moonshot defaults.
- `goyo-dev` scheduled run wrote structured report JSON to SQLite.
- `goyo-dev` dashboard is up and healthy.
- `goyo-dev` interactive agent is connected to Slack via Socket Mode.
- `goyo-dev` scheduled monitoring runs successfully with `TARGET_NAMESPACES=all`.
- `goyo-dev` Slack action helpers validated `describe pod`, `pod log`, `restart deployment`, `restart statefulset`, `delete pod`, `rollout status`, `rollout undo deployment`, and `scale deployment/statefulset`.
- `goyo-dev` latest all-namespaces run reports `issues_found` with real problematic pods instead of false `issues=0` results.
