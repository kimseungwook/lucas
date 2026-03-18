# Operations

## Scheduled scans

The interactive agent can scan multiple namespaces on a timer.

Set:

- `TARGET_NAMESPACES` (comma-separated)
- `SCAN_INTERVAL_SECONDS`
- `SRE_ALERT_CHANNEL`

If `SRE_ALERT_CHANNEL` is empty, scheduled scans are disabled.

## Storage and data

- Current production/dev runtime still uses SQLite until the Postgres cutover is executed.
- The target state is Postgres as the single source of truth for runs, fixes, token usage, slack sessions, recovery actions, and run summaries.
- Shadow validation may temporarily keep `SQLITE_PATH` present while Postgres is validated in parallel.

## Postgres migration direction

- The target storage model is Postgres as the single source of truth for report/runtime state.
- Agent, cron, and dashboard should all use the same Postgres service.
- The dashboard should not require the shared `lucas-data` PVC after cutover.
- The live log viewer should be removed or reduced to persisted run log content in the first Postgres release.

## Logs

- CronJob runs write to `/data/lucas.log`.
- The dashboard live file viewer is planned to be removed or reduced during the Postgres cutover so it no longer depends on shared `/data` storage.
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

## Virtual-node compensating malware control

- The first release is report-only.
- The feature is disabled by default.
- Only namespaces listed in `SECURITY_MONITOR_NAMESPACES` are inspected.
- This control is a virtual-node compensating control, not a kernel-level runtime detector.
- Lucas/AI summarizes deterministic signals and recommends actions; it does not act as the detector itself.
