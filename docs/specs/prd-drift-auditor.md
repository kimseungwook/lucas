# PRD: Drift Auditor

## Summary

Lucas should add a drift-auditor capability for Kubernetes operations that detects high-risk operational drift, explains the likely root cause using deterministic evidence, and proposes exact remediation steps without making changes automatically.

The first release targets the drift types Lucas already encountered in live development and production rollouts:

- storage and node-placement drift
- stale ConfigMap-mounted code drift
- deployment-vs-cron runtime configuration drift

## Problem

Lucas can already detect unhealthy pods and summarize cluster issues, but several of the highest-value operational failures happen one layer earlier than normal incident reporting.

Examples from recent live rollout work:

- provider env changes looked correct while the cluster was still running old `llm.py` from ConfigMaps
- production workloads failed before Lucas started because PVC placement and node placement diverged
- interactive and cron runtime surfaces drifted apart even when they were meant to run the same provider/model

Today, operators must manually correlate PVCs, PVs, ConfigMaps, Deployment envs, CronJob envs, node labels, and startup logs to find the root cause. That is slow, error-prone, and hard to standardize.

## Goal

- Detect the most important Kubernetes operational drift types that affect Lucas runtime behavior.
- Explain the likely root cause using deterministic cluster evidence.
- Provide exact remediation guidance for operators.
- Keep the first release read-only and safe.
- Make the output useful in both scheduled reporting and interactive operator workflows.

## Non-Goals

- Automatically patch or restart workloads in the first release.
- Replace existing scheduled monitoring or Slack emergency actions.
- Become a full generic Kubernetes policy engine in the first release.
- Add dashboard redesign or schema migrations as part of this first drift-auditor slice.

## Users and stakeholders

- Platform operators running Lucas in dev and prod clusters
- SREs investigating rollout failures from Slack or reports
- Maintainers responsible for ConfigMaps, secrets, deployment manifests, and rollout safety

## User needs

### Platform operator

Needs Lucas to tell them when the live cluster no longer matches the intended runtime shape.

### SRE

Needs a short, evidence-based explanation of why a workload is unhealthy before deciding whether to restart, patch, or roll back.

### Maintainer

Needs a deterministic drift report that does not depend on model creativity to be correct.

## In scope

### Drift family 1: storage and placement drift

Detect at least these patterns:

- PVC selected-node history mismatches the node pool used by the workload
- PVC/PV attachment problems that prevent pod startup
- storage-related startup blockers such as volume attach errors and node-placement incompatibility

### Drift family 2: ConfigMap code drift

Detect at least these patterns:

- live mounted code does not contain provider support expected by the current repo or rollout intent
- interactive and cron code ConfigMaps are out of sync with each other
- provider-related runtime files differ across the mounted code surfaces

### Drift family 3: runtime configuration drift

Detect at least these patterns:

- Deployment and CronJob use different provider/model/base URL unintentionally
- secret refs and effective env values do not match the intended provider path
- runtime is configured for one provider while prompts/docs or rollout inputs imply another

## Out of scope

- Generic multi-cluster policy enforcement
- automatic ConfigMap refresh or nodeSelector mutation
- broad self-healing beyond reporting and guided remediation

## Functional requirements

### FR-1 Deterministic evidence

Drift conclusions must come from deterministic Kubernetes data and runtime files, not from LLM inference alone.

### FR-2 Read-only first release

The first release must not automatically mutate cluster state. It may only report, explain, and recommend.

### FR-3 Multi-surface comparison

The auditor must compare at least these surfaces:

- Deployment
- CronJob
- PVC/PV
- node labels and selected-node evidence
- ConfigMap-mounted runtime code
- secret/env references relevant to provider selection

### FR-4 Operator-focused output

For each detected drift, Lucas must emit:

- drift type
- impacted workload or resource
- evidence
- likely root cause
- remediation steps
- severity level

### FR-5 Safe wording

Lucas must clearly distinguish between:

- confirmed evidence
- likely cause
- recommended action

It must not present guesses as facts.

### FR-6 Scheduled compatibility

The drift auditor must fit into scheduled reporting as an additive section rather than replacing the existing cluster health report.

### FR-7 Interactive compatibility

The drift auditor must be callable from interactive operator flows without requiring unrestricted kubectl mutation rights.

## Output contract

Suggested result shape:

```json
{
  "status": "issues_found",
  "drift_summary": {
    "storage": 1,
    "code": 1,
    "runtime": 2
  },
  "drifts": [
    {
      "type": "storage.node_placement_mismatch",
      "severity": "high",
      "resource": "deployment/a2w-lucas-agent",
      "evidence": [
        "PVC selected-node=10.130.107.220",
        "Pod scheduled on 10.130.115.253",
        "AttachVolume error mentions non-paravirtualized attachment"
      ],
      "likely_cause": "The workload landed on a node pool that does not match the PVC-selected lineage for this OCI block volume.",
      "recommended_actions": [
        "Pin the workload to the validated node pool.",
        "Recreate the pod after updating node placement.",
        "Avoid changing provider config and storage placement in the same step."
      ]
    }
  ]
}
```

## Success metrics

- Operators can identify the likely cause of rollout drift without manual multi-object correlation.
- Lucas reports the three targeted drift families using deterministic evidence.
- Remediation guidance is specific enough to act on immediately.
- False certainty is avoided; evidence and hypothesis stay clearly separated.

## Acceptance criteria

- The design clearly defines the first-release drift families.
- The first-release output is read-only and remediation-oriented.
- Scheduled and interactive integration points are described.
- The spec does not promise auto-fix behavior in the first release.
- Docs build succeeds after adding the new spec files.

## Risks

- Overreaching into auto-remediation too early would increase blast radius.
- Weakly structured evidence could make the output noisy or non-actionable.
- Mixing rollout intent with actual live evidence could create false positives if not carefully defined.

## Follow-up directions

- Safe-case auto-remediation for narrow drift classes
- Rule externalization after the first deterministic implementation exists
- Dashboard surfacing for drift history and repeated drift patterns
