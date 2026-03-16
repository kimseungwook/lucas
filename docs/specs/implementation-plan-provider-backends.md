# Implementation Plan: Provider Backends

## Purpose

This document translates the PRD and TRD into a delivery sequence that can be executed by engineering without expanding scope.

## Execution status

### Completed in development

- Claude-specific execution was isolated behind a backend abstraction.
- Provider-neutral config resolution and secret naming were introduced.
- Groq and Kimi support were implemented and validated.
- OpenRouter support is available as an optional OpenAI-compatible provider. Default model is `stepfun/step-3.5-flash:free`.
- `goyo-dev` now runs a live scheduled monitoring path, dashboard, and interactive agent in `a2w-lucas`.
- Scheduled alert formatting was tightened to prevent raw pseudo-command transcripts from being forwarded.
- Interactive non-Claude replies were moved toward snapshot-driven results instead of command echoing.
- Slack emergency-action parsing, allowlist execution, and confirmation flow are implemented in development.
- Scheduled monitoring now supports `TARGET_NAMESPACES=all` aggregate scans.
- Deterministic all-namespaces issue counting is implemented to avoid false `status=ok` results when unhealthy pods exist.

### Remaining hardening work

- Replace bootstrap-style public runtime containers with pullable prebuilt images.
- Confirm final user-facing Slack interactive behavior after the latest live patch.
- Rotate Slack tokens that were exposed during testing.
- Decide the permanent Slack webhook destination for scheduled alerts.
- Add final manual Slack QA for the new emergency-action path.

## Milestones

### Milestone 1: isolate Claude runtime

- Extract configuration parsing from `main.py` into a shared module.
- Wrap current Claude execution in a `ClaudeCodeBackend` implementation.
- Keep all existing Claude behavior unchanged.

Exit criteria:

- Existing Claude path still works for interactive and scheduled execution.

### Milestone 2: define generic backend contract

- Introduce backend result normalization.
- Route interactive and scheduled flows through the same abstraction.
- Add capability flags for session resume and usage availability.

Exit criteria:

- No direct Claude invocation remains outside the Claude backend implementation.

### Milestone 3: add OpenAI-compatible backend

- Implement OpenAI-compatible backend configuration and request flow.
- Support provider-specific base URLs for Groq and Kimi.
- Normalize response text and usage metadata.

Exit criteria:

- One OpenAI-compatible provider can run end-to-end in Lucas.

### Milestone 4: deployment and docs migration

- Update Dockerfiles, manifests, and secrets.
- Document new env vars and backward-compatible Claude mapping.
- Add migration and rollback steps.

Exit criteria:

- A fresh deployment can be configured through docs only.

Implementation note:

- This milestone was completed in `goyo-dev` using a bootstrap deployment workaround because `ghcr.io/a2wio/*` pulls were blocked.

### Milestone 5: Slack emergency actions

- Implement deterministic parsing for the approved Slack command set.
- Include `describe pod` and `pod log` as read-only Slack actions.
- Add confirmation and refusal behavior for mutating actions.
- Extend RBAC only for the allowlisted Kubernetes verbs/resources.
- Verify action execution and audit evidence in `goyo-dev`.

Exit criteria:

- Supported Slack actions execute or refuse exactly as documented.
- Mutating actions require confirmation.
- Logs and Slack output show clear execution results.

## Workstreams

### Application runtime

- Backend interface
- Config loader
- Claude backend wrapper
- OpenAI-compatible backend implementation
- Result normalization

### Deployment

- Image dependency updates
- Manifest updates
- Secret naming guidance
- Config examples

### Documentation

- Guide updates
- Ops updates
- Migration notes
- Known limitations
- OpenRouter and OpenViking context wording alignment

### Validation

- Docs build
- Runtime smoke tests
- Interactive Slack verification
- CronJob verification
- Slack emergency-action verification
- Multi-namespace or all-namespaces scheduled scan verification

## Dependencies

- Backend abstraction must exist before OpenAI-compatible integration.
- Config precedence must be defined before manifest updates.
- Capability decisions must be made before Slack parity is promised.

## Delivery assumptions

- First release may preserve full Claude behavior while limiting non-Claude support to the capabilities explicitly verified.
- SQLite schema can remain stable unless implementation proves otherwise.

## Definition of done

- PRD and TRD requirements are met.
- Deployment docs are updated in the same release.
- Manual QA passes on Claude and one OpenAI-compatible provider.
- Known limitations are documented, not implied.

## Current outcome

- The implementation goals are met for development validation.
- Groq and Kimi have both passed live API checks.
- `goyo-dev` is running the current development release.
- Production-hardening follow-up remains for image distribution, token rotation, and final alert-channel decisions.
- Slack emergency-action implementation is complete in development and awaiting final manual Slack QA.
