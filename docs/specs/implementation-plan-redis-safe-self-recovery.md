# Redis Safe Self-Recovery Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe Redis self-recovery subsystem that can detect pod-local Redis failure, suppress itself during rollouts or infra-correlated incidents, and perform at most one automatic pod deletion when explicitly enabled.

**Architecture:** Implement a deterministic Redis recovery evaluator that combines Kubernetes pod signals, rollout suppression checks, infra-correlation checks, and a Redis serveability probe. Integrate its output into scheduled reporting first, then gate the single allowed mutating action (`delete pod`) behind an explicit feature flag and workload opt-in so the first live validation can happen safely in development.

**Tech Stack:** Python 3.12, `unittest`, kubectl-based runtime inspection/execution, existing Lucas scheduled reporting pipeline, existing Slack emergency-action safety model, VitePress docs.

---

## Scope Lock

This plan covers:

- deterministic Redis health classification
- rollout/update suppression
- infra-correlated suppression
- workload lock/cooldown
- scheduled reporting integration
- dev-only feature-flagged `delete pod` execution path for opted-in workloads

This plan does **not** cover:

- failover or replica promotion
- StatefulSet/Deployment restart automation
- scale changes, config mutation, or rollout undo
- Slack interactive mutation flow for Redis recovery
- production auto-remediation enablement

For this repository, **do not create git commits during execution unless the user explicitly asks for them.**

## File Structure

### New files

- `src/agent/main/redis_recovery.py` — Redis health classification, suppression, lock/cooldown checks, and recovery decision/action logic
- `tests/agent/test_redis_recovery.py` — unit tests for Redis classifier, suppression, and action decisions

### Modified files

- `src/agent/main/cron_runner.py` — invoke Redis recovery evaluation and optionally execute the shallow action when enabled
- `src/agent/main/report_utils.py` — preserve and format Redis recovery findings in scheduled reports
- `tests/agent/test_cron_runner.py` — scheduled-path integration coverage for Redis recovery fields
- `tests/agent/test_report_utils.py` — Slack formatting coverage for Redis recovery output
- `src/agent/main/sessions.py` — optional lightweight persistence for workload-scoped cooldown/last-action state if existing run store is insufficient
- `k8s/dev.env.template` — expose safe self-recovery feature flags and cooldown config
- `k8s/prod.env.template` — keep feature flags present but disabled by default
- `docs/ops/operations.md` — operator-facing note for Redis self-recovery v1 behavior
- `docs/specs/index.md` — include this implementation plan in the spec set

### Existing files to reference while implementing

- `src/agent/main/drift_auditor.py`
- `src/agent/main/cluster_snapshot.py`
- `src/agent/main/slack_actions.py`
- `docs/specs/prd-redis-safe-self-recovery.md`
- `docs/specs/trd-redis-safe-self-recovery.md`
- `docs/specs/status-first-reporting.md`

### Live validation assumptions

- Dev namespace: `a2w-lucas`
- Prod namespace: `lucas`
- Scheduled workload name: `a2w-lucas`
- Interactive workload name: `a2w-lucas-agent`

## Chunk 1: Redis Recovery Core (Read-only evaluation first)

### Task 1: Write failing unit tests for Redis recovery decisions

**Files:**
- Create: `tests/agent/test_redis_recovery.py`
- Reference: `docs/specs/prd-redis-safe-self-recovery.md`
- Reference: `docs/specs/trd-redis-safe-self-recovery.md`

- [ ] **Step 1: Add failing health-classification tests**

Add tests for at least:

```python
def test_classifies_not_serving_when_k8s_and_ping_both_fail():
    ...

def test_does_not_trigger_on_single_signal_only():
    ...
```

- [ ] **Step 2: Add failing rollout-suppression tests**

Add tests for at least:

```python
def test_suppresses_when_generation_exceeds_observed_generation():
    ...

def test_suppresses_when_updated_replicas_are_behind():
    ...
```

- [ ] **Step 3: Add failing infra-correlation tests**

Add tests for at least:

```python
def test_suppresses_when_multiple_redis_pods_fail_together():
    ...

def test_suppresses_when_storage_or_node_placement_failure_is_present():
    ...
```

- [ ] **Step 4: Add failing cooldown/lock tests**

Add tests for at least:

