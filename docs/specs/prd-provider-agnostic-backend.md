# PRD: Provider-Agnostic Backend

## Summary

Lucas is currently coupled to Anthropic's Claude Code CLI for both interactive Slack flows and scheduled CronJob execution. This project will introduce a provider-agnostic backend layer so Lucas can keep its existing operational behavior while supporting multiple model backends, starting with Claude Code and an OpenAI-compatible path suitable for Groq, Kimi, Gemini, and OpenRouter.

## Current implementation status

- Shared backend/config abstraction has been implemented.
- Claude compatibility remains in the codebase.
- OpenAI-compatible validation has succeeded against both Groq and Kimi.
- OpenRouter is supported as an optional OpenAI-compatible provider. Default model is `stepfun/step-3.5-flash:free`.
- `goyo-dev` currently runs the dashboard, a Groq-backed scheduled monitoring CronJob, and a Groq-backed interactive Slack agent in `a2w-lucas`.
- The current non-Claude runtime is intentionally reduced-capability: it uses Kubernetes snapshots and report formatting instead of full Claude-style tool execution.
- Slack emergency actions are implemented in development and validated against an allowlisted command set in `goyo-dev`.

## Problem

At project start, provider choice was effectively hardcoded into the runtime. That created four problems:

1. Lucas cannot use Groq or Kimi without code changes.
2. Deployment configuration is tied to Anthropic-specific secrets and naming.
3. Future provider expansion requires touching core runtime logic instead of adding a backend.
4. Product risk is concentrated in a single vendor path.

## Goals

- Preserve existing Lucas behavior for Claude users.
- Add a provider-neutral configuration model for backend, provider, model, API key, and base URL.
- Support an OpenAI-compatible backend path that can target Groq or Kimi.
- Support OpenRouter as an optional OpenAI-compatible provider.
- Keep Slack workflows, scheduled scans, SQLite persistence, and dashboard visibility intact.
- Make future provider additions incremental rather than architectural.
- Add a safe Slack emergency-action surface for a small allowlist of Kubernetes operations.

## Non-Goals

- Rewriting the dashboard.
- Expanding Lucas into a generic workflow engine beyond the current agent use cases.
- Adding every provider at once.
- Changing the operational semantics of runbooks, Slack prompts, or Kubernetes checks unless required by backend differences.
- Allowing arbitrary shell execution or unrestricted kubectl access from Slack.

## Users and stakeholders

- Platform engineers operating Lucas in Kubernetes.
- SREs using Lucas from Slack.
- Maintainers responsible for image builds, secrets, and deployment manifests.

## User needs

### Platform operator

Needs to choose a backend through environment variables and secrets without editing application code.

### SRE using Slack

Needs Lucas behavior in Slack threads to remain stable after backend changes, including continuity for follow-up messages.

### Incident responder

Needs a small set of safe, pre-approved emergency actions from Slack when direct system access is unavailable.

### Maintainer

Needs the backend integration surface to be explicit, testable, and documented so new providers can be added with bounded effort.

## Scope

## Operating assumptions

- The primary development validation environment is an Oracle Kubernetes Engine (OKE) cluster.
- The working `kubectl` context for development validation is `goyo-dev`.
- This development cluster is assumed to be available for 24x7 on-call validation, rollout rehearsal, and backend smoke testing.

### In scope

- Introduce a backend abstraction for agent execution.
- Keep Claude Code as a supported backend.
- Add one OpenAI-compatible backend path for Groq and Kimi.
- Generalize configuration, secrets, manifests, and docs.
- Normalize token usage, model identity, and cost capture where provider data is available.

### Current release decision

- Scheduled monitoring for non-Claude providers is implemented and validated with snapshot-driven analysis.
- Interactive Slack support for non-Claude providers is implemented with snapshot-driven replies rather than full tool parity.
- Full Claude-style tool orchestration remains a future enhancement, not a requirement for this release.
- The current development increment includes a limited Slack emergency-action path with explicit confirmation and an allowlist.

### Out of scope

- Guaranteed parity for every Claude Code capability on every provider.
- Full agent-tool orchestration parity if a provider only supports plain chat completions.
- Multi-provider routing or automatic failover in the first release.

## Functional requirements

### FR-1 Configuration

Lucas must support provider-neutral settings for backend type, provider name, model name, API key, and optional base URL.

OpenViking context guardrail:

