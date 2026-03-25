# Pod Death Without Source Access Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only Lucas incident-triage path for workloads whose pods suddenly die or repeatedly restart when the application source code is not available for modification.

**Architecture:** Reuse Lucas’s existing status-first reporting, drift-auditor evidence model, and runbook boundaries. Add a dedicated read-only pod-incident evidence collector and reporting shape that starts from phase/reason/restarts, gathers deterministic Kubernetes evidence, classifies incidents into a small set of operational hypothesis buckets, and recommends the shallowest reversible operator action.

**Tech Stack:** Python 3.12, `unittest`, Kubernetes/OKE, `kubectl`, existing Lucas reporting pipeline, existing runbooks, existing drift-auditor/report-utils patterns.

---

## Scope Lock

This plan covers:

- sudden pod death, restart churn, or CrashLoop-style incidents
- workloads where application source code cannot be changed in the short term
- read-only evidence collection from Kubernetes and OCI-runtime-adjacent signals
- status-first operator reporting and escalation guidance
- bounded stabilization guidance limited to the shallowest reversible actions

This plan does **not** cover:

- application source-code fixes
- speculative remediation without evidence
- broad automatic mutation across workloads
- permanent platform redesign in the first pass
- full node-level/runtime-process detection

For this repository, **do not create git commits during execution unless the user explicitly asks for them.**

## Acceptance Criteria

The work described by this plan is complete only when all of the following are true:

1. Lucas can produce a status-first incident snapshot for a failing pod/workload that includes phase, reason, restarts, owner, and top supporting evidence.
2. The incident output distinguishes at least these hypothesis buckets: pod-local transient failure, config/secret failure, image/startup failure, resource/probe failure, dependency failure, and infra/placement failure.
3. The output keeps `evidence`, `likely_cause`, and `recommended_actions` separate.
4. The path remains read-only by default and does not imply that a fix was applied when it was not.
5. Unit tests pass and manual QA shows the incident output on a realistic failing-pod scenario.

## File Structure

### New files

- `src/agent/main/pod_incident_triage.py` — deterministic incident evidence collection and hypothesis classification for no-source-access pod failures
- `tests/agent/test_pod_incident_triage.py` — unit tests for incident bucket classification, evidence preservation, and read-only behavior
- `src/agent/runbooks/pod-death-without-source-access.md` — operator-facing runbook for opaque workload failures

### Modified files

- `src/agent/main/cluster_snapshot.py` — reuse or expose status-first pod fields needed by the incident collector
- `src/agent/main/report_utils.py` — preserve and format incident findings if they are embedded into stored reports or Slack output
- `src/agent/main/cron_runner.py` — optionally append incident-triage fields additively to scheduled reporting for selected namespaces/workloads
- `src/agent/main/main.py` — interactive/report-only prompt wiring for incident diagnosis guidance
- `src/agent/entrypoint/master-prompt-report.md` — strengthen report-only pod incident workflow with previous-log and hypothesis-bucket guidance
- `src/agent/entrypoint/master-prompt-interactive.md` — align interactive diagnosis flow with the same evidence-first incident model
- `docs/ops/runbooks.md` — link the new runbook or mention the bounded incident path
- `tests/agent/test_report_utils.py` — formatting coverage if new incident fields are added to reports
- `tests/agent/test_cron_runner.py` — scheduled payload coverage if new incident fields are stored

### Existing files to reference while implementing

- `src/agent/main/cluster_snapshot.py`
- `src/agent/main/drift_auditor.py`
- `src/agent/main/redis_recovery.py`
- `src/agent/main/cron_runner.py`
- `src/agent/main/report_utils.py`
- `src/agent/main/main.py`
- `src/agent/entrypoint/master-prompt-report.md`
- `src/agent/entrypoint/master-prompt-interactive.md`
- `src/agent/runbooks/crashloopbackoff.md`
- `src/agent/runbooks/image-pull-backoff.md`
- `src/agent/runbooks/oom-killed.md`
- `docs/specs/status-first-reporting.md`
- `docs/specs/trd-drift-auditor.md`
- `docs/specs/prd-redis-safe-self-recovery.md`

## Design Rules

### Status first

The first output must start from real pod `phase`, `reason`, `restartCount`, and workload ownership.

### Evidence before interpretation

Every likely cause must be backed by at least two supporting evidence points when possible.

### Read-only first

The diagnosis path must not restart, patch, or mutate cluster state by default.

### Shallow action only

If an operator action is recommended before the cause is fully proven, it must be the shallowest reversible action, such as inspecting previous logs or deleting one isolated failing pod only under explicit gates.