```python
def test_suppresses_when_recent_recovery_attempt_exists():
    ...

def test_allows_single_action_when_lock_and_cooldown_are_clear():
    ...
```

- [ ] **Step 5: Run the new test file and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_redis_recovery.py -v
```

Expected:
- FAIL because `redis_recovery.py` does not exist yet

### Task 2: Implement Redis recovery evaluator

**Files:**
- Create: `src/agent/main/redis_recovery.py`
- Test: `tests/agent/test_redis_recovery.py`

- [ ] **Step 1: Define stable result shapes**

Add typed dictionaries or equivalent structures for:

- Redis health classification
- suppression outcome
- recovery decision
- recovery report payload

- [ ] **Step 2: Implement the health classifier**

Implement a pure evaluator that combines:

- pod phase/readiness
- restart count
- recent events
- Redis ping or simple command probe result

It should classify:

- `healthy`
- `degraded_but_serving`
- `not_serving`
- `unknown`

- [ ] **Step 3: Implement suppression checks**

Implement pure helpers for:

- rollout/update suppression
- maintenance/suppression annotation
- infra-correlated suppression
- cooldown/lock suppression

- [ ] **Step 4: Implement final decision function**

Implement a top-level function such as:

```python
def build_redis_recovery_decision(...):
    ...
```

It should return:

- evidence
- likely cause
- suppressed or not
- action recommendation
- whether auto-delete is allowed

- [ ] **Step 5: Run the Redis recovery unit tests**

Run:

```bash
python3 -m unittest tests/agent/test_redis_recovery.py -v
```

Expected:
- PASS

## Chunk 2: Scheduled Reporting Integration

### Task 3: Add failing scheduled-path tests first

**Files:**
- Modify: `tests/agent/test_cron_runner.py`
- Modify: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Add failing cron integration test**

Add a test that proves scheduled reporting carries Redis recovery findings additively.

- [ ] **Step 2: Add failing Slack/report formatting test**

Add a test that proves Redis recovery sections appear in the report output without replacing the existing drift/pod summary sections.

- [ ] **Step 3: Run targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- FAIL because cron/report formatting does not yet know about Redis recovery fields

### Task 4: Integrate Redis recovery reporting into cron path

**Files:**
- Modify: `src/agent/main/cron_runner.py`
- Modify: `src/agent/main/report_utils.py`
- Test: `tests/agent/test_cron_runner.py`
- Test: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Add live input collection wrapper**

Add a thin runtime collection layer for:

- target Redis workload object(s)
- matching pod(s)
- recent events
- rollout status
- Redis serveability probe result

Keep the classifier pure; do not mix kubectl execution with the core decision logic.

- [ ] **Step 2: Add report payload fields additively**

Update stored report payloads to include Redis recovery fields without breaking compatibility.

Suggested fields:

- `redis_recovery_summary`
- `redis_recovery_findings`

- [ ] **Step 3: Add concise Slack formatting**

Update `format_slack_scan_message()` to render a small additive Redis recovery section only when findings exist.

- [ ] **Step 4: Re-run targeted cron/report tests**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

## Chunk 3: Feature-Flagged Auto-Delete Execution (Dev only)

### Task 5: Add failing execution-path tests

**Files:**
- Modify: `tests/agent/test_redis_recovery.py`
- Modify if needed: `tests/agent/test_cron_runner.py`

- [ ] **Step 1: Add failing auto-delete policy tests**

Add tests for at least:

```python
def test_auto_delete_requires_feature_flag_and_workload_opt_in():
    ...

def test_auto_delete_is_skipped_when_rollout_suppression_is_active():
    ...

def test_auto_delete_is_skipped_for_infra_correlated_failures():
    ...
```

- [ ] **Step 2: Add failing command-construction test**

Add a test that verifies the only automatic command is:

```bash
kubectl delete pod <name> -n <namespace>
```

- [ ] **Step 3: Run targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_redis_recovery.py tests/agent/test_cron_runner.py -v
```

Expected:
- FAIL because auto-delete execution path is not implemented yet

### Task 6: Implement the guarded auto-delete path

**Files:**
- Modify: `src/agent/main/redis_recovery.py`
- Modify: `src/agent/main/cron_runner.py`
- Modify if needed: `src/agent/main/sessions.py`
- Test: `tests/agent/test_redis_recovery.py`

- [ ] **Step 1: Add explicit feature flags/config**

