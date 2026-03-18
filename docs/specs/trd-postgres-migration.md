# TRD: Postgres Migration

## Objective

Design a safe migration from the current shared SQLite file model to a dedicated Postgres-backed persistence layer for Lucas.

The first release must solve the core storage-coupling problem without taking on SQLite import complexity or preserving dashboard dependencies that force shared filesystem access.

## Design principles

### Single persistence source of truth

Once cutover is complete, the migrated Lucas runtime state should exist in Postgres only. Do not keep a long-lived split-brain model between SQLite and Postgres.

### Development first

The first rollout target is development. Production design comes only after dev behavior is stable.

### Fresh start over backfill

The first release favors safe clean initialization over one-time historical migration.

### Remove hidden file coupling

The migration is only complete if the dashboard no longer depends on the shared `/data/lucas.db` and shared `/data/lucas.log` model for the report experience.

## Current coupling

Today the following state is persisted in SQLite-backed paths:

- `runs`
- `fixes`
- `token_usage`
- `slack_sessions`
- `recovery_actions`
- `run_summaries`

The dashboard currently reads directly from the same database file that the agent and cron write to. This is the operational bottleneck that made dashboard restarts sensitive to PVC topology.

## Target architecture

### Postgres service

Introduce a dedicated Postgres workload/service for Lucas in development first.

Recommended v1 shape:

- single-instance Postgres deployment or stateful workload
- dedicated PVC for Postgres only
- service reachable from agent, cron, and dashboard

### Python runtime storage layer

Replace the SQLite-backed `RunStore` / `SessionStore` implementation with a Postgres-backed equivalent.

Suggested implementation strategy:

- keep the existing store interface shape where practical
- swap the backend implementation from SQLite to Postgres
- minimize call-site churn in `cron_runner.py`, interactive session handling, and recovery-action persistence

### Dashboard storage layer

Replace `src/dashboard/db/sqlite.go` with a Postgres-backed data access layer.

The dashboard should remain a database reader, not a log-file or shared-storage consumer.

## Table model

The following logical tables should exist in Postgres:

- `runs`
- `fixes`
- `token_usage`
- `slack_sessions`
- `recovery_actions`
- `run_summaries`

The schema can remain conceptually aligned with the current SQLite tables to keep the migration focused on storage, not domain redesign.

## Live log viewer decision

The current dashboard live log viewer depends on `/data/lucas.log`, which keeps the dashboard tied to shared filesystem state.

For v1, the recommended technical choice is:

- remove the live log viewer, or
- reduce it to already-persisted run log content stored in Postgres

Do **not** keep a shared file dependency for live logs in the first Postgres migration release.

## Migration phases

### Phase 1: Shadow validation

In dev, deploy Postgres and exercise the new storage layer without immediately removing the old path from every runtime surface.

Validation goals:

- schema creation works
- Python runtime can connect and write
- dashboard can read expected rows
- auth/secrets/networking are stable

### Phase 2: Dev cutover

Switch dev agent, cron, and dashboard to Postgres as the only report-state backend.

Success condition:

- no remaining dependency on the shared SQLite DB file for dashboard or reporting

### Phase 3: Production plan

Only after dev stability is proven:

- produce a production rollout plan
- decide whether production should also start fresh or whether a separate migration path is needed later

## Configuration model

Suggested new runtime envs:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- optionally `POSTGRES_SSLMODE`

The Python and Go runtimes should read the same logical Postgres connection settings.

## Validation strategy

### Unit tests

Add tests for:

- schema initialization
- CRUD behavior for each logical table family
- dashboard query compatibility against Postgres-backed rows

### Integration tests

In dev, verify:

- agent writes runs/fixes/tokens to Postgres
- dashboard reads runs and detail views from Postgres
- namespace summary rows still work
- session mappings and recovery actions still persist

### Acceptance behavior

The migration is considered technically correct when:

- dashboard restarts are no longer blocked by shared SQLite PVC coupling
- agent/cron/dashboard all read/write the same Postgres database
- report retrieval works without shared `/data/lucas.db`
- the live log viewer no longer forces shared filesystem coupling

## Risks

- A half-migrated dashboard that still reads local files would hide the real coupling problem
- Schema drift between Python and Go storage implementations could create subtle failures
- Shadow validation can give false confidence if it does not exercise dashboard reads and cron writes together

## Recommended rollout

### Phase 1

Dev-only Postgres deployment plus shadow validation.

### Phase 2

Dev cutover and removal of SQLite report dependency.

### Phase 3

Production design and rollout planning after stable dev operation.
