# Operations

## Scheduled scans

The interactive agent can scan multiple namespaces on a timer.

Set:

- `TARGET_NAMESPACES` (comma-separated)
- `SCAN_INTERVAL_SECONDS`
- `SRE_ALERT_CHANNEL`

If `SRE_ALERT_CHANNEL` is empty, scheduled scans are disabled.

## Storage and data

- SQLite lives at `SQLITE_PATH` (default `/data/lucas.db`).
- The CronJob and dashboard share the same PVC (`lucas-data`).
- Slack sessions are stored in SQLite and cleaned after 7 days.

## Logs

- CronJob runs write to `/data/lucas.log`.
- The dashboard reads from `LOG_PATH`.
- The agent logs are available via `kubectl logs`.

## Drift auditor

- The first drift-auditor release is read-only.
- It reports evidence, likely cause, and remediation steps.
- The first release targets storage/node-placement drift, runtime surface drift, and deployment-vs-cron runtime configuration drift.

## Redis safe self-recovery

- The first Redis self-recovery release is opt-in.
- Automatic action is limited to deleting a single Redis pod.
- Redis self-recovery uses Kubernetes signals plus a Redis serveability probe.
- Rollout/update suppression and infra-correlated suppression can skip recovery even when Redis looks bad.
- Production should keep Redis self-heal mutation flags disabled until dev validation is complete.
