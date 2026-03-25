# Architecture

## Components

- **Agent (Slack)**: long-running service that answers Slack mentions and runs scheduled scans.
- **Agent (CronJob)**: batch worker that runs on a schedule and writes a report.
- **Dashboard**: web UI for runs, sessions, fixes, and token usage.
- **Postgres**: primary runtime store for runs, sessions, fixes, token usage, recovery actions, and run summaries.
- **SQLite**: compatibility path that may still exist during transition cleanup but is no longer the intended primary runtime store.
- **PVCs**: persistent storage for `lucas.db`, logs, and Claude sessions when resume support is enabled.
- **OpenViking (optional)**: environment-provided memory/context support when available.

## Data flow

1. A Slack mention or a scheduled scan triggers the agent.
2. The agent resolves the configured LLM backend and runs either Claude Code or an OpenAI-compatible provider (Groq, Kimi, Gemini, OpenRouter) with kubectl access.
3. Scheduled reporting can merge deterministic helpers such as pod incident triage into the final report payload.
4. Findings are written to Postgres in the current primary runtime path.
5. The dashboard reads the persisted runtime data.

## Scheduled scans

The interactive agent includes a scheduler. It scans namespaces from `TARGET_NAMESPACES` every `SCAN_INTERVAL_SECONDS` and posts results to `SRE_ALERT_CHANNEL`.

The current scheduled scan path can also merge bounded pod incident triage findings for namespaces/workloads selected through:

- `POD_INCIDENT_TARGET_NAMESPACES`
- `POD_INCIDENT_TARGET_WORKLOADS`

## Master prompts

Lucas behavior is driven by master prompt files included in the agent image. The selected prompt depends on mode:

- Interactive agent: `master-prompt-interactive.md` (autonomous) or `master-prompt-interactive-report.md` (watcher).
- CronJob: `master-prompt-autonomous.md` or `master-prompt-report.md`.

The prompt defines the rules of engagement, required output format, and runbook usage. Variables like `$TARGET_NAMESPACE`, `$SQLITE_PATH`, `$RUN_ID`, and `$LAST_RUN_TIME` are replaced at runtime.

## OpenViking context note

OpenViking can provide memory or context support in supported environments, but Lucas must not assume OpenViking tools, long-term memory, or Claude-style resume are always available. When that support is absent, Lucas should rely only on the current prompt, explicit context, and live Kubernetes data.