### Skip on ambiguity

If rollout, storage, node, registry, or shared dependency correlation is visible, the path must prefer report-and-escalate over repeated restart churn.

## Output Contract

The new incident output should mirror repo patterns already used by drift and security reporting.

Suggested finding shape:

```python
class PodIncidentFinding(TypedDict):
    type: str
    severity: str
    resource: str
    evidence: list[str]
    likely_cause: str
    recommended_actions: list[str]
    category: str

class PodIncidentResult(TypedDict):
    status: str
    incident_summary: dict[str, int]
    incidents: list[PodIncidentFinding]
```

If these findings are embedded into scheduled reporting, they must do so additively and must not break the existing `status_breakdown`, `reason_breakdown`, and `top_problematic_pods` contract.

## Hypothesis Buckets

The classifier must place each incident into one primary category:

- `pod_local_transient_failure`
- `config_or_secret_failure`
- `image_or_startup_failure`
- `resource_or_probe_failure`
- `dependency_connectivity_failure`
- `infra_or_placement_failure`

Each category must be explainable from deterministic evidence.

## Chunk 1: Status-first incident snapshot

### Task 1: Add failing tests for the incident input contract

**Files:**
- Create: `tests/agent/test_pod_incident_triage.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_pod_incident_triage.py -v`
- Expected before implementation: FAIL because `pod_incident_triage.py` does not exist yet

- [ ] **Step 1: Write failing tests for base incident input extraction**

Add tests for at least:

```python
def test_collects_phase_reason_restart_and_owner_for_failing_pod():
    ...

def test_collects_previous_log_hint_when_restart_count_is_nonzero():
    ...
```

- [ ] **Step 2: Write failing blast-radius tests**

Add tests for at least:

```python
def test_marks_single_pod_failure_as_isolated_when_peers_are_healthy():
    ...

def test_marks_multi_workload_failure_as_non_isolated():
    ...
```

- [ ] **Step 3: Confirm the failure mode is explicit**

The failure output should clearly show the missing module or missing symbol, not a silent skip.

### Task 2: Implement the status-first incident collector

**Files:**
- Create: `src/agent/main/pod_incident_triage.py`
- Modify: `src/agent/main/cluster_snapshot.py`
- Test: `tests/agent/test_pod_incident_triage.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_pod_incident_triage.py -v`
- Expected after implementation: PASS

- [ ] **Step 1: Define stable incident input structures**

Include at minimum:

- pod identity
- owner identity
- phase/reason/restarts
- current and previous log availability markers
- rollout/deployment context
- node and PVC/placement clues when relevant

- [ ] **Step 2: Reuse status-first logic instead of inventing new severity semantics**

The collector should align with existing `cluster_snapshot.py` severity ordering and problematic-pod logic where possible.

- [ ] **Step 3: Keep collection read-only**

No mutation or restart logic belongs in this module.

## Chunk 2: Hypothesis classification and evidence separation

### Task 3: Add failing hypothesis-bucket tests

**Files:**
- Modify: `tests/agent/test_pod_incident_triage.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_pod_incident_triage.py -v`
- Expected before green step: FAIL on missing classifier behavior

- [ ] **Step 1: Write failing config/image/probe/dependency/infra bucket tests**

Add tests for at least:

```python
def test_classifies_createcontainerconfigerror_as_config_failure():
    ...

def test_classifies_imagepullbackoff_as_image_failure():
    ...

def test_classifies_oomkilled_as_resource_or_probe_failure():
    ...

def test_classifies_attach_failure_as_infra_or_placement_failure():
    ...
```

- [ ] **Step 2: Write failing evidence-boundary tests**

Add tests proving:

- `evidence` is preserved as factual observations
- `likely_cause` is separate from evidence
- `recommended_actions` does not claim a fix already happened

### Task 4: Implement deterministic hypothesis classification

**Files:**
- Modify: `src/agent/main/pod_incident_triage.py`
- Test: `tests/agent/test_pod_incident_triage.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_pod_incident_triage.py -v`
- Expected after implementation: PASS

- [ ] **Step 1: Implement the six hypothesis buckets**

Classification must be deterministic and evidence-backed.

- [ ] **Step 2: Require at least one hard signal and one supporting context signal when possible**

Examples:

- hard signal: `ImagePullBackOff`, `OOMKilled`, `CreateContainerConfigError`, attach failure event
- support signal: rollout context, peer health, dependency error log, probe configuration, selected-node mismatch

- [ ] **Step 3: Emit read-only operator actions**

Examples:

- inspect previous logs
- verify secret/config wiring
- verify image/tag/registry auth
- inspect PVC/node placement
- escalate to owner with evidence