Recommended env flags:

- `REDIS_SELF_HEAL_ENABLED=false`
- `REDIS_SELF_HEAL_NAMESPACES=` or annotation-based enablement
- `REDIS_SELF_HEAL_COOLDOWN_SECONDS=600`
- `REDIS_SELF_HEAL_MUTATIONS_ALLOWED=false`
- `REDIS_SELF_HEAL_ALLOWED_ENVIRONMENTS=dev`

The implementation must include a **hard guard** so pod deletion is impossible when:

- `REDIS_SELF_HEAL_MUTATIONS_ALLOWED != true`, or
- the runtime environment is not explicitly in the allowed environment list

The default production outcome must therefore be `report only`, even if other flags are mis-set.

- [ ] **Step 2: Add cooldown/lock persistence**

Use the existing SQLite/runtime persistence path to store workload-scoped last-action data if that is simpler than annotations for v1.

- [ ] **Step 2.5: Pin the minimum infra-suppression rule set**

Do not leave infra correlation as an abstract concept.

For v1, suppression must trigger when any of these are present:

- 2 or more pods in the same Redis workload are failing at once
- a pod event contains storage attach or node-placement failures
- a pod event contains common scheduling blockers such as `FailedScheduling`
- the workload has no clear single target pod in `not_serving` state

Add deterministic fixtures for these exact cases.

- [ ] **Step 3: Implement the single allowed action**

If and only if all gates pass, execute exactly one:

```bash
kubectl delete pod <pod-name> -n <namespace>
```

Also add tests that prove the command is **not constructed** when:

- prod guard is active
- rollout suppression is active
- infra suppression is active
- cooldown lock is active

- [ ] **Step 4: Re-run Redis recovery tests**

Run:

```bash
python3 -m unittest tests/agent/test_redis_recovery.py tests/agent/test_cron_runner.py -v
```

Expected:
- PASS

## Chunk 4: Docs and Final Verification

### Task 7: Document the runtime flags and operator expectations

**Files:**
- Modify: `docs/ops/operations.md`
- Modify: `docs/specs/index.md`
- Modify if needed: `k8s/dev.env.template`
- Modify if needed: `k8s/prod.env.template`

- [ ] **Step 1: Add runtime flag docs**

Document that:

- v1 is opt-in
- action ceiling is pod delete only
- rollout/infra suppression can skip recovery even if Redis looks bad

- [ ] **Step 2: Keep prod disabled by default**

Ensure the templates and docs make it clear that the first auto-delete enablement target is development only.

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

### Task 8: Final verification sweep

**Files:**
- Verify: `src/agent/main/redis_recovery.py`
- Verify: `src/agent/main/cron_runner.py`
- Verify: `src/agent/main/report_utils.py`
- Verify: `tests/agent/test_redis_recovery.py`
- Verify: `tests/agent/test_cron_runner.py`
- Verify: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Run all Redis-recovery-related tests together**

Run:

```bash
python3 -m unittest tests/agent/test_redis_recovery.py tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run Python syntax verification**

Run:

```bash
python3 -m py_compile src/agent/main/redis_recovery.py src/agent/main/cron_runner.py src/agent/main/report_utils.py
```

Expected:
- PASS

- [ ] **Step 3: Live dev smoke checklist**

Use an opted-in dev Redis workload only and verify all of the following with concrete commands and expected outputs.

**Discovery step: identify the dev smoke target first**

Run:

```bash
kubectl get statefulset,deployment -A \
  -o custom-columns='KIND:.kind,NS:.metadata.namespace,NAME:.metadata.name,RECOVERY:.metadata.annotations.lucas\.a2w/recovery-mode,IMAGE:.spec.template.spec.containers[0].image'
