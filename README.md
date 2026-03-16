# A2W: Lucas

A Kubernetes operations and reliability agent. It runs in-cluster, inspects pods and logs, can report or remediate issues based on mode, and exposes a dashboard backed by SQLite.

## What it does

- Slack-first investigations with thread context.
- Scheduled scans across namespaces.
- Optional remediation when allowed.
- Dashboard for runs, sessions, and token usage.

## Modes

Interactive agent (`Dockerfile.agent`):

- `SRE_MODE=autonomous`: can fix issues.
- `SRE_MODE=watcher`: report-only.

CronJob agent (`Dockerfile.lucas`):

- `SRE_MODE=autonomous`: can fix issues.
- `SRE_MODE=report`: report-only.

## Environment variables

### Interactive agent

Required:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`

LLM:

- `LLM_BACKEND` (`claude-code` or `openai-compatible`)
- `LLM_PROVIDER` (`anthropic`, `groq`, `kimi`, `gemini`, `openrouter`)
- `LLM_API_KEY` or provider-specific env such as `GROQ_API_KEY` / `KIMI_API_KEY` / `GEMINI_API_KEY` / `OPENROUTER_API_KEY`
- `LLM_MODEL` for openai-compatible providers
- OpenRouter (optional): default model is `stepfun/step-3.5-flash:free` when `LLM_PROVIDER=openrouter`.

Legacy Claude compatibility:

- `ANTHROPIC_API_KEY`

Common:

- `SRE_MODE` (`autonomous` or `watcher`)
- `CLAUDE_MODEL` (`sonnet` or `opus`, Claude only)
- `LLM_BASE_URL` (optional; required for providers that do not have a built-in default)
- `TARGET_NAMESPACE`
- `TARGET_NAMESPACES` (comma-separated)
- `SRE_ALERT_CHANNEL` (enables scheduled scans)
- `SCAN_INTERVAL_SECONDS`
- `SQLITE_PATH` (default `/data/lucas.db`)
- `PROMPT_FILE` (default `/app/master-prompt-interactive.md`)
- OpenAI-compatible interactive mode is reduced-capability; it does not match Claude tool/resume behavior.

### CronJob agent

Required:

- `TARGET_NAMESPACE`
- `SRE_MODE` (`autonomous` or `report`)
- `LLM_BACKEND` (`claude-code` or `openai-compatible`)
- `LLM_PROVIDER` (`anthropic`, `groq`, `kimi`, `gemini`, `openrouter`)

If `LLM_BACKEND=claude-code`:

- `AUTH_MODE` (`api-key` or `credentials`)
- `ANTHROPIC_API_KEY` or `LLM_API_KEY`

If `AUTH_MODE=credentials`:

- Mount `credentials.json` at `/secrets/credentials.json` or `$HOME/.claude/.credentials.json`.

If `LLM_BACKEND=openai-compatible`:

- Set `LLM_MODEL`
- Set `LLM_API_KEY` or provider-specific env
- Set `LLM_BASE_URL` when the provider requires it
- Expect report-oriented behavior rather than full Claude-style tool parity
- Gemini Flash is supported as a development backend candidate via the official OpenAI-compatible endpoint.

Optional:

- `SLACK_WEBHOOK_URL` (Slack notifications)
- `SQLITE_PATH` (default `/data/lucas.db`)

### Dashboard

- `SQLITE_PATH` (default `/data/lucas.db`)
- `PORT` (default `8080`)
- `LOG_PATH` (default `/data/lucas.log`)
- `AUTH_USER` (default `a2wmin`)
- `AUTH_PASS` (default `a2wssword`)

## Deployment (interactive agent + dashboard)

1. Create sealed secrets for `llm-auth` and `slack-bot`.
2. Build and push images.
3. Apply the manifests.

Do not apply `k8s/secret.yaml` or `k8s/slack-bot-secret.yaml` in production. They are examples only.

Apply the manifests explicitly:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/pvc.yaml
kubectl apply -f k8s/rbac.yaml
kubectl apply -f k8s/agent-deployment.yaml
kubectl apply -f k8s/dashboard-deployment.yaml
kubectl apply -f k8s/dashboard-service.yaml
```

Port-forward the dashboard:

```bash
kubectl -n a2w-lucas port-forward svc/dashboard 8080:80
```

Open `http://localhost:8080`.

## CronJob mode

Use `k8s/cronjob.yaml`. It runs a batch scan on a schedule and writes to SQLite. It can notify Slack via webhook.

## Slack commands

- `@lucas check pods in namespace xyz`
- `@lucas why is pod abc crashing?`
- `@lucas show recent errors`
- `@lucas help`

## Dashboard

The dashboard shows recent runs, sessions, costs, and runbooks. Configure login with `AUTH_USER` and `AUTH_PASS`.

## Notes

- The helper script at `scripts/install.sh` can generate manifests and sealed secrets.
- `claude-sessions` PVC is only required for Claude resume support.
- OpenViking can provide memory or context support in supported environments, but Lucas must not assume OpenViking tools, long-term memory, or Claude-style resume are always available. When that support is absent, Lucas should rely only on the current prompt, explicit context, and live Kubernetes data.
- Docs live in `docs/` (VitePress).