## Chunk 3: Runbook and prompt operationalization

### Task 5: Add the operator runbook first

**Files:**
- Create: `src/agent/runbooks/pod-death-without-source-access.md`
- Modify: `docs/ops/runbooks.md`

**QA:**
- Read `src/agent/runbooks/pod-death-without-source-access.md`
- Expected: the runbook explicitly covers status-first triage, previous logs, bucket classification, shallow action gates, and escalation packaging

- [ ] **Step 1: Write the runbook around the same bucket model**

The runbook must not diverge from the classifier categories.

- [ ] **Step 2: Link the runbook from docs/ops**

Keep the operator entry path obvious.

### Task 6: Align prompt files with the same incident flow

**Files:**
- Modify: `src/agent/entrypoint/master-prompt-report.md`
- Modify: `src/agent/entrypoint/master-prompt-interactive.md`

**QA:**
- Read both prompt files after modification
- Expected: both prompts explicitly require current + previous logs for restarting pods, evidence-first diagnosis, and no false claim of applied fixes

- [ ] **Step 1: Strengthen the report-only workflow**

Require:

- status-first snapshot
- previous-log inspection when restarts exist
- hypothesis-bucket selection
- escalation when ambiguity remains

- [ ] **Step 2: Keep mutation boundaries explicit**

Interactive flow may suggest actions, but report-only flow must not imply they were run.

## Chunk 4: Scheduled report integration

### Task 7: Add failing report-path tests if incident findings will be persisted

**Files:**
- Modify: `tests/agent/test_report_utils.py`
- Modify: `tests/agent/test_cron_runner.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_report_utils.py tests/agent/test_cron_runner.py -v`
- Expected before green step: FAIL on missing incident fields or formatting

- [ ] **Step 1: Write failing payload-shape tests**

Add tests proving incident findings can be stored additively without breaking existing report consumers.

- [ ] **Step 2: Write failing formatting tests**

Add tests proving Slack/report output stays compact and evidence-first.

### Task 8: Wire the incident result into reporting carefully

**Files:**
- Modify: `src/agent/main/cron_runner.py`
- Modify: `src/agent/main/report_utils.py`
- Test: `tests/agent/test_report_utils.py`
- Test: `tests/agent/test_cron_runner.py`

**QA:**
- Run `python3 -m unittest tests/agent/test_report_utils.py tests/agent/test_cron_runner.py -v`
- Expected after implementation: PASS

- [ ] **Step 1: Keep the existing payload contract intact**

Do not break:

- `status_breakdown`
- `reason_breakdown`
- `top_problematic_pods`
- existing drift/security/redis sections

- [ ] **Step 2: Add the incident fields additively only if needed**

If the same problem can be represented with existing fields plus `summary/details`, prefer reuse over schema expansion.

- [ ] **Step 3: Keep Slack output bounded**

Maintain the current compact formatting pattern and avoid raw log dumps.

## Chunk 5: Manual QA and live validation

### Task 9: Prove the path on a realistic failing workload

**Files:**
- no new files required for manual QA

**QA:**
- Run the following evidence-gathering sequence against a non-production failing workload:

```bash
kubectl get pods -n <namespace> -o wide
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --tail=100 --timestamps
kubectl logs <pod-name> -n <namespace> --previous --tail=100 --timestamps
kubectl get deployment,statefulset,job,cronjob -n <namespace>
kubectl get events -n <namespace> --sort-by=.lastTimestamp
```

- Expected pass condition:
  - one primary hypothesis bucket can be assigned
  - at least two evidence points support it
  - the recommended action is shallow and reversible or escalation-only

- [ ] **Step 1: Validate isolated pod-local failure behavior**

Expected:

- one pod fails
- peers are healthy
- one shallow recycle recommendation is allowed only if no rollout/infra signal exists

- [ ] **Step 2: Validate non-isolated infra/config failure behavior**

Expected:

- repeated blind restart is rejected
- escalation path is recommended instead

## Atomic Commit Strategy

If the user later asks for commits, use this order:

1. **Commit 1:** add `pod_incident_triage.py` tests and implementation core
2. **Commit 2:** add runbook + prompt alignment
3. **Commit 3:** add optional report integration and formatting changes

Each commit must leave the repo in a working, testable state.

## Out-of-Scope Follow-Up

After this plan ships, follow-up work can cover:

- bounded automation for repeatable safe cases
- dependency-health enrichment
- OCI WAF/LB or Audit correlation when pod death is only one part of a larger incident
- longer-term policy for resource/probe tuning when code access is unavailable
