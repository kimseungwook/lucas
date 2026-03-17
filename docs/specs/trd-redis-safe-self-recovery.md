# TRD: Redis Safe Self-Recovery

## Objective

Design a conservative Redis self-recovery subsystem for Lucas that can automatically delete a single unhealthy Redis pod only when the failure looks pod-local and the cluster does not appear to be in the middle of a rollout or broader infra incident.

The first release must be safe by default and bias uncertain cases to reporting only.

## Design principles

### Shallow action only

The first release performs one mutating action only:

- `kubectl delete pod <target>`

Everything deeper remains out of scope.

### Suppression before recovery

Rollout and infra checks are mandatory gates that decide whether auto-recovery is allowed at all.

### Evidence before mutation

The system must build a deterministic evidence record before it decides to act.

### Skip on ambiguity

If the system cannot distinguish pod-local failure from rollout or infra-wide instability, it must skip and report.

## Scope boundaries

### Supported workload shape in v1

The safest first release should treat Redis recovery as valid only for explicitly opted-in workloads that satisfy all of the following:

- Redis is reachable through a stable pod-local command check
- deleting one pod is an expected and reversible recovery action for that workload
- the workload is not currently under rollout/update suppression

If topology or ownership is unclear, the workload must fall back to report-only mode.

### Opt-in model

Recommended v1 enablement signal:

- workload annotation or label such as `lucas.a2w/recovery-mode=redis-safe-restart`

Optional suppression annotation:

- `lucas.a2w/recovery-disabled=true`

## High-level architecture

### 1. Redis recovery detector

New logical component that evaluates whether the target Redis workload is likely unhealthy.

Suggested file target:

- `src/agent/main/redis_recovery.py`

Possible helper split if needed:

- `src/agent/main/redis_health.py`
- `src/agent/main/recovery_guards.py`

### 2. Health classifier

Inputs should include:

- pod phase/readiness
- restart counts
- recent pod events
- Redis ping or equivalent simple command probe

The classifier should output one of:

- `healthy`
- `degraded_but_serving`
- `not_serving`
- `unknown`

Recommended v1 trigger rule:

- require at least two independent failure signals
- one of them must be a Redis serveability signal

Examples:

- `Ready=false` + `PING timeout`
- `Running with high restarts` + `PING failed`
- `CrashLoopBackOff` + command failure

### 3. Rollout/update suppression checker

Before any auto-recovery, evaluate the owning Deployment or StatefulSet.

Required gates:

- `metadata.generation > status.observedGeneration`
- `updatedReplicas < spec.replicas` when applicable
- recent rollout/restart events
- explicit maintenance or suppression annotation
- recent Lucas/operator action cooldown

If any gate is active, recovery is skipped.

### 4. Infra-correlated suppression checker

Detect situations where deleting one Redis pod is unlikely to help or may amplify churn.

Examples:

- multiple pods in the same workload failing together
- PVC attach failure or node-placement mismatch
- storage-related startup blockers
- node-level or cluster-wide event storm affecting multiple workloads

If infra correlation is detected, recovery is skipped.

### 5. Recovery lock and cooldown

Recommended v1 coordination mechanism:

- store a workload-scoped recovery record in existing Lucas SQLite state
- optionally mirror a lock/last-action timestamp in workload annotations later

Minimum lock fields:

- workload identity
- last attempt timestamp
- action type
- last result

Rules:

- one active recovery per workload
- cooldown window after action
- escalation if repeated failures continue after the cooldown

### 6. Recovery executor

If and only if:

- workload is opted in
- health classifier returns `not_serving`
- rollout/update suppression is clear
- infra-correlated suppression is clear
- no active lock/cooldown blocks the action

then Lucas may execute:

```bash
kubectl delete pod <pod-name> -n <namespace>
```

No other automated mutation is allowed in v1.

### 7. Reporting and audit trail

Every evaluation should produce a structured result, whether action is taken or skipped.

Suggested result shape:

```json
{
  "status": "issues_found",
  "recovery_candidate": true,
  "suppressed": true,
  "suppression_reason": "rollout_in_progress",
  "evidence": [
    "pod Ready=false",
    "Redis PING timeout",
    "deployment generation 9 > observedGeneration 8"
  ],
  "likely_cause": "Redis is unhealthy, but a rollout is still being processed.",
  "action": "skipped",
  "recommended_next_steps": [
    "Wait for rollout completion.",
    "Re-run health check after cooldown."
  ]
}
```

## Integration points

### Scheduled path first

The first implementation should plug into scheduled reporting, not immediate interactive action.

Suggested path:

- scheduled monitoring calls Redis recovery evaluator
- evaluator returns findings and action/skip outcome
- scheduled report includes Redis self-recovery section additively

### Interactive follow-up later

Interactive Slack support should be a later phase. It may reuse the same evidence and suppression logic, but it is not required in v1.

## Data sources

Minimum Kubernetes/runtime data sources:

- pod object
- owner workload object
- workload status (`generation`, `observedGeneration`, `updatedReplicas`)
- pod events
- drift auditor storage/node findings when relevant
- Redis command probe output

## Validation strategy

### Unit tests

Add deterministic tests for:

- healthy vs not-serving classification
- rollout suppression
- infra-correlated suppression
- lock/cooldown suppression
- single allowed action path
- skip reasons and reporting shape

### Live smoke tests

Recommended safe validation pattern:

- use a dev Redis workload only
- verify that unhealthy-but-rollout-in-progress produces `skip`
- verify that unhealthy-and-stable produces `delete pod`
- verify that multi-pod or infra-style symptoms produce `skip`

### Success criteria

The implementation is correct when:

- pod-local Redis failure leads to at most one automatic pod delete
- rollout/update state suppresses action
- infra-correlated state suppresses action
- reports clearly distinguish action taken vs action skipped

## Risks

- Redis ping may be necessary but not sufficient; some bad states still need a report-only outcome.
- If rollout detection is incomplete, auto-recovery can fight intended updates.
- If infra correlation is too weak, the system can create restart storms.

## Recommended rollout

### Phase 1

Read-only evaluation and reporting only.

### Phase 2

Enable automatic single-pod delete for opted-in workloads in dev.

### Phase 3

Promote to production only after repeated safe dev validation.
