# QA and Rollout: Provider Backends

## Environment baseline

- Development Kubernetes validation runs on Oracle Kubernetes Engine (OKE).
- The expected `kubectl` context for this work is `goyo-dev`.
- This cluster is treated as the 24x7 available environment for smoke tests, rollout rehearsal, and on-call validation.

## Current implementation result

- Namespace `a2w-lucas` exists on `goyo-dev`.
- Dashboard is deployed and healthy.
- Groq-backed scheduled monitoring is deployed and producing live runs.
- Groq-backed interactive Slack agent is deployed and connected through Socket Mode.
- Scheduled alerts currently use the webhook stored in `a2w-lucas/slack-webhook`, which now points to `k8s-ai-alert-analysis`.
- Slack emergency actions are enabled in `goyo-dev` for the allowed Slack channel.

## Verification matrix

### Claude backend

- Interactive Slack request returns a valid response.
- Slack thread follow-up reuses prior session when available.
- Scheduled scan writes run status, report text, and usage data.
- Existing Anthropic-oriented deployment remains valid during migration.

### OpenAI-compatible backend

- Startup accepts provider-neutral configuration.
- Request succeeds against configured base URL.
- Response text is persisted correctly.
- Model and usage fields are recorded without breaking dashboard queries.
- Unsupported session behavior is either handled or clearly logged.
- Reduced-capability behavior is documented for non-Claude interactive flows.
- OpenRouter path: `LLM_PROVIDER=openrouter` uses OpenRouter envs and defaults model to `stepfun/step-3.5-flash:free`.

### Slack emergency actions

- Only the documented allowlist is accepted.
- `describe pod` and `pod log` succeed as read-only actions.
- Read-only actions succeed without mutation.
- Mutating actions require explicit confirmation.
- Unsupported or ambiguous commands are refused safely.
- Execution results are logged and user-visible in Slack.

## Manual QA scenarios

### Scenario 1: existing Claude deployment

- Confirm the active context is `goyo-dev` before running deployment validation.
- Start the interactive agent with current Claude settings.
- Send a Slack mention.
- Send a follow-up reply in the same thread.
- Confirm response continuity and SQLite session persistence.

### Scenario 2: scheduled Claude run

- Confirm the active context is `goyo-dev` before triggering the CronJob path.
- Run CronJob mode with Claude config.
- Confirm report, status, and token data are written.

### Scenario 3: Groq or Kimi through OpenAI-compatible backend

- Confirm the active context is `goyo-dev` before validating the non-Claude backend.
- Start Lucas with `LLM_BACKEND=openai-compatible`.
- Use provider-specific `LLM_BASE_URL` and `LLM_API_KEY`.
- Inject credentials from the runtime environment or Kubernetes secrets; do not place raw keys in repo files or docs examples.
- Run one scheduled execution first.
- If interactive support is in scope, validate one Slack request and one follow-up behavior.

### Scenario 4: OpenRouter through OpenAI-compatible backend

- Confirm the active context is `goyo-dev` before validating the OpenRouter path.
- Start Lucas with `LLM_BACKEND=openai-compatible` and `LLM_PROVIDER=openrouter`.
- Prefer `OPENROUTER_API_KEY`. Optionally set `OPENROUTER_MODEL` (default `stepfun/step-3.5-flash:free`).
- Do not assume OpenViking tools or long-term memory are present unless the environment provides them.

## Executed verification evidence

- Docs build passed.
- Agent-focused unit tests passed.
- Groq live API validation passed.
- Kimi live API validation passed.
- `goyo-dev` scheduled monitoring wrote structured JSON report data to SQLite.
- `goyo-dev` dashboard reached healthy state.
- `goyo-dev` interactive agent reached running state and established a Socket Mode session.
- `goyo-dev` scheduled monitoring produced successful `namespace=all` runs.
- `goyo-dev` live helper execution validated the current allowlist against disposable resources.
- `goyo-dev` latest `namespace=all` run produced `status=issues_found`, `pods=313`, and `issues=107`, matching visible unhealthy pods in the cluster.

## Emergency-action QA scenarios

- `describe pod` from Slack in `goyo-dev`
- `pod log` from Slack in `goyo-dev`
- `rollout status deployment/statefulset` from Slack in `goyo-dev`
- `restart deployment/statefulset` with confirmation
- `delete pod` with confirmation
- `rollout undo deployment` with confirmation
- `scale deployment/statefulset` with replica bounds and confirmation
- refusal for unsupported commands, ambiguous text, unauthorized users, and unauthorized channels

## Scheduled-scan scope QA

- multi-namespace scan using explicit `TARGET_NAMESPACES`
- all-namespaces scan using the new aggregate mode
- concise Slack summary output even when multiple namespaces contain findings

## Known live limitations

- `ghcr.io/a2wio/*` images were not pullable from `goyo-dev`, so the current deployment uses public bootstrap containers plus ConfigMap-mounted source files.
- Scheduled alerts currently land in `k8s-ai-alert-analysis`.
- A fresh end-user Slack mention should be used to confirm the latest interactive reply formatting after the most recent live patch.
- Final user-typed Slack command verification is still pending for tomorrow.

## Rollout plan

### Step 1

Release backend abstraction with Claude as default.

### Step 2

Release OpenAI-compatible backend behind explicit configuration.

### Step 3

Update deployment examples for Groq and Kimi after successful validation.

### Step 4

Enable Slack emergency actions behind a feature flag in `goyo-dev` and validate the allowlist end to end.

## Rollback plan

- Keep Claude backend as the default fallback.
- Preserve old Anthropic env handling during the migration window.
- If OpenAI-compatible backend fails, revert configuration to Claude without requiring schema rollback.
- If the bootstrap deployment path becomes unstable, disable or remove the dev bootstrap workloads and return to the previously known-good manifest set.
- If Slack emergency actions misbehave, disable the feature flag and revert the RBAC/deployment changes associated with the allowlist path.

## Release notes checklist

- New configuration variables documented.
- Claude compatibility path documented.
- Groq and Kimi setup examples documented.
- Known limitations called out explicitly.

## Sign-off criteria

- Engineering confirms runtime behavior.
- Operations confirms manifest and secret changes.
- Documentation confirms setup steps are reproducible.
