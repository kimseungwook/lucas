# Postgres Migration Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Lucas’s shared SQLite persistence with a dev-first Postgres-backed storage layer, validate it in shadow mode, and then cut over agent/cron/dashboard without preserving the shared live-log dependency.

**Architecture:** Introduce a single Postgres schema that replaces all current SQLite-backed state (`runs`, `fixes`, `token_usage`, `slack_sessions`, `recovery_actions`, `run_summaries`). First build a Postgres storage layer in parallel with the existing SQLite path for dev validation, then switch dashboard and runtime components to Postgres as the only report-state backend and remove the dashboard’s dependency on shared `/data/lucas.db` and `/data/lucas.log`.

**Tech Stack:** Python 3.12, Go 1.22, PostgreSQL, Kubernetes, `unittest`, dashboard DB abstraction layer, VitePress docs.

---

## Scope Lock

This plan covers:

- dev-only Postgres deployment and service
- Postgres schema creation for all current logical persistence tables
- Python runtime storage abstraction swap
- Go dashboard DB abstraction swap
- dev shadow validation and dev cutover
- dashboard live-log dependency removal/reduction in v1

This plan does **not** cover:

- SQLite data import
- production rollout
- Postgres HA
- external log backend introduction in v1

For this repository, **do not create git commits during execution unless the user explicitly asks for them.**

## File Structure

### New files

- `src/agent/main/postgres_store.py` — Postgres-backed replacement for the Python runtime persistence surface
- `tests/agent/test_postgres_store.py` — unit/integration tests for Postgres-backed persistence behavior
- `src/dashboard/db/postgres.go` — Postgres-backed dashboard data access layer
- `k8s/postgres.yaml` — dev-first Postgres deployment/service/PVC manifest

### Modified files

- `src/agent/main/sessions.py` — either become a storage interface boundary or delegate to the new Postgres store
- `src/agent/main/cron_runner.py` — runtime storage initialization and optional shadow-write plumbing
- `src/agent/main/main.py` — interactive session storage initialization path
- `src/dashboard/main.go` — DB backend initialization switch from SQLite to Postgres
- `src/dashboard/handlers/handlers.go` — keep handler contract stable while swapping DB backend
- `k8s/agent-deployment.yaml` — Postgres env wiring and removal of SQLite dependence for report DB access
- `k8s/cronjob.yaml` — Postgres env wiring and removal of SQLite dependence for report DB access
- `k8s/dashboard-deployment.yaml` — Postgres env wiring and removal/reduction of live log file dependency
- `k8s/pvc.yaml` — shrink or de-scope shared report DB usage if appropriate after cutover
- `README.md` — operator-facing deployment and config changes
- `docs/ops/operations.md` — update dashboard/log/storage behavior notes
- `docs/specs/index.md` — include this implementation plan in the spec set

### Existing files to reference while implementing

- `src/agent/main/sessions.py`
- `src/dashboard/db/sqlite.go`
- `src/dashboard/handlers/handlers.go`
- `k8s/agent-deployment.yaml`
- `k8s/cronjob.yaml`
- `k8s/dashboard-deployment.yaml`
- `docs/specs/prd-postgres-migration.md`
- `docs/specs/trd-postgres-migration.md`

## Test Harness and Driver Decisions

### Python driver

Use:

- `asyncpg`

Reason:

- the current `RunStore` / `SessionStore` interface is async
- this minimizes churn in `cron_runner.py`, interactive session persistence, and recovery-state writes

### Go driver

Use:

- `github.com/jackc/pgx/v5/stdlib`

Reason:

- it preserves a `database/sql` style integration while letting the dashboard stay structurally close to the current SQLite implementation

### Required dependency updates

Python:

- modify `src/agent/main/requirements.txt` to add `asyncpg`

Go:

- modify `src/dashboard/go.mod` to add `pgx/v5`

### Dev Postgres test harness

The plan assumes a dev Postgres instance deployed from `k8s/postgres.yaml`.

Required dev secret contract:

- Secret name: `lucas-postgres-auth`
- Required keys:
  - `username`
  - `password`
  - `database`

Create the secret before applying the Postgres workload:

```bash
kubectl -n a2w-lucas create secret generic lucas-postgres-auth \
  --from-literal=username=lucas \
  --from-literal=password=<dev-password> \
  --from-literal=database=lucas \
  --dry-run=client -o yaml | kubectl apply -f -
```

