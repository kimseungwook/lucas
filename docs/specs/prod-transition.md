# Production Transition

## Summary

Lucas is development-ready in `goyo-dev` and now needs a production transition that closes the remaining runtime gap between development and production. The target is to make `goyo-prd` use the same Postgres-backed storage contract and dedicated dashboard image model already validated in development, while preserving the existing Slack operator experience and current prod guardrails.

## Current State

- Development validation happens in `goyo-dev`.
- Development has already validated direct Postgres writes for new scheduled runs.
- Slack emergency actions are implemented and validated in development.
- Scheduled monitoring uses `TARGET_NAMESPACES=all` and status-first reporting.

### Observed production runtime drift (`goyo-prd`, namespace `lucas`)

- Production agent still runs `python:3.12-slim` with bootstrap-style package installation and ConfigMap-mounted code.
- Production cron still runs `python:3.12-slim` with ConfigMap-mounted code and writes through `SQLITE_PATH=/data/lucas.db`.
- Production dashboard is not yet on the dedicated Harbor dashboard image and is not yet wired to Postgres.
- `lucas-postgres`, `lucas-postgres-auth`, and `lucas-postgres-data` do not yet exist in production.
- Production workloads currently run in namespace `lucas`, while many repo manifests still default to `a2w-lucas` and must not be applied to prod unchanged.

## Production Target

- Production context: `goyo-prd`
- Control namespace: `lucas`
- Initial monitored namespace scope: `all`
- Dashboard enabled in production
- Secrets managed through direct Kubernetes Secrets for this production path.
- Dev and prod share the same Slack emergency command surface
- Agent and CronJob write runtime state directly to Postgres.
- Dashboard reads runtime state from Postgres using the dedicated Harbor image.
- Shared SQLite/PVC report coupling is no longer the primary production data path.

## Product Policy

### Command parity

The Slack emergency-action command set must remain identical between development and production.

Supported commands:

- `describe pod`
- `pod log`
- `restart deployment`
- `restart statefulset`
- `delete pod`
- `rollout status deployment/statefulset`
- `rollout undo deployment`
- `scale deployment/statefulset`

### Namespace policy

- Initial production rollout permits all namespaces.
- Namespace narrowing is a hardening follow-up, not a blocker for the first production rollout.
- The code and configuration must be prepared for later namespace allowlisting without changing the Slack command syntax.

### Slack safety policy

- Mutating commands require explicit confirmation.
- Allowed channel and allowed user controls remain active.
- All executions must remain auditable.

## Configuration Source of Truth

- Git-tracked manifests and overlays are the deployment source of truth.
- `k8s/prod.env.template` is a redacted reference template only.
- `k8s/prod.env.local` is a local untracked operator convenience file.
- Secret values must never remain in tracked plaintext files and must be created as direct Kubernetes Secrets for this production path.

## Deployment Model

- Dev and prod are separated before production apply.
- Production should not rely on the bootstrap workaround still present in the legacy prod runtime.
- Production images should be pulled from the configured registry with `imagePullSecrets`.
- Production should not depend on `:latest` as the final rollout policy.
- Production should converge toward the same packaged-image model already validated in development.

## Required Production Inputs

