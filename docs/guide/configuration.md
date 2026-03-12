# Configuration

## Agent (interactive Slack)

Required:

- `SLACK_BOT_TOKEN`
- `SLACK_APP_TOKEN`

LLM:

- `LLM_BACKEND`: `claude-code` or `openai-compatible`.
- `LLM_PROVIDER`: `anthropic`, `groq`, `kimi`.
- `LLM_API_KEY`: provider API key.
- `LLM_MODEL`: required for openai-compatible providers.
- `LLM_BASE_URL`: optional for Groq, required when the provider does not have a built-in default.

Legacy Claude compatibility:

- `ANTHROPIC_API_KEY`

Common:

- `SRE_MODE`: `autonomous` or `watcher`.
- `CLAUDE_MODEL`: `sonnet` or `opus` for Claude only.
- `TARGET_NAMESPACE`: default namespace for interactive requests.
- `TARGET_NAMESPACES`: comma-separated list for scheduled scans.
- `SRE_ALERT_CHANNEL`: channel ID for scheduled scan alerts.
- `SCAN_INTERVAL_SECONDS`: seconds between scheduled scans.
- `SQLITE_PATH`: defaults to `/data/lucas.db`.
- `PROMPT_FILE`: defaults to `/app/master-prompt-interactive.md`.

Notes:

- If `SRE_ALERT_CHANNEL` is empty, scheduled scans are disabled.
- `SRE_MODE=watcher` uses the report-only prompt.
- `LLM_BACKEND=openai-compatible` in interactive mode is reduced-capability today; it does not have Claude-style tool and resume parity.

## Agent (CronJob mode)

Required:

- `TARGET_NAMESPACE`
- `SRE_MODE`: `autonomous` or `report`.
- `LLM_BACKEND`: `claude-code` or `openai-compatible`.
- `LLM_PROVIDER`: `anthropic`, `groq`, `kimi`.

If `LLM_BACKEND=claude-code`:

- `AUTH_MODE`: `api-key` or `credentials`.

- `ANTHROPIC_API_KEY` or `LLM_API_KEY`

If `AUTH_MODE=credentials`:

- Mount `credentials.json` at `/secrets/credentials.json` or `$HOME/.claude/.credentials.json`.

If `LLM_BACKEND=openai-compatible`:

- `LLM_MODEL`
- `LLM_API_KEY`
- `LLM_BASE_URL` for providers that need an explicit endpoint
- Non-Claude CronJob mode is report-oriented and uses a Kubernetes snapshot instead of Claude tool execution.

Optional:

- `SLACK_WEBHOOK_URL`: enables Slack notifications.
- `SQLITE_PATH`: defaults to `/data/lucas.db`.

## Dashboard

- `SQLITE_PATH`: defaults to `/data/lucas.db`.
- `PORT`: defaults to `8080`.
- `LOG_PATH`: defaults to `/data/lucas.log`.
- `AUTH_USER`: defaults to `a2wmin`.
- `AUTH_PASS`: defaults to `a2wssword`.
