# Status-First Reporting

## Summary

Lucas scheduled reporting should move from issue-first summaries to status-first reporting. The primary view should reflect actual Kubernetes pod states and reasons, while `issues` remains a derived and supporting metric.

## Problem

Current scheduled reporting compresses pod health into `issues` and a short summary. This loses important operational context such as `ImageInspectError`, `ContainerCreating`, `Error`, `PodInitializing`, `Completed`, and restart-heavy `Running` pods. It also allows weak model output to distort the final report.

## Goal

- Make pod status the primary reporting model.
- Preserve compatibility with current `pod_count`, `error_count`, `fix_count`, `status`, `summary`, and `details` fields.
- Keep Slack output concise and operator-friendly.
- Keep the persisted report contract additive and compact in this scope.

## Non-Goals

- Full dashboard redesign.
- Replacing all existing counters with a new schema immediately.
- Removing `issues` entirely.

## Current State

- Scheduled monitoring already supports `TARGET_NAMESPACES=all` and deterministic all-namespace aggregation in development.
- The current implementation already emits `status_breakdown`, `reason_breakdown`, and `top_problematic_pods` through the scheduled reporting path.
- The current implementation can also append `pod_incident_summary` and `pod_incident_findings` additively when bounded incident triage is enabled for the scanned namespace/workload scope.
- Dashboard and DB consumers still rely on the existing top-level compatibility fields.

## Proposed Reporting Model

### Primary fields

- `scope`
- `run_id`
- `total_pods`
- `pods_with_restarts`
- `status_breakdown`
- `reason_breakdown`
- `top_problematic_pods`
- `pod_incident_summary`
- `pod_incident_findings`
- `summary`

### Supporting fields

- `issues`
- `error_count`
- `fix_count`

## Status Classification Rules

Classification must use actual Kubernetes data from pod `phase`, container `reason`, and `restartCount`.

Track at least these buckets:

- `Running`
- `Completed`
- `Pending`
- `ContainerCreating`
- `PodInitializing`
- `ImageInspectError`
- `ErrImagePull`
- `CrashLoopBackOff`
- `Error`
- `Unknown`

### Problematic pod rule

A pod is considered problematic when:

- `phase != Running`, or
- `restartCount > 0`, or
- `reason` is not one of `Running` or `Succeeded`

## Report Payload

The stored `report` JSON should evolve toward this structure while preserving existing compatibility keys:

```json
{
  "scope": "all",
  "status": "issues_found",
  "pod_count": 313,
  "error_count": 107,
  "fix_count": 0,
  "pods_with_restarts": 27,
  "status_breakdown": {
    "Running": 206,
    "Pending": 21,
    "Failed": 5,
    "Completed": 18,
    "Unknown": 1
  },
  "reason_breakdown": {
    "ContainerCreating": 9,
    "PodInitializing": 4,
    "ImageInspectError": 3,
    "ErrImagePull": 2,
    "Error": 5,
    "CrashLoopBackOff": 7
  },
  "top_problematic_pods": [
    {
      "namespace": "ldap",
      "pod": "goyo-ldap-phpldapadmin-84b59df48c-mr4xv",
      "phase": "Pending",
      "reason": "ImageInspectError",
      "restarts": 0
    }
  ],
  "pod_incident_summary": {
    "findings": 1,
    "high": 1,
    "medium": 0,
    "evaluated_namespaces": 1
  },
  "pod_incident_findings": [
    {
      "type": "runtime.pod_incident",
      "namespace": "ldap",
      "severity": "high",
      "resource": "pod/goyo-ldap-phpldapadmin-84b59df48c-mr4xv",
      "category": "image_or_startup_failure",
      "likely_cause": "Image retrieval or startup artifact failure is preventing the workload from starting."
    }
  ],
  "summary": "주의가 필요한 파드가 107건 있습니다.",
  "details": [
    {
      "pod": "ldap/goyo-ldap-phpldapadmin-84b59df48c-mr4xv",
      "issue": "phase=Pending, reason=ImageInspectError, restarts=0"
    }
  ]
}
```

## Compatibility Rules

- Keep top-level `pod_count`, `error_count`, `fix_count`, `status`, `summary`, and `details`.
- `error_count` remains a derived metric from the status-first model.
- `details` becomes a compatibility projection of `top_problematic_pods`.
- Additional structured sections such as `pod_incident_summary` and `pod_incident_findings` must remain additive.
- Existing dashboard views must continue to work without schema migration.

## Slack Output Format

Recommended output shape:

```text
*Lucas status report*
scope=all run=113
total_pods=313 pods_with_restarts=27

status_breakdown
- Running: 206
- Pending: 21
- Failed: 5
- Completed: 18
- Unknown: 1

reason_breakdown
- ContainerCreating: 9
- PodInitializing: 4
- ImageInspectError: 3
- ErrImagePull: 2
- Error: 5
- CrashLoopBackOff: 7

top_problematic_pods
- ldap/goyo-ldap-phpldapadmin-84b59df48c-mr4xv: Pending / ImageInspectError / restarts=0
- dev-goyoai-web/dev-goyoai-web-back-v1-75dc787db7-67mvq: Pending / PodInitializing / restarts=0
- goyoai-web/goyoai-aify-scheduler-ffb684747-2rbcf: Running / Error / restarts=98

summary
주의가 필요한 파드가 107건 있습니다.

pod_incident_summary
- findings=1 high=1 medium=0 evaluated_namespaces=1

pod_incident_findings
- runtime.pod_incident @ ldap severity=high category=image_or_startup_failure: Image retrieval or startup artifact failure is preventing the workload from starting.
```

Formatting rules:

- Structural keys remain English.
- Human summary remains Korean.
- Show at most 3 to 5 problematic pods in Slack.
- Do not include shell transcripts.
- `status_breakdown` should represent real pod phase-level states.
- `reason_breakdown` should represent detailed waiting/terminated reasons that explain unhealthy non-running pods.
- Pod incident findings should stay compact and show at most 3 incident findings in Slack output.

## Deterministic Source of Truth

For scheduled scans:

- Status counts come from deterministic cluster inspection.
- The LLM may help with wording only.
- The LLM must not be the source of truth for pod state classification in all-namespace scans.

## Affected Components

- `src/agent/main/cluster_snapshot.py`
- `src/agent/main/report_utils.py`
- `src/agent/main/cron_runner.py`
- `src/agent/main/main.py` if scheduled callback formatting is kept aligned
- `src/agent/main/sessions.py`
- `src/dashboard/handlers/handlers.go`
- dashboard run detail and run list templates

## Acceptance Criteria

- If unhealthy pods exist, `status_breakdown` reflects them deterministically.
- `issues=0` must never be emitted when unhealthy pod states are present.
- Slack output leads with status breakdown rather than issue count.
- Existing dashboard counters still render.
- Additional incident sections remain additive and do not break existing consumers.
- Report payload remains within current storage limits.

## QA Plan

- unit tests for deterministic status aggregation
- unit tests for parser compatibility
- live `goyo-dev` run with known unhealthy pods
- verify SQLite row contents
- verify stored report payload contents in the current primary runtime store path
- verify Slack message shape
- verify dashboard still loads runs correctly

## Rollout Notes

- Introduce the new payload shape additively first.
- Keep compatibility fields for at least one release.
- Update Slack formatting before dashboard enhancements.
- Treat dashboard-specific visual improvements as a follow-up after the core data contract stabilizes.
