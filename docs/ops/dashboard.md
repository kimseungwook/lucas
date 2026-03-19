# Dashboard

The dashboard is a simple Go app that now targets Postgres-backed report state.

## Login

Set credentials with:

- `AUTH_USER`
- `AUTH_PASS`

Defaults are `a2wmin` / `a2wssword`.

## Pages

- **Overview**: recent runs and latest run details.
- **Sessions**: Slack sessions stored in the runtime database.
- **Costs**: token usage and cost totals.
- **Runbooks**: static runbook summaries.

## Current recovery deployment

- The dashboard should run from a dedicated image: `gdhb.goyoai.com/lukas/lucas-dashboard:postgres`.
- The deployment uses the `harbor-creds` image pull secret.
- It does not mount the shared `lucas-data` PVC.
- It reads report state from Postgres instead of a shared SQLite file.

## Storage

- The intended steady state is Postgres as the dashboard data source.
- The dashboard should not depend on shared SQLite report storage after cutover.
- The old live log tail path from `LOG_PATH` is no longer the primary dashboard data path.
