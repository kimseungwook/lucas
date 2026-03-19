# Specifications

This section defines the work required to evolve Lucas from a Claude-specific runtime into a provider-agnostic agent backend with support for non-Claude providers such as Groq, Kimi, Gemini, and OpenRouter.

## Current status

- The provider-agnostic refactor has been implemented in the local codebase.
- Groq and Kimi have both been validated through the OpenAI-compatible backend path.
- OpenRouter is available as an optional OpenAI-compatible provider. Default model is `stepfun/step-3.5-flash:free`.
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
- `prd-drift-auditor.md`: product goals, scope, and acceptance criteria for deterministic drift detection.
- `trd-drift-auditor.md`: technical design for storage/code/runtime drift auditing and remediation guidance.
- `implementation-plan-drift-auditor.md`: execution plan for the first read-only scheduled drift-auditor release.
- `implementation-plan-redis-safe-self-recovery.md`: execution plan for feature-flagged Redis safe self-recovery in scheduled monitoring.
- `trd-redis-safe-self-recovery.md`: technical design for Redis health gating, suppression, locking, and single-pod recovery.
- `prd-redis-safe-self-recovery.md`: product scope for rollout-aware Redis self-recovery with shallow automatic action.
- `prd-postgres-migration.md`: product scope for replacing shared SQLite persistence with a dev-first Postgres rollout.
- `trd-postgres-migration.md`: technical design for Postgres-backed Lucas persistence, shadow validation, and dashboard decoupling.
- `implementation-plan-postgres-migration.md`: execution plan for the dev-first Postgres migration with shadow validation and dashboard decoupling.
- `current-platform-state.md`: cross-cutting technical summary of the implemented workstreams and current platform shape.
- `prod-transition.md`: production-transition policy, env-file workflow, and dev/prod rollout boundaries.
- `gemini-flash-dev-backend.md`: draft proposal for adding Gemini Flash as a development-only backend candidate.
- OpenRouter provider support is documented in the provider-agnostic backend docs.
- Drift-auditor design is the next operations-hardening track.

## Intended use

Read the PRD first to align on problem and scope. Use the TRD to implement the architecture. Use the implementation and QA documents to sequence work and verify release readiness. Use `current-platform-state.md` when you need a single technical summary of where the platform stands today. Use the drift-auditor specs, Redis self-recovery specs, and Postgres migration specs as the next design tracks for Kubernetes operations hardening.
