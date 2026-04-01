# Current Runtime Settings

This document records the current non-secret runtime settings and secret references for Lucas.

## Scope

- Secret values are intentionally omitted.
- This document records effective runtime values and secret reference names.
- Where a feature is not currently enabled in the live dev rollout, the template default is noted instead.
- Use `docs/ops/current-handoff-state.md` for the active cross-session handoff record.

## Current live development target

- Cluster context: `goyo-dev`
- Namespace: `a2w-lucas`

## Interactive agent deployment

Workload:

- Kubernetes object: `Deployment/a2w-lucas-agent`
- Image: `gdhb.goyoai.com/lukas/lucas-agent:postgres-shadow`
- Image pull secret: `harbor-creds`
- PVC mount: `lucas-data` -> `/data`

Current non-secret env:

- `TARGET_NAMESPACE=default`
- `TARGET_NAMESPACES=default`
- `POD_INCIDENT_TARGET_NAMESPACES=` (template default; empty falls back to `TARGET_NAMESPACE(S)`)
- `POD_INCIDENT_TARGET_WORKLOADS=` (template default; empty means all workloads in the scoped namespaces)
- `SRE_MODE=watcher`
- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `SQLITE_PATH=/data/lucas.db`
- `SCAN_INTERVAL_SECONDS=3600`
- `PROMPT_FILE=/app/master-prompt-interactive-report.md`
- `SLACK_EMERGENCY_ACTIONS_ENABLED=true`
- `SLACK_ACTION_ALLOWED_CHANNELS=C0AKTLTBP4M`
- `SLACK_ACTION_ALLOWED_USERS=`
- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `POSTGRES_SHADOW_VALIDATE=false`

Secret references:

- `LLM_API_KEY` -> `Secret/llm-auth:key=api-key`
- `SLACK_BOT_TOKEN` -> `Secret/slack-bot:key=bot-token`
- `SLACK_APP_TOKEN` -> `Secret/slack-bot:key=app-token`
- `GEMINI_API_KEY` -> `Secret/llm-auth-gemini:key=api-key`
- `OPENROUTER_API_KEY` -> `Secret/llm-auth-openrouter:key=OPENROUTER_API_KEY`
- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Scheduled CronJob

Workload:

- Kubernetes object: `CronJob/a2w-lucas`
- Schedule: `*/10 * * * *`
- Image: `gdhb.goyoai.com/lukas/lucas:postgres-shadow`
- Image pull secret: `harbor-creds`
- PVC mount: `lucas-data` -> `/data`

Current non-secret env:

- `TARGET_NAMESPACE=default`
- `TARGET_NAMESPACES=all`
- `POD_INCIDENT_TARGET_NAMESPACES=` (template default; empty falls back to `TARGET_NAMESPACE(S)`)
- `POD_INCIDENT_TARGET_WORKLOADS=` (template default; empty means all workloads in the scoped namespaces)
- `SRE_MODE=report`
- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `SQLITE_PATH=/data/lucas.db`
- `PROMPT_FILE=/app/master-prompt-report.md`
- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `POSTGRES_SHADOW_VALIDATE=false`

Secret references:

- `LLM_API_KEY` -> `Secret/llm-auth:key=api-key`
- `SLACK_WEBHOOK_URL` -> `Secret/slack-webhook:key=webhook-url`
- `OPENROUTER_API_KEY` -> `Secret/llm-auth-openrouter:key=OPENROUTER_API_KEY`
- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Dashboard deployment

Workload:

- Kubernetes object: `Deployment/dashboard`
- Image: `gdhb.goyoai.com/lukas/lucas-dashboard:postgres`
- Image pull secret: `harbor-creds`
- No shared `lucas-data` PVC mount

Current non-secret env:

- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `PORT=8080`

Current probes/resources:

- `livenessProbe.initialDelaySeconds=20`
- `livenessProbe.periodSeconds=15`
- `readinessProbe.initialDelaySeconds=20`
- `readinessProbe.periodSeconds=10`
- requests: `cpu=100m`, `memory=128Mi`
- limits: `cpu=500m`, `memory=1Gi`