Bring up the harness with:

```bash
kubectl -n a2w-lucas create secret generic lucas-postgres-auth \
  --from-literal=username=lucas \
  --from-literal=password=<dev-password> \
  --from-literal=database=lucas \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n a2w-lucas apply -f k8s/postgres.yaml
kubectl -n a2w-lucas rollout status deployment/lucas-postgres --timeout=300s
kubectl -n a2w-lucas port-forward svc/lucas-postgres 5432:5432
```

Use these envs while the port-forward is active:

```bash
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=lucas
export POSTGRES_USER=lucas
export POSTGRES_PASSWORD=<dev-password>
export POSTGRES_SSLMODE=disable
```

The same env block must be exported before running Go DB tests.

## Chunk 1: Postgres Schema and Python Store

### Task 1: Write failing Python store tests first

**Files:**
- Create: `tests/agent/test_postgres_store.py`

- [ ] **Step 1: Write failing schema tests**

Add tests that assert the Postgres store initializes logical equivalents of:

- `runs`
- `fixes`
- `token_usage`
- `slack_sessions`
- `recovery_actions`
- `run_summaries`

- [ ] **Step 2: Write failing CRUD tests**

Add tests for at least:

```python
def test_create_and_update_run_in_postgres():
    ...

def test_store_and_read_session_mapping_in_postgres():
    ...

def test_store_run_summaries_in_postgres():
    ...
```

- [ ] **Step 3: Run the new test file and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_postgres_store.py -v
```

Expected:
- FAIL because `postgres_store.py` does not exist yet

- [ ] **Step 4: Prepare the Postgres harness before the green step**

Run:

```bash
kubectl -n a2w-lucas apply -f k8s/postgres.yaml
kubectl -n a2w-lucas rollout status deployment/lucas-postgres --timeout=300s
kubectl -n a2w-lucas port-forward svc/lucas-postgres 5432:5432
pip install -r src/agent/main/requirements.txt
```

Expected:

- Postgres is reachable from the local test runner
- Python dependencies install successfully

### Task 2: Implement the Python Postgres store

**Files:**
- Create: `src/agent/main/postgres_store.py`
- Modify: `src/agent/main/sessions.py`
- Test: `tests/agent/test_postgres_store.py`

- [ ] **Step 1: Define the Postgres connection config contract**

Recommended envs:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_SSLMODE`

- [ ] **Step 1.5: Add `asyncpg` dependency**

Modify:

- `src/agent/main/requirements.txt`

Run:

```bash
pip install -r src/agent/main/requirements.txt
```

Expected:

- `asyncpg` is importable in tests and runtime code

- [ ] **Step 1.5: Add `asyncpg` dependency**

Modify:

- `src/agent/main/requirements.txt`

Run:

```bash
pip install -r src/agent/main/requirements.txt
```

Expected:

- `asyncpg` is importable for tests and runtime code

- [ ] **Step 2: Implement schema initialization**

Implement schema creation for the six logical table families.

- [ ] **Step 3: Implement CRUD-compatible store methods**

Match the current runtime needs for:

- create/update run
- record fix
- record token usage
- record/get recovery action
- session save/get/delete
- run summary replacement

- [ ] **Step 4: Keep runtime call sites stable where practical**

Either:

- wrap the new Postgres store behind the existing `RunStore` / `SessionStore` interface shape, or
- add an explicit storage backend selector with minimal call-site churn

- [ ] **Step 5: Run the Postgres store tests**

Run:

```bash
python3 -m unittest tests/agent/test_postgres_store.py -v
```

Expected:
- PASS

## Chunk 2: Dashboard DB Layer

### Task 3: Add failing dashboard DB tests first

**Files:**
- Create: `src/dashboard/db/postgres_test.go`

- [ ] **Step 1: Add failing query tests**

Cover at least:

- namespace list retrieval
- run list retrieval
- run detail retrieval
- run summary retrieval

- [ ] **Step 2: Run the Go test and confirm failure**

Run:

```bash
go test ./src/dashboard/db/...
```

Expected:
- FAIL because `postgres.go` does not exist yet

- [ ] **Step 3: Add the Go Postgres driver dependency before the green step**

