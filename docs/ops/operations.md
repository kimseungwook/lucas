# Operations

## Scheduled scans

The interactive agent can scan multiple namespaces on a timer.

Set:

- `TARGET_NAMESPACES` (comma-separated)
- `SCAN_INTERVAL_SECONDS`
- `SRE_ALERT_CHANNEL`
- `POD_INCIDENT_TARGET_NAMESPACES` (optional, comma-separated override for pod incident triage)
- `POD_INCIDENT_TARGET_WORKLOADS` (optional, comma-separated `<kind>/<name>` list such as `deployment/api`)

If `SRE_ALERT_CHANNEL` is empty, scheduled scans are disabled.

Scheduled scan output can now include bounded pod-incident triage findings when the namespace/workload scope matches the configured pod-incident target settings.

## Storage and data

- Development and production now both use Postgres as the primary runtime store for new runs.
- The target state is Postgres as the single source of truth for runs, fixes, token usage, slack sessions, recovery actions, and run summaries.
- `SQLITE_PATH` may still remain present as a compatibility path during transition cleanup, but it is no longer the intended primary runtime store.

## Postgres migration direction

- The target storage model is Postgres as the single source of truth for report/runtime state.
- Agent, cron, and dashboard should all use the same Postgres service.
- The dashboard should not require the shared `lucas-data` PVC after cutover.
- The live log viewer should be removed or reduced to persisted run log content in the first Postgres release.

## Dashboard image deployment

- The dashboard deployment should use a dedicated image instead of building the binary inside the pod.
- The current deployment target is `gdhb.goyoai.com/lukas/lucas-dashboard:postgres` with the `harbor-creds` pull secret.
- The dashboard no longer mounts the shared `lucas-data` PVC.
- The dashboard no longer relies on the old live log file path as its primary data path.
- This deployment path exists because the older runtime hit both a `ReadWriteOnce` PVC attach conflict and `ghcr.io/a2wio/lucas-dashboard:latest` image pull failures.

## Postgres cutover checklist

- This checklist has now been executed for both dev and prod and remains here as the rollback/audit reference for future re-runs.
- Confirm `lucas-postgres` is healthy and the `lucas-postgres-auth` secret contains `username`, `password`, and `database`.
- Confirm the dedicated dashboard image is built and pushed before rollout.
- Confirm the dashboard is healthy without the shared `lucas-data` PVC and that `/health` responds on the dashboard service.
- Confirm recent scheduled runs are being written to Postgres and match the expected namespace/status values.
- Confirm the agent and cron manifests both point at `lucas-postgres` with the intended `POSTGRES_*` env values.
- If shadow validation is still enabled in the live cluster, disable `POSTGRES_SHADOW_VALIDATE` for the cutover rollout and restart the workloads in this order: dashboard, agent, cron.
- After the restart, confirm new runs continue to appear in Postgres and that the dashboard reads current data without falling back to shared SQLite state.
- Keep the previous manifest revision available until at least one full scheduled scan cycle completes cleanly after cutover.
- If cutover fails, roll back the workload manifests to the previous revision and restore the prior runtime path before retrying.

Reference:

- `README.md`
- `docs/specs/index.md`

## Logs

- CronJob runs write to `/data/lucas.log`.
- The dashboard live file viewer is planned to be removed or reduced during the Postgres cutover so it no longer depends on shared `/data` storage.
- The agent logs are available via `kubectl logs`.

## Pod incident triage

- This path is read-only and evidence-first.
- It is intended for pods that die or restart when direct application source remediation is not available.
- The current implementation groups incidents into bounded buckets:
  - config/secret failure
  - image/startup failure
  - resource/probe failure
  - dependency/connectivity failure
  - infra/placement failure
  - pod-local transient failure
- The goal is to produce a better first operator message, not to auto-fix every opaque workload failure.
- If the evidence points to config, image, dependency, or infra causes, operators should prefer escalation over repeated restart churn.

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
