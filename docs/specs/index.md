# Specifications

This section defines the work required to evolve Lucas from a Claude-specific runtime into a provider-agnostic agent backend with support for non-Claude providers such as Groq and Kimi.

## Current status

- The provider-agnostic refactor has been implemented in the local codebase.
- Groq and Kimi have both been validated through the OpenAI-compatible backend path.
- The development cluster `goyo-dev` currently runs a live Groq-backed scheduled monitoring path, a live interactive Slack agent, and the dashboard in namespace `a2w-lucas`.
- The current non-Claude path is snapshot-driven and reduced-capability compared with Claude Code tool execution.
- Slack emergency actions are implemented in development for the approved allowlist.
- Status-first scheduled reporting is now the active reporting improvement track.
- The specs below reflect both the intended design and the implementation state reached in development.

## Document set

- `prd-provider-agnostic-backend.md`: product goals, scope, user value, and acceptance criteria.
- `trd-provider-agnostic-backend.md`: technical design, system boundaries, interfaces, rollout, and risks.
- `implementation-plan-provider-backends.md`: execution breakdown, milestones, dependencies, and delivery order.
- `qa-rollout-provider-backends.md`: verification matrix, migration checklist, rollout plan, and fallback plan.
- `status-first-reporting.md`: reporting contract for pod-state-first scheduled summaries and compatibility rules.
- `prod-transition.md`: production-transition policy, env-file workflow, and dev/prod rollout boundaries.
- `gemini-flash-dev-backend.md`: draft proposal for adding Gemini Flash as a development-only backend candidate.

## Intended use

Read the PRD first to align on problem and scope. Use the TRD to implement the architecture. Use the implementation and QA documents to sequence work and verify release readiness.
