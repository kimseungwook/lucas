# PRD: Postgres Migration

## Summary

Lucas should replace its shared SQLite persistence model with a dedicated Postgres-backed storage layer so the agent, cron runner, and dashboard can operate without sharing a single ReadWriteOnce filesystem volume.

The first migration release is intentionally constrained:

- Postgres becomes the single persistence layer for Lucas runtime state
- the rollout starts in development first
- the migration uses a fresh-start database, not a SQLite import
- the dashboard live log viewer is removed or reduced so the dashboard can become stateless relative to shared filesystem storage
- the rollout uses a short shadow-validation phase before cutover

## Problem

The current storage model ties multiple runtime components to the same SQLite file on the same PVC:

- interactive agent
- scheduled cron job
- dashboard

This creates multiple operational problems:

1. dashboard availability depends on the same RWO volume as agent and cron
2. rollout behavior is constrained by storage attachment semantics rather than application health
3. dashboard restart safety depends on the PVC topology of unrelated workloads
4. future reporting features increase query and persistence complexity on a single shared SQLite file

The issue is not just that SQLite exists. The real problem is **shared file coupling** across independently managed workloads.

## Goal

- Make Postgres the single source of truth for Lucas runtime data.
- Remove dashboard dependence on the shared SQLite PVC.
- Keep agent, cron, and dashboard stateless relative to the report database after the migration.
- Roll out safely in development first using a shadow-validation step.

## Non-Goals

- One-time import of old SQLite data in the first release
- Immediate production rollout in the first release
- Dashboard redesign beyond storage-driven changes
- Introducing a separate logging backend in the first release

## Users and stakeholders

- Platform operators running Lucas in Kubernetes
- SREs consuming dashboard and scheduled reports
- Maintainers responsible for deployment stability and rollout safety

## User needs

### Platform operator

Needs dashboard restarts and agent/cron rollouts to stop failing because of shared SQLite storage topology.

### SRE

Needs the same report and run data to remain visible through the dashboard after the migration.

### Maintainer

Needs a migration path that is operationally safe and does not require risky one-time backfill logic in the first release.

## Scope

### In scope

- Replace SQLite-backed runtime persistence with Postgres for:
  - `runs`
  - `fixes`
  - `token_usage`
  - `slack_sessions`
  - `recovery_actions`
  - `run_summaries`
- Add development-first Postgres deployment/service configuration
- Remove or reduce dashboard live log viewer dependency on `/data/lucas.log`
- Introduce a shadow-validation step before final cutover

### Out of scope

- SQLite data import in v1
- Production rollout in the same first increment
- Full observability/logging redesign
- Postgres high availability in v1

## Functional requirements

### FR-1 Single persistence layer

Postgres must become the only persistence layer for the migrated reporting/runtime state listed above.

### FR-2 Development-first rollout

The migration must be validated in development first before any production transition is attempted.

### FR-3 Fresh start in v1

The first release must not depend on SQLite data import. The migration should start with a clean Postgres database.

### FR-4 Dashboard statelessness for report storage

After cutover, the dashboard must read report data from Postgres and must no longer depend on the shared SQLite PVC for report access.

### FR-5 Log viewer scope reduction

If the dashboard live log viewer would reintroduce shared filesystem coupling, it must be removed or reduced in v1.

### FR-6 Shadow validation

The migration design must include a pre-cutover validation step where Postgres wiring is exercised in development before old storage paths are retired.

## Success metrics

- Dashboard rollout no longer depends on the shared SQLite PVC
- Agent/cron/dashboard can be restarted independently of the old shared DB file
- Postgres becomes the only source of truth for the migrated runtime tables
- Development rollout completes without SQLite import complexity

## Acceptance criteria

- PRD/TRD clearly state the storage boundary shift to Postgres
- Dashboard live log viewer dependency is explicitly addressed
- Fresh-start migration is explicit
- Docs build succeeds after the new spec files are added

## Risks

- Partial migration can leave hidden shared filesystem coupling in place
- Keeping the live log viewer unchanged can invalidate the “stateless after migration” claim
- Attempting SQLite import in v1 would add unnecessary risk and delay

## Recommended rollout

### Phase 1

Dev-only Postgres deployment and storage-layer integration with shadow validation.

### Phase 2

Cut over dev runtime and dashboard to Postgres, leaving SQLite path behind.

### Phase 3

Plan and execute production rollout after dev stability is proven.
