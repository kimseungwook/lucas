# CronJob Mode

CronJob mode runs a batch scan and writes a report to SQLite. It can also notify Slack via webhook.

## Manifest

Use `k8s/cronjob.yaml` and adjust:

- `schedule`
- `image`
- `TARGET_NAMESPACE`
- `SRE_MODE` (`autonomous` or `report`)
- `LLM_BACKEND` (`claude-code` or `openai-compatible`)
- `LLM_PROVIDER` (`anthropic`, `groq`, `kimi`, `gemini`)
- `SLACK_WEBHOOK_URL` (optional)

## Auth options

Claude compatibility:

- Set `LLM_BACKEND=claude-code`.
- Set `AUTH_MODE=api-key` or `credentials`.
- Provide `ANTHROPIC_API_KEY` or `LLM_API_KEY` in a secret.

Credentials file:

- Set `AUTH_MODE=credentials`.
- Mount `credentials.json` at `/secrets/credentials.json`.

OpenAI-compatible providers:

- Set `LLM_BACKEND=openai-compatible`.
- Set `LLM_PROVIDER=groq`, `LLM_PROVIDER=kimi`, or `LLM_PROVIDER=gemini`.
- Provide `LLM_API_KEY` and `LLM_MODEL`.
- Set `LLM_BASE_URL` when the provider requires an explicit endpoint.

## Storage

The CronJob writes to the same PVC (`lucas-data`). This lets the dashboard read its results.