Modify:

- `src/dashboard/go.mod`

Run:

```bash
cd src/dashboard
go mod tidy
```

Expected:

- `pgx/v5` resolves cleanly

- [ ] **Step 3: Add the Go Postgres driver dependency before the green step**

Modify:

- `src/dashboard/go.mod`

Run:

```bash
cd src/dashboard
go mod tidy
```

Expected:

- `pgx/v5` resolves cleanly

### Task 4: Implement the dashboard Postgres DB layer

**Files:**
- Create: `src/dashboard/db/postgres.go`
- Modify: `src/dashboard/main.go`
- Modify if needed: `src/dashboard/handlers/handlers.go`
- Test: `src/dashboard/db/postgres_test.go`

- [ ] **Step 1: Implement Postgres-backed equivalents for current SQLite queries**

Match the current dashboard query contract for:

- `GetRuns`
- `GetRun`
- `GetNamespaces`
- `GetNamespaceStats`
- `GetFixesByRun`
- `GetSessions`
- `GetTokenUsage`
- `GetCostStats`

- [ ] **Step 2: Switch `main.go` to Postgres configuration**

Do not leave the dashboard hardwired to `SQLITE_PATH` after cutover.

Also make the dashboard use:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_SSLMODE`

Also make the dashboard use:

- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `POSTGRES_SSLMODE`

- [ ] **Step 3: Keep handler/template contracts stable**

Minimize changes outside the DB layer so the UI behavior stays focused on the storage migration only.

- [ ] **Step 4: Run dashboard DB tests**

Run:

```bash
export POSTGRES_HOST=127.0.0.1
export POSTGRES_PORT=5432
export POSTGRES_DB=lucas
export POSTGRES_USER=lucas
export POSTGRES_PASSWORD=<dev-password>
export POSTGRES_SSLMODE=disable
go test ./src/dashboard/db/...
```

Expected:
- PASS

If the envs are absent, tests should fail fast with a clear message rather than silently using SQLite.

## Chunk 3: Dev Postgres Deployment and Shadow Validation

### Task 5: Add Postgres deployment assets

**Files:**
- Create: `k8s/postgres.yaml`
- Modify: `k8s/agent-deployment.yaml`
- Modify: `k8s/cronjob.yaml`
- Modify: `k8s/dashboard-deployment.yaml`

- [ ] **Step 1: Define dev Postgres Kubernetes resources**

Include:

- Deployment or StatefulSet
- Service
- dedicated PVC
- auth secret references

- [ ] **Step 2: Add env wiring for all three runtime surfaces**

- agent
- cron
- dashboard

- [ ] **Step 3: Keep SQLite path intact only during shadow validation**

The shadow step may temporarily dual-write or compare behavior, but the design must still lead to single-source Postgres after cutover.

### Task 6: Shadow validation in dev

**Files:**
- Modify: `src/agent/main/cron_runner.py`
- Modify: `src/agent/main/main.py`
- Modify: `src/dashboard/main.go`

- [ ] **Step 1: Add a temporary shadow validation switch**

Recommended:

- explicit env like `POSTGRES_SHADOW_VALIDATE=true`

Use it only in dev.

- [ ] **Step 2: Validate write/read behavior in dev**

Expected checks:

- agent writes to Postgres
- cron writes to Postgres
- dashboard reads from Postgres
- existing SQLite path is no longer needed for successful report retrieval during the validation window

Run concrete checks:

```bash
kubectl -n a2w-lucas get pods
kubectl -n a2w-lucas logs deploy/a2w-lucas-agent --tail=80
kubectl -n a2w-lucas logs job/<latest-lucas-job> --tail=120
kubectl -n a2w-lucas port-forward svc/lucas-postgres 5432:5432
psql "host=127.0.0.1 port=5432 dbname=lucas user=lucas password=<dev-password> sslmode=disable" -c '\dt'
psql "host=127.0.0.1 port=5432 dbname=lucas user=lucas password=<dev-password> sslmode=disable" -c 'select count(*) from runs;'
```

Expected:

- required tables exist
- fresh rows appear in `runs`
- dashboard query layer can read those rows

## Chunk 4: Dev Cutover and Dashboard Log Scope Reduction

### Task 7: Remove report DB dependence on shared SQLite paths

**Files:**
- Modify: `src/dashboard/handlers/handlers.go`
- Modify: `src/dashboard/main.go`
- Modify: `docs/ops/operations.md`
- Modify: `README.md`

- [ ] **Step 1: Reduce or remove the live log viewer**

For v1, the dashboard should either:

- remove the live log view entirely, or
- show only persisted run log content from the database

Do not keep `/data/lucas.log` as a hard dependency for dashboard viability.

For v1, make this explicit:

- remove `logPath` / `readLog()` dependence from `src/dashboard/handlers/handlers.go`
- remove `LOG_PATH` usage from `src/dashboard/main.go` if it is only used for the live viewer
- remove `LOG_PATH` from `k8s/dashboard-deployment.yaml`
- remove `/data` volume mount from `k8s/dashboard-deployment.yaml`
- remove dashboard dependence on `lucas-data` in `k8s/dashboard-deployment.yaml`

If any log view remains, it must render persisted run log content from Postgres rather than reading `/data/lucas.log`.

- [ ] **Step 2: Cut over dev to Postgres-only report storage**

Success condition:

- dashboard report retrieval no longer depends on `/data/lucas.db`

- [ ] **Step 3: Validate dashboard restart safety**

Expected:

- dashboard can restart without the old shared SQLite PVC bottleneck

Run concrete checks:

```bash
kubectl -n a2w-lucas rollout restart deployment/dashboard
kubectl -n a2w-lucas rollout status deployment/dashboard --timeout=300s
kubectl -n a2w-lucas get deployment dashboard -o yaml | grep -E 'LOG_PATH|lucas-data' || true
kubectl -n a2w-lucas port-forward svc/dashboard 8080:80
curl -I http://127.0.0.1:8080/health
```

Expected:

- rollout succeeds
- dashboard no longer references `LOG_PATH` or `lucas-data`
- health endpoint returns `200`

## Chunk 5: Final Docs and Verification

### Task 8: Final docs and template alignment

**Files:**
- Modify: `README.md`
- Modify: `docs/ops/operations.md`
- Modify: `docs/specs/index.md`

- [ ] **Step 1: Update operator docs for Postgres envs and dashboard behavior**

- [ ] **Step 2: Explicitly document fresh-start and no-import v1 policy**

- [ ] **Step 3: Build docs**

Run:

```bash
npm run build
```

from:

```bash
cd docs
```

Expected:
- PASS

### Task 9: Final verification sweep

**Files:**
- Verify Python storage files
- Verify Go dashboard DB files
- Verify K8s manifests

- [ ] **Step 1: Run Python tests**

Run:

```bash
python3 -m unittest tests/agent/test_postgres_store.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run Go tests**