- `KUBECTL_CONTEXT`
- `LUCAS_NAMESPACE`
- `TARGET_NAMESPACES`
- `LLM_*`
- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`
- `SLACK_WEBHOOK_URL`
- `SLACK_ACTION_ALLOWED_CHANNELS`
- `SLACK_ACTION_ALLOWED_USERS`
- `SLACK_ACTION_ALLOWED_NAMESPACES`
- `DASHBOARD_HOST`
- `DASHBOARD_AUTH_*`
- `IMAGE_REGISTRY`
- `IMAGE_PULL_SECRET`

## Implementation Scope

### In scope

- Add production-transition docs and link them into the spec set.
- Support local env-file driven manifest generation.
- Support both `manual` and `sealed-secrets` secret backends, with `manual` as the chosen production path for this environment.
- Keep tracked env templates redacted.
- Add explicit namespace-allowlist configuration semantics to Slack actions.
- Align generated manifests with Slack emergency-action env settings.
- Create the production Postgres prerequisites in namespace `lucas`.
- Replace the legacy production agent/cron runtime path with the packaged image path.
- Move the production dashboard to the dedicated Harbor dashboard image and Postgres env wiring.
- Execute the production cutover in ordered stages with explicit rollback points.

### Out of scope

- Token rotation execution on behalf of the operator.
- Final image promotion pipeline.
- Production ingress and certificate issuance.
- Large feature-surface expansion unrelated to the production baseline.

## Acceptance Criteria

- The production-transition policy is documented in the repo.
- Tracked production env templates do not contain live secrets.
- A local env file can be used to drive manifest generation.
- Slack command parity is documented across dev and prod.
- Namespace scope defaults to all namespaces but can later be narrowed by configuration.
- `goyo-prd` has a healthy `lucas-postgres` deployment, service, PVC, and auth secret.
- Production dashboard runs from the dedicated Harbor image and reads runtime state from Postgres.
- Production agent and CronJob run with the Postgres-backed path and `POSTGRES_SHADOW_VALIDATE=false`.
- A manual post-cutover cron run succeeds and new runs increase Postgres without relying on SQLite as the primary runtime store.
- Docs build and tests continue to pass.

## Rollout Order

1. Sanitize tracked production templates.
2. Add production-transition spec.
3. Support local env-file driven generation.
4. Add explicit namespace-allowlist semantics in code and manifests.
5. Validate docs and tests.
6. Export the current production manifests and keep them as rollback artifacts.
7. Create the production Postgres prerequisites in namespace `lucas`.
8. Cut over dashboard first and verify `/health` plus runtime reads.
9. Cut over the interactive agent second and verify Slack continuity.
10. Cut over the CronJob third, trigger one manual job, and verify direct Postgres writes.
11. Hold through at least one full scheduled cycle before considering legacy report paths retired.

## Risks

- Carrying dev bootstrap deployment patterns into production.
- Leaving Slack tokens in tracked files.
- Enabling all-namespace emergency actions without channel/user controls.
- Assuming dev cluster behavior exactly matches prod cluster pull/auth behavior.
- Creating production drift by applying `a2w-lucas` namespace manifests directly into a cluster whose live namespace is `lucas`.
- Attempting production cutover without first creating `lucas-postgres-auth` and `harbor-creds` in `lucas`.
- Treating the current production SQLite/ConfigMap runtime as “close enough” to the development baseline.

## Production cutover checklist

### Preconditions

- Confirm Kubernetes context is `goyo-prd`.
- Confirm control namespace is `lucas`.
- Export and save the current live manifests for:
  - `Deployment/a2w-lucas-agent`
  - `CronJob/a2w-lucas`
  - `Deployment/dashboard`
  - related `Secret`, `PVC`, and `Service` objects
- Confirm the production auth/input secrets required for rollout exist or are ready to be created:
  - `lucas-postgres-auth`
  - `harbor-creds`
  - `dashboard-auth`
  - `llm-auth` / `llm-auth-openrouter`
  - `slack-bot`
  - `slack-webhook`

### Postgres prerequisites

- Create `Secret/lucas-postgres-auth` in namespace `lucas`.
- Create `PersistentVolumeClaim/lucas-postgres-data` in namespace `lucas`.
- Create `Deployment/lucas-postgres` in namespace `lucas`.
- Create `Service/lucas-postgres` in namespace `lucas`.
- Verify Postgres readiness before changing any Lucas workload.

### Dashboard cutover

- Deploy the dedicated Harbor image for dashboard.
- Use Postgres env wiring in place of the older shared SQLite/report path.
- Do not keep the dashboard dependent on the shared `lucas-data` PVC as its primary report path.
- Verify `/health`, login, and current run visibility before proceeding.

### Agent cutover

- Replace the bootstrap-style runtime with the packaged image path.
- Preserve the existing prod operator semantics:
  - namespace scope
  - Slack emergency-action policy
  - current provider/model choice unless intentionally changed
- Set `POSTGRES_SHADOW_VALIDATE=false` for the final state.
- Verify the interactive agent remains healthy and Slack continuity is preserved.

### Cron cutover

- Replace the bootstrap-style runtime with the packaged image path.
- Set `POSTGRES_SHADOW_VALIDATE=false`.
- Trigger one manual job from the updated template before relying on the schedule.
- Verify the manual run completes successfully.

### Success criteria

- Dashboard is healthy and reading Postgres-backed runtime state.
- Agent is healthy after rollout.
- Manual cron run succeeds.
- The next scheduled cron run succeeds.
- New runs appear in Postgres and the runtime no longer depends on SQLite as the primary report path.

### Rollback boundaries

- If dashboard rollout fails, roll back dashboard only and stop.
- If agent rollout fails, roll back agent and stop before touching cron.
- If cron rollout fails, roll back cron before the next scheduled window.
- If Postgres itself is unhealthy, stop the cutover and revert workloads to the previous known-good runtime path.

## Follow-Up Hardening

- Add namespace allowlists once operational confidence is established.
- Rotate all Slack tokens used during testing.
- Introduce stronger audit persistence for Slack emergency actions.
- Add Postgres backup, restore, and indexing as explicit production hardening.
- Remove remaining legacy SQLite-centered docs and manifest generation paths once production parity is complete.
