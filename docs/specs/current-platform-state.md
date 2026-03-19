# Current Platform Technical State

This document summarizes the technical state reached across the major Lucas workstreams so far.

For a human-oriented quick guide, see `docs/manual.md`.

## Scope

This is not a replacement for the feature-by-feature PRD/TRD documents in `docs/specs/`.
It exists to answer a different question:

- what has actually been implemented so far
- how the current platform is wired together
- which hardening tracks are now part of the running system
- what is still intentionally left for the next stage

Also note:

- `docs/manual.md` is a human quick guide, not the implementation source of truth.
- design and implementation changes should still follow the detailed documents under `docs/specs/` and `docs/ops/`.

## Current technical baseline

Lucas currently operates as a Kubernetes-native operations agent with three primary runtime paths:

- interactive Slack agent
- scheduled CronJob scanner
- dashboard for runs, sessions, costs, and operational visibility

The current design direction is provider-agnostic and Postgres-backed.

## Workstreams completed so far

### Provider-agnostic backend and OpenRouter

- Lucas supports `openai-compatible` execution paths for non-Claude providers.
- OpenRouter is implemented as an optional provider under that path.
- The current OpenRouter default model is `stepfun/step-3.5-flash:free`.
- OpenRouter support is documented in the provider-agnostic backend spec set.

Primary references:

- `docs/specs/prd-provider-agnostic-backend.md`
- `docs/specs/trd-provider-agnostic-backend.md`
- `docs/specs/implementation-plan-provider-backends.md`
- `docs/specs/qa-rollout-provider-backends.md`

### OpenViking integration boundary

- OpenViking is treated as an external memory/context integration, not as the Lucas runtime provider contract.
- Lucas docs now explicitly avoid assuming OpenViking availability in the cluster runtime.
- When OpenViking is unavailable, Lucas falls back to explicit prompt context and live Kubernetes state.

Primary references:

- `README.md`
- `docs/guide/configuration.md`

### Drift Auditor

- Drift Auditor is implemented as a deterministic scheduled audit path.
- It is intended to detect storage, code, and runtime drift and report it in stored run results.
- The first release is read-only and reporting-focused.

Primary references:

- `docs/specs/prd-drift-auditor.md`
- `docs/specs/trd-drift-auditor.md`
- `docs/specs/implementation-plan-drift-auditor.md`

### Redis Safe Self-Recovery

- Redis self-recovery is designed as a feature-flagged, tightly constrained automation path.
- The only approved automatic action is pod deletion.
- The implementation is rollout-aware and intended to avoid unsafe topology mutations.

Primary references:

- `docs/specs/prd-redis-safe-self-recovery.md`
- `docs/specs/trd-redis-safe-self-recovery.md`
- `docs/specs/implementation-plan-redis-safe-self-recovery.md`

### Virtual-node compensating malware control

- This track exists because OCI virtual nodes cannot rely on the same daemon-style host enforcement path used for normal node pools.
- The current design is report-only, namespace-scoped, and feature-flagged.
- AI is used as a classification/interpretation layer over collected signals, not as a low-level process detector.

Primary references:

- `docs/specs/prd-virtual-node-compensating-malware-control.md`
- `docs/specs/trd-virtual-node-compensating-malware-control.md`
- `docs/specs/implementation-plan-virtual-node-compensating-malware-control.md`

### Namespace summary reporting

- Scheduled all-namespace scans now have a namespace-aware summary path.
- The design adds namespace summary rows so the dashboard can show per-namespace results even when the scheduled run scope is stored as `all`.

Primary references:

- `docs/specs/status-first-reporting.md`
- `docs/ops/dashboard.md`

### Dashboard runtime hardening

- The dashboard no longer depends on the shared `lucas-data` PVC for its primary runtime path.
- The running dashboard now uses a dedicated Harbor image instead of the older shared SQLite/PVC approach.
- The dashboard is intended to read report state from Postgres.

Primary references:

- `docs/ops/dashboard.md`
- `docs/ops/operations.md`
- `k8s/dashboard-deployment.yaml`

### Postgres migration

- The Postgres migration is the largest current storage change.
- The target state is Postgres as the runtime system of record for Lucas report/session state.
- The dashboard has been decoupled from the older shared SQLite report path.
- Development cutover has been validated by showing that new scheduled runs increase Postgres counts while SQLite no longer increases for that path.
- Production cutover has also been executed, bringing production onto the same direct Postgres write model for new runs.

Primary references:

- `docs/specs/prd-postgres-migration.md`
- `docs/specs/trd-postgres-migration.md`
- `docs/specs/implementation-plan-postgres-migration.md`
- `docs/ops/operations.md`

## Current architecture snapshot

### Interactive agent

- Runs as a single deployment in `a2w-lucas`
- Uses OpenRouter through the `openai-compatible` backend path
- Keeps Slack interaction and approved emergency-action controls
- Stores runtime state through the current storage abstraction

### Scheduled scanner

- Runs as a CronJob in `a2w-lucas`
- Uses the report-oriented prompt path
- Targets all namespaces in the current development rollout
- Writes new scheduled run state directly to Postgres in the current dev cutover state

### Dashboard

- Runs from a dedicated Harbor image
- Auth is secret-backed
- Reads runtime data from Postgres
- No longer uses the older shared report DB file as its intended primary source

### Postgres service

- Runs as a dedicated in-cluster deployment and service
- Uses a dedicated PVC and auth secret
- Is the current system of record for new scheduled run records in dev

## Current state by deployment stage

### Development (`goyo-dev`)

- OpenRouter-based provider path is in use
- dashboard is running from the Harbor dashboard image
- agent and CronJob are running with `POSTGRES_SHADOW_VALIDATE=false`
- current development state reflects direct Postgres writes for scheduled runs

### Production

- Production now runs the dedicated Harbor dashboard image and direct Postgres-backed agent/cron runtime for new runs
- Production still retains some cleanup debt in templates/scripts, but the live storage/runtime cutover has been completed

## What is still intentionally not finished

- All cluster/runtime secret values are intentionally excluded from docs and must stay out of Git
- The existing feature-level specs remain the source of truth for detailed acceptance criteria and deep design decisions
- Some repo templates and generation paths may still need cleanup as the final source-of-truth follows the now-completed production runtime

## How to use this document

- Start here if you want a single technical summary of the platform state
- Use `docs/specs/index.md` to jump to the detailed feature specs
- Use `docs/ops/current-runtime-settings.md` to see the current non-secret runtime settings and secret reference map