Secret references:

- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`
- `AUTH_USER` -> `Secret/dashboard-auth:key=username`
- `AUTH_PASS` -> `Secret/dashboard-auth:key=password`

## Postgres service

Workload:

- Kubernetes object: `Deployment/lucas-postgres`
- Image: `docker.io/library/postgres:16-alpine`
- Service: `Service/lucas-postgres`
- Service port: `5432`
- PVC: `lucas-postgres-data`

Current non-secret env:

- `PGDATA=/var/lib/postgresql/data/pgdata`

Secret references:

- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Current live production target

- Cluster context: `goyo-prd`
- Namespace: `lucas`

## Production interactive agent deployment

Workload:

- Kubernetes object: `Deployment/a2w-lucas-agent`
- Image: `gdhb.goyoai.com/lukas/lucas-agent:report-full-multi-20260331-182013`
- Image pull secret: `harbor-creds`
- No shared `lucas-data` PVC mount

Current non-secret env:

- `TARGET_NAMESPACE=default`
- `TARGET_NAMESPACES=default`
- `POD_INCIDENT_TARGET_NAMESPACES=` (template default; empty falls back to `TARGET_NAMESPACE(S)`)
- `POD_INCIDENT_TARGET_WORKLOADS=` (template default; empty means all workloads in the scoped namespaces)
- `SRE_MODE=watcher`
- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `SQLITE_PATH=/tmp/lucas.db`
- `SCAN_INTERVAL_SECONDS=3600`
- `PROMPT_FILE=/app/master-prompt-interactive-report.md`
- `SLACK_EMERGENCY_ACTIONS_ENABLED=true`
- `SLACK_ACTION_ALLOWED_CHANNELS=C0AKTLTBP4M`
- `SLACK_ACTION_ALLOWED_USERS=`
- `SLACK_ACTION_ALLOWED_NAMESPACES=`
- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `POSTGRES_SHADOW_VALIDATE=false`

Secret references:

- `LLM_API_KEY` -> `Secret/llm-auth:key=api-key`
- `SLACK_BOT_TOKEN` -> `Secret/slack-bot:key=bot-token`
- `SLACK_APP_TOKEN` -> `Secret/slack-bot:key=app-token`
- `OPENROUTER_API_KEY` -> `Secret/llm-auth-openrouter:key=OPENROUTER_API_KEY`
- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Production scheduled CronJob

Workload:

- Kubernetes object: `CronJob/a2w-lucas`
- Schedule: `*/10 * * * *`
- Image: `gdhb.goyoai.com/lukas/lucas:report-full-multi-20260331-182013`
- Image pull secret: `harbor-creds`
- No shared `lucas-data` PVC mount

Current non-secret env:

- `TARGET_NAMESPACE=default`
- `TARGET_NAMESPACES=all`
- `POD_INCIDENT_TARGET_NAMESPACES=` (template default; empty falls back to `TARGET_NAMESPACE(S)`)
- `POD_INCIDENT_TARGET_WORKLOADS=` (template default; empty means all workloads in the scoped namespaces)
- `SRE_MODE=report`
- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `SQLITE_PATH=/tmp/lucas.db`
- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `POSTGRES_SHADOW_VALIDATE=false`

Secret references:

- `LLM_API_KEY` -> `Secret/llm-auth:key=api-key`
- `SLACK_WEBHOOK_URL` -> `Secret/slack-webhook:key=webhook-url`
- `OPENROUTER_API_KEY` -> `Secret/llm-auth-openrouter:key=OPENROUTER_API_KEY`
- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Production dashboard deployment

Workload:

- Kubernetes object: `Deployment/dashboard`
- Image: `gdhb.goyoai.com/lukas/lucas-dashboard:attention-pods-20260331-140150`
- Image pull secret: `harbor-creds`
- No shared `lucas-data` PVC mount

Current non-secret env:

- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `PORT=8080`

Current probes/resources:

- `livenessProbe.initialDelaySeconds=20`
- `livenessProbe.periodSeconds=15`
- `readinessProbe.initialDelaySeconds=20`
- `readinessProbe.periodSeconds=10`
- requests: `cpu=100m`, `memory=128Mi`
- limits: `cpu=500m`, `memory=1Gi`

Secret references:

- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`
- `AUTH_USER` -> `Secret/dashboard-auth:key=username`
- `AUTH_PASS` -> `Secret/dashboard-auth:key=password`