```

Pick one dev-only Redis workload with:

- namespace in a development cluster
- annotation `lucas.a2w/recovery-mode=redis-safe-restart`
- a known label selector for its pods

Set these variables for the remaining steps:

```bash
export REDIS_KIND=<statefulset|deployment>
export REDIS_NS=<namespace>
export REDIS_NAME=<workload-name>
export REDIS_LABEL='<label-selector>'
```

**Trigger Lucas scheduled evaluation**

After each scenario setup, trigger the Lucas scheduled evaluation explicitly with a one-off Job derived from the existing CronJob:

```bash
SMOKE_JOB=redis-recovery-smoke-$(date +%s)
kubectl -n a2w-lucas create job --from=cronjob/a2w-lucas ${SMOKE_JOB}
```

Observe the result in:

```bash
kubectl -n a2w-lucas logs job/${SMOKE_JOB}
kubectl exec -n a2w-lucas deploy/a2w-lucas-agent -- python3 -c "import sqlite3, json; conn=sqlite3.connect('/data/lucas.db'); cur=conn.cursor(); row=cur.execute('SELECT id, status, report FROM runs ORDER BY id DESC LIMIT 1').fetchone(); payload=json.loads(row[2]); print(json.dumps({'id': row[0], 'status': row[1], 'redis_recovery_summary': payload.get('redis_recovery_summary'), 'redis_recovery_findings': payload.get('redis_recovery_findings')}, ensure_ascii=True))"
```

Use the stored report payload or action audit record as the source of truth for whether deletion was attempted.

**Scenario A: rollout-in-progress -> skip**

Create an observable rollout state:

```bash
kubectl patch ${REDIS_KIND} ${REDIS_NAME} -n ${REDIS_NS} --type merge -p "{\"spec\":{\"template\":{\"metadata\":{\"annotations\":{\"lucas.a2w/smoke-rollout\":\"$(date +%s)\"}}}}}"
```

Suggested checks:

```bash
kubectl get ${REDIS_KIND} ${REDIS_NAME} -n ${REDIS_NS} -o jsonpath='{.metadata.generation} {.status.observedGeneration} {.status.updatedReplicas} {.spec.replicas}'
kubectl get pods -n ${REDIS_NS} -l ${REDIS_LABEL}
```

Expected result:

- Redis recovery report contains `suppressed=true`
- suppression reason references rollout/update state
- no `kubectl delete pod` action is executed
- verification command for no delete:

```bash
kubectl get events -n ${REDIS_NS} --sort-by=.lastTimestamp | grep -i "delete" || true
```

**Scenario B: infra-correlated failure -> skip**

Collect events and failing pods:

```bash
kubectl get pods -n ${REDIS_NS} -l ${REDIS_LABEL}
kubectl get events -n ${REDIS_NS} --sort-by=.lastTimestamp
```

Expected result:

- report contains infra-correlated suppression evidence
- no pod deletion occurs

**Scenario C: healthy -> no action**

Expected result:

- report shows no recovery action
- no suppression reason required

**Scenario D: clearly not-serving and stable -> one pod delete only**

Use a dedicated dev smoke workload only. Induce a pod-local non-serving condition on that workload with an explicit command such as:

```bash
REDIS_POD=$(kubectl get pods -n ${REDIS_NS} -l ${REDIS_LABEL} -o jsonpath='{.items[0].metadata.name}')
BEFORE_UID=$(kubectl get pod ${REDIS_POD} -n ${REDIS_NS} -o jsonpath='{.metadata.uid}')
kubectl exec -n ${REDIS_NS} ${REDIS_POD} -- sh -lc 'redis-cli shutdown nosave || pkill redis-server'
```

Then trigger Lucas scheduled evaluation and re-read the target pod UID.

Expected result:

- exactly one target pod delete is issued
- report includes `action=delete_pod` (or equivalent stored action field)
- no second pod is touched
- verification command for exactly one delete:

```bash
AFTER_UID=$(kubectl get pod ${REDIS_POD} -n ${REDIS_NS} -o jsonpath='{.metadata.uid}')
test "$BEFORE_UID" != "$AFTER_UID"
```

**Scenario E: repeated failure within cooldown -> skip and escalate**

Expected result:

- second evaluation during cooldown reports `suppressed=true`
- reason references cooldown/lock
- no second delete occurs

## Out-of-Scope Follow-Up

After this plan ships, the next follow-up plan should cover:

- interactive Slack approval flows for Redis recovery
- support for additional Redis deployment shapes
- production enablement plan
- dashboard surfacing for Redis recovery history

## Atomic Commit Strategy (only if the user explicitly asks for commits during execution)

- Commit 1: add `redis_recovery.py` and `tests/agent/test_redis_recovery.py`
- Commit 2: integrate Redis recovery reporting into `cron_runner.py` / `report_utils.py` and update tests
- Commit 3: add guarded auto-delete execution and persistence/cooldown plumbing
- Commit 4: docs/templates only