OpenViking can provide memory or context support in supported environments, but Lucas must not assume OpenViking tools, long-term memory, or Claude-style resume are always available. When that support is absent, Lucas should rely only on the current prompt, explicit context, and live Kubernetes data.

### FR-2 Backward compatibility

Existing Claude deployments must continue to work with minimal or no manifest changes during the migration window.

### FR-3 Interactive execution

The interactive Slack agent must run through the selected backend and return response text, normalized model metadata, and usage data when available.

### FR-4 Scheduled execution

CronJob mode must run through the selected backend and continue writing summaries and status to SQLite.

### FR-5 Session continuity

Backend session behavior must be normalized enough to preserve Slack thread continuity where the backend supports resumable sessions. If a backend cannot resume, Lucas must degrade predictably and document the limitation.

### FR-6 Observability

Lucas must continue recording model, token usage, and cost fields in a consistent format for the dashboard.

### FR-7 Documentation

Deployment and configuration docs must describe both Claude and OpenAI-compatible setup paths.

### FR-8 Secret handling

Provider credentials must be supplied through environment variables or secret managers. Raw API keys must not be committed to the repository, embedded in markdown examples, or hardcoded in manifests.

### FR-9 Slack emergency-action allowlist

Lucas must support only this pre-approved Slack action set: `describe pod`, `pod log`, `restart deployment`, `restart statefulset`, `delete pod`, `rollout status deployment/statefulset`, `rollout undo deployment`, and `scale deployment/statefulset`.

### FR-10 Slack safety workflow

Mutating Slack actions must use explicit confirmation, authorization checks, audit logging, and refusal behavior for unsupported or ambiguous commands.

### FR-11 Scheduled monitoring scope

Scheduled monitoring must support multi-namespace execution and an all-namespaces mode rather than remaining fixed to `default` only.

## Success metrics

- A maintainer can switch between Claude and an OpenAI-compatible provider using configuration, not code edits.
- Existing Claude deployment flow still works after the refactor.
- Interactive and scheduled flows both execute successfully on the new abstraction.
- Documentation covers configuration, migration, rollback, and known limitations.
- At least one approved Slack emergency action executes safely in `goyo-dev` with traceable logs and user-visible confirmation.

## Implementation evidence

- Groq live API validation passed.
- Kimi live API validation passed against the official Moonshot endpoint.
- `goyo-dev` scheduled monitoring persisted structured run data to SQLite.
- `goyo-dev` dashboard is live in `a2w-lucas`.
- `goyo-dev` interactive Slack agent is connected via Socket Mode and can read the configured test channel.
- `goyo-dev` scheduled monitoring now supports `namespace=all` aggregate scans.
- `goyo-dev` live helper execution validated `describe pod`, `pod log`, `restart deployment`, `restart statefulset`, `delete pod`, `rollout status`, `rollout undo deployment`, and `scale deployment/statefulset` against disposable resources.

## Release acceptance criteria

- Claude backend behavior remains functional for existing deployments.
- Groq or Kimi can be configured through the OpenAI-compatible backend path.
- Docs build succeeds and deployment docs are internally consistent.
- Manual QA passes for one Claude path and one OpenAI-compatible path.
- Slack emergency actions, if enabled, are limited to the documented allowlist and produce auditable results.

## Risks

- Claude Code CLI provides session/tool semantics that plain OpenAI-compatible APIs may not match.
- Usage and cost fields may differ across providers.
- Prompt and tool behavior may need backend-specific adaptation.
- The current `goyo-dev` deployment uses bootstrap-style public images because direct pulls from `ghcr.io/a2wio/*` were blocked in that cluster.
- The scheduled Slack webhook currently targets the dedicated `k8s-ai-alert-analysis` channel.
- Over-permissive Slack actions could create unintended impact if allowlists, namespace scoping, or confirmation flows are too loose.

## Open questions

- When should the bootstrap deployment path be replaced with pullable prebuilt images?
- Should the scheduled alert destination remain the current dev alert channel or move to a Lucas-specific webhook?
- How far should non-Claude interactive parity go beyond snapshot-driven responses?
- Slack tokens used during testing were exposed in chat and should be rotated before long-lived use.
- Which Slack users or channels should be authorized for mutating emergency actions?
- What replica bounds should apply to `scale` in development and production-like namespaces?
- How should all-namespaces scheduled scans summarize findings without becoming noisy in Slack?