## Production Postgres service

Workload:

- Kubernetes object: `Deployment/lucas-postgres`
- Image: `docker.io/library/postgres:16-alpine`
- Service: `Service/lucas-postgres`
- Service port: `5432`
- PVC: `lucas-postgres-data`

Current non-secret env:

- `PGDATA=/var/lib/postgresql/data/pgdata`

Secret references:

- `POSTGRES_DB` -> `Secret/lucas-postgres-auth:key=database`
- `POSTGRES_USER` -> `Secret/lucas-postgres-auth:key=username`
- `POSTGRES_PASSWORD` -> `Secret/lucas-postgres-auth:key=password`

## Current template defaults for optional hardening features

These are the current template defaults from `k8s/dev.env.template` and `k8s/prod.env.template` unless overridden in a live rollout.

### Redis Safe Self-Recovery

- `REDIS_SELF_HEAL_ENABLED=false`
- `REDIS_SELF_HEAL_MUTATIONS_ALLOWED=false`
- `REDIS_SELF_HEAL_ALLOWED_ENVIRONMENTS=dev`
- `REDIS_SELF_HEAL_COOLDOWN_SECONDS=600`
- `REDIS_SELF_HEAL_NAMESPACES=`

### Security monitor / virtual-node compensating control

- `SECURITY_MONITOR_ENABLED=false`
- `SECURITY_MONITOR_NAMESPACES=`
- `SECURITY_MONITOR_MODE=report-only`

## Current template defaults for provider settings

Development template reference (`k8s/dev.env.template`):

- `KUBECTL_CONTEXT=goyo-dev`
- `LUCAS_NAMESPACE=a2w-lucas`
- `TARGET_NAMESPACES=all`
- `OPENROUTER_MODEL=stepfun/step-3.5-flash:free`
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `SLACK_EMERGENCY_ACTIONS_ENABLED=true`
- `SRE_MODE=watcher`
- `SCAN_INTERVAL_SECONDS=3600`
- `DASHBOARD_ENABLED=true`
- `DASHBOARD_AUTH_USER=a2wmin`

Production template reference (`k8s/prod.env.template`):

- `KUBECTL_CONTEXT=goyo-prd`
- `LUCAS_NAMESPACE=lucas`
- `TARGET_NAMESPACES=all`
- `LLM_BACKEND=openai-compatible`
- `LLM_PROVIDER=openrouter`
- `LLM_MODEL=stepfun/step-3.5-flash:free`
- `LLM_BASE_URL=https://openrouter.ai/api/v1`
- `OPENROUTER_MODEL=stepfun/step-3.5-flash:free`
- `OPENROUTER_BASE_URL=https://openrouter.ai/api/v1`
- `POSTGRES_HOST=lucas-postgres`
- `POSTGRES_PORT=5432`
- `POSTGRES_SSLMODE=disable`
- `POSTGRES_SHADOW_VALIDATE=false`
- `SRE_MODE=autonomous`
- `SCAN_INTERVAL_SECONDS=3600`
- `DASHBOARD_ENABLED=true`
- `DASHBOARD_AUTH_USER=a2wmin`
- `IMAGE_REGISTRY=gdhb.goyoai.com/lukas`
- `IMAGE_PULL_SECRET=harbor-creds`

## Related documents

- `docs/specs/current-platform-state.md`
- `docs/specs/index.md`
- `docs/guide/configuration.md`
- `docs/ops/operations.md`
