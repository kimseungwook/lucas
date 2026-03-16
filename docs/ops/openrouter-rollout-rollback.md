# OpenRouter Rollout and Rollback

This document captures the live rollout shape used for Lucas when switching dev and prod from Groq/Gemini-style `openai-compatible` providers to OpenRouter with `stepfun/step-3.5-flash:free`.

## Current Intent

- Provider: `openrouter`
- Model: `stepfun/step-3.5-flash:free`
- Base URL: `https://openrouter.ai/api/v1`
- Canonical secret/env: `OPENROUTER_API_KEY`
- Backward-compatible app support exists for `OPENROUTE_API_KEY`, but new runtime wiring should use `OPENROUTER_API_KEY`

## Important Runtime Notes

- Updating only env vars is not enough when Lucas code is mounted from ConfigMaps.
- In both clusters, live runtime code came from:
  - `lucas-agent-code`
  - `lucas-cron-code`
- If the repo code changes provider logic, refresh those ConfigMaps before rollout.

## Dev Rollout Shape

Namespace: `a2w-lucas`

### Required surfaces

- Secret: `llm-auth-openrouter`
- Deployment: `a2w-lucas-agent`
- CronJob: `a2w-lucas`
- ConfigMaps:
  - `lucas-agent-code`
  - `lucas-cron-code`

### Dev verification

- Direct OpenRouter probe returns `200`
- Interactive pod log shows:
  - `provider=openrouter`
  - `model=stepfun/step-3.5-flash:free`
- One-off single-namespace cron smoke completes successfully
- Scheduled cron may be enabled after the smoke path is green

## Prod Rollout Shape

Namespace: `lucas`

### Required surfaces

- Secret: `llm-auth-openrouter`
- Deployment: `a2w-lucas-agent`
- CronJob: `a2w-lucas`
- ConfigMaps:
  - `lucas-agent-code`
  - `lucas-cron-code`

### Prod-specific storage note

Prod initially failed before Lucas started because OCI block volumes could not attach on the wrong node pool.

Observed failure pattern:

`node has in transit encryption enabled, but attachment type is not paravirtualized`

The safe remediation used in production was to keep Lucas on the node pool that matched the PVC-selected node lineage. In practice this was done with:

- `nodeSelector: { goyo-svc: backoffice }`

Do not remove that blindly unless storage behavior is revalidated.

## Rollout Checklist

### 1. Secret

- Create or update `llm-auth-openrouter`
- Store `OPENROUTER_API_KEY`

### 2. Code surface

- Refresh `lucas-agent-code`
- Refresh `lucas-cron-code`

### 3. Runtime env

Set on both interactive deployment and cronjob:

- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `OPENROUTER_API_KEY` from secret

### 4. Interactive smoke

- Scale deployment to `1`
- Wait for rollout
- Confirm log shows OpenRouter provider/model
- Run one real backend call in-pod and expect `OK`

### 5. Cron smoke

- Keep real cron suspended at first if risk-sensitive
- Run a one-off single-namespace job derived from the CronJob
- Confirm run completes with `status=ok` or `status=issues_found`

### 6. Scheduled enablement

- Unsuspend the real CronJob only after smoke passes
- Confirm at least one real scheduled run completes

## Rollback Checklist

### Runtime rollback order

1. Suspend CronJob
2. Scale interactive deployment to `0`
3. Restore previous provider env on deployment and cronjob
4. Restore previous code ConfigMaps if provider logic changed
5. Re-enable interactive deployment
6. Run one interactive smoke test
7. Re-enable scheduled cron only after smoke passes

### Commands to remember

Suspend cron:

```bash
kubectl --context <ctx> -n <ns> patch cronjob a2w-lucas --type merge -p '{"spec":{"suspend":true}}'
```

Scale agent down:

```bash
kubectl --context <ctx> -n <ns> scale deployment a2w-lucas-agent --replicas=0
```

Scale agent up:

```bash
kubectl --context <ctx> -n <ns> scale deployment a2w-lucas-agent --replicas=1
```

### What to restore

Restore these env values to the previous provider if needed:

- `LLM_BACKEND`
- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_BASE_URL`
- secret ref for API key

If runtime code was refreshed via ConfigMap, restore:

- `lucas-agent-code`
- `lucas-cron-code`

## Success Signals

- Interactive log says `provider=openrouter model=stepfun/step-3.5-flash:free`
- In-pod Lucas backend call returns `OK`
- One-off cron smoke completes
- Real scheduled cron completes

## Failure Signals

- OpenRouter direct probe returns non-200
- Interactive pod never gets past volume attach / node scheduling
- Logs show old provider after env patch
- Cron smoke job fails before Lucas starts
- SQLite run/token records stop updating

## Git Note

The repo changes were committed locally, but push to `origin` failed with `403` under the authenticated `kimseungwook` account. Cluster runtime may therefore be ahead of the remote repository until GitHub access is corrected.
