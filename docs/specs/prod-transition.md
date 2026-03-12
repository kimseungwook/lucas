# Production Transition

## Summary

Lucas is development-ready in `goyo-dev` and needs a production transition plan that preserves the same Slack operator experience while hardening deployment, RBAC, secrets, and image distribution for `goyo-prd`.

## Current State

- Development validation happens in `goyo-dev`.
- The live dev deployment uses bootstrap-style public runtime containers plus ConfigMap-mounted code because `ghcr.io/a2wio/*` pulls were blocked.
- Slack emergency actions are implemented and validated in development.
- Scheduled monitoring uses `TARGET_NAMESPACES=all` and status-first reporting.

## Production Target

- Production context: `goyo-prd`
- Control namespace: `lucas`
- Initial monitored namespace scope: `all`
- Dashboard enabled in production
- Secrets managed through direct Kubernetes Secrets for this production path.
- Dev and prod share the same Slack emergency command surface

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
- Production should not rely on the bootstrap workaround used in development.
- Production images should be pulled from the configured registry with `imagePullSecrets`.
- Production should not depend on `:latest` as the final rollout policy.

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

### Out of scope

- Full production deployment execution.
- Token rotation execution on behalf of the operator.
- Final image promotion pipeline.
- Production ingress and certificate issuance.

## Acceptance Criteria

- The production-transition policy is documented in the repo.
- Tracked production env templates do not contain live secrets.
- A local env file can be used to drive manifest generation.
- Slack command parity is documented across dev and prod.
- Namespace scope defaults to all namespaces but can later be narrowed by configuration.
- Docs build and tests continue to pass.

## Rollout Order

1. Sanitize tracked production templates.
2. Add production-transition spec.
3. Support local env-file driven generation.
4. Add explicit namespace-allowlist semantics in code and manifests.
5. Validate docs and tests.
6. Fill production values locally and generate direct Secret manifests and workload manifests.
7. Apply to production only after manual review.

## Risks

- Carrying dev bootstrap deployment patterns into production.
- Leaving Slack tokens in tracked files.
- Enabling all-namespace emergency actions without channel/user controls.
- Assuming dev cluster behavior exactly matches prod cluster pull/auth behavior.

## Follow-Up Hardening

- Replace bootstrap deployment with prebuilt pinned images.
- Add namespace allowlists once operational confidence is established.
- Rotate all Slack tokens used during testing.
- Introduce stronger audit persistence for Slack emergency actions.