Run:

```bash
go test ./src/dashboard/db/...
```

Expected:
- PASS

- [ ] **Step 2.5: Validate dashboard DB behavior explicitly**

Run:

```bash
go test ./src/dashboard/db/...
kubectl -n a2w-lucas port-forward svc/dashboard 8080:80
curl -s http://127.0.0.1:8080/api/namespaces
curl -s "http://127.0.0.1:8080/api/runs?ns=all"
```

Expected:

- dashboard endpoints return Postgres-backed data

- [ ] **Step 3: Run Python syntax verification**

Run:

```bash
python3 -m py_compile src/agent/main/postgres_store.py src/agent/main/cron_runner.py src/agent/main/main.py
```

Expected:
- PASS

- [ ] **Step 4: Live dev verification checklist**

Verify all of the following in `goyo-dev`:

- Postgres pod/service healthy
- agent writes runs/fixes/tokens to Postgres
- dashboard reads run list and details from Postgres
- namespace summary rows still work
- dashboard restart no longer depends on the shared SQLite DB file

## Out-of-Scope Follow-Up

After this plan ships, the next follow-up plan should cover:

- production rollout
- optional SQLite import tooling if historical data becomes important
- external log backend for a richer dashboard log view

## Atomic Commit Strategy (only if the user explicitly asks for commits during execution)

- Commit 1: add Postgres Python store and tests
- Commit 2: add dashboard Postgres DB layer and tests
- Commit 3: add dev Postgres deployment and shadow validation plumbing
- Commit 4: cut over dashboard/runtime and reduce live log dependency
- Commit 5: docs only
