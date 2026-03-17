# PRD: Redis Safe Self-Recovery

## Summary

Lucas should add a Redis safe self-recovery capability that can automatically recover a Redis workload when it is truly not serving traffic, while explicitly avoiding interference with legitimate rolling updates, operator-driven changes, and infra-correlated incidents.

The first release is intentionally narrow:

- automatic action is limited to **pod deletion only**
- health judgment uses **Kubernetes signals + Redis ping/command health**
- rollout/update suppression is mandatory
- ambiguous or infra-wide incidents are **report-only**

## Problem

Redis can fail in two ways that matter operationally:

1. it is obviously unhealthy (`Pending`, `CrashLoopBackOff`, repeated restarts)
2. it appears `Running`, but it is not actually serving traffic or answering Redis commands

In practice, deleting the bad pod is often enough to restore service. However, the same symptom can also appear during a legitimate Redis rollout, a planned restart, or an infra-level problem such as storage, node, or control-plane instability.

If Lucas blindly deletes Redis pods during those periods, it can create churn, interfere with updates, or amplify the incident.

## Goal

- Detect when a Redis workload is likely not serving traffic.
- Automatically perform the shallowest safe recovery action when conditions are safe.
- Suppress recovery during rollouts, maintenance, and infra-correlated incidents.
- Produce an evidence-based report that explains why Lucas acted or why it intentionally skipped action.

## Non-Goals

- Automatic Redis failover
- Replica promotion
- Topology change or cluster reshaping
- Config mutation
- Scale up/down
- Rollout undo
- General self-healing for all stateful services in the first release

## Users and stakeholders

- Platform operators responsible for Redis-backed services
- SREs monitoring cluster health and scheduled reports
- Maintainers who need safe default automation without hidden destructive behavior

## User needs

### Platform operator

Needs Lucas to recover obvious Redis pod-local failures without waiting for manual intervention, while never fighting planned updates.

### SRE

Needs clear evidence for why Lucas acted or refused to act.

### Maintainer

Needs a design that keeps the blast radius small and is safe for production by default.

## Scope

### In scope

- Redis workloads explicitly opted into safe self-recovery
- Kubernetes-based health signals
- Redis ping or equivalent simple serveability check
- rollout-aware suppression
- cooldown and lock-based deduplication
- one automatic action: delete exactly one target pod
- evidence/likely-cause/action-or-skip reporting

### Out of scope

- automatic StatefulSet restart
- automatic Deployment restart
- multi-pod or infra-wide recovery actions
- any topology-changing Redis action

## Functional requirements

### FR-1 Opt-in only

Redis self-recovery must be enabled only for explicitly opted-in workloads. The first release must not silently act on every Redis-like workload in the cluster.

### FR-2 Two-part health gate

Lucas must require both:

1. a target Redis workload that appears unhealthy
2. a surrounding system state that looks stable enough for pod deletion to be a meaningful test

If the second condition is unclear, Lucas must skip auto-recovery.

### FR-3 Multi-signal failure detection

Lucas must not trigger auto-recovery from a single signal.

At minimum, the health classifier must combine:

- Kubernetes runtime state (phase/readiness/restarts/events)
- Redis serveability signal (`PING` or equivalent simple command)

### FR-4 Rollout-aware suppression

Lucas must suppress auto-recovery when a legitimate update or recent operator action is likely in progress.

Required suppression inputs:

- `metadata.generation > status.observedGeneration`
- `updatedReplicas < spec.replicas` when applicable
- recent rollout or restart events within a cooldown window
- explicit maintenance or suppression annotation

### FR-5 Infra-correlated suppression

Lucas must not auto-delete Redis pods when symptoms look infra-correlated rather than pod-local.

Examples:

- multiple pods in the same workload failing together
- storage attach or node-placement failure
- broad node/network/control-plane instability

### FR-6 Shallow action only

When auto-recovery is allowed, Lucas may only delete one target pod.

It must not:

- restart the entire workload
- mutate Redis config
- scale the workload
- trigger failover

### FR-7 Lock and cooldown

Lucas must prevent duplicate recovery attempts against the same workload within a bounded window.

### FR-8 Action transparency

Lucas must report:

- evidence
- likely cause
- action taken or skipped reason
- recommended next step when automatic recovery is skipped or fails

## Success metrics

- Pod-local Redis failures can be recovered automatically without operator intervention.
- Rollout/update collisions are prevented by suppression gates.
- Infra-wide incidents do not trigger repeated destructive churn.
- Operators can understand from reports why Lucas acted or did not act.

## Acceptance criteria

- The first release limits automatic action to deleting a single pod.
- The first release requires Kubernetes + Redis serveability signals.
- The first release suppresses action during rollout/update and infra-correlated conditions.
- The first release reports evidence and action/skip reasoning.
- The spec does not promise failover or topology mutation.

## Risks

- False positives from weak health signals can still cause unnecessary restarts.
- Infra-correlated failures can look like Redis failures unless suppression is strict.
- Operators may over-trust automation if evidence and skip reasons are not clear enough.

## Recommended defaults

- default automatic action: `delete pod`
- default Redis health signals: Kubernetes state + Redis ping
- default policy for ambiguous cases: **skip and report**
- default posture for rollouts/maintenance: **suppressed**

## Follow-up directions

- Interactive Slack confirmation path for deeper recovery actions
- Safe-case restart policy for more than one Redis deployment shape
- Redis-specific dashboards and trend visibility
