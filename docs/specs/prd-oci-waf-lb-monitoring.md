# PRD: OCI WAF/LB Monitoring

## Summary

Lucas should add a read-only OCI edge-monitoring capability for Web Application Firewall (WAF) and Load Balancer (LB) resources.

The first release should query bounded WAF/LB signals through OCI SDK/API calls, reduce them into evidence-first findings, and surface those findings through the existing Lucas scheduled reporting path every 15 minutes.

This feature is intentionally narrow. It is an entrypoint-monitoring control, not a full DDoS platform, not a ransomware detector, and not a replacement for deeper cloud logging, SIEM, or backend application telemetry.

## Problem

The organization needs a defensible first monitoring layer for externally exposed entrypoints.

In the current environment:

- OCI WAF and LB are the primary edge controls for exposed application traffic.
- Lucas already provides scheduled operational reporting, but it lacks OCI edge visibility.
- Full raw log ingestion is expensive in both volume and sensitivity.
- The team wants a practical first release that can be specified and reviewed before wider signal expansion.

If the design overclaims what WAF/LB monitoring can detect, the control becomes weak from both operational and audit perspectives. If the design waits for every downstream log source before starting, the platform remains blind to useful edge/entrypoint signals.

## Goal

- Provide a read-only, SDK/API-based monitoring capability for OCI WAF and LB resources.
- Use deterministic OCI signals as the basis for findings.
- Deliver those findings through the existing Lucas scheduled reporting pipeline on a 15-minute cadence.
- Keep retained evidence small, auditable, and low-sensitivity.
- Reuse the existing Lucas finding/report contract rather than inventing a new top-level payload shape.

## Non-Goals

- Full raw request-log ingestion in Phase 1.
- Retaining full headers, full query strings, or other sensitive request payload data.
- Claiming advanced DDoS attribution or ransomware detection from WAF/LB alone.
- Automated blocking, policy mutation, or OCI resource changes in Phase 1.
- Monitoring OCI Flow logs, OCI Audit logs, or FE/BE application logs in Phase 1.
- Replacing SIEM, SOC, or long-term forensics workflows.

## Users and stakeholders

- Security engineers who need bounded edge/entrypoint visibility.
- SREs responsible for availability and safe rollout of WAF/LB-backed services.
- Compliance owners who need an implemented, reviewable monitoring control.

## User needs

### Security engineer

Needs actionable WAF/LB findings without reading large volumes of raw OCI log rows.

### SRE

Needs a stable 15-minute signal on edge health and suspicious patterns that fits into the current Lucas report workflow.

### Compliance owner

Needs a control story that is accurate, bounded, and explicit about what is monitored versus deferred.

## Scope

### In scope

- OCI SDK/API-based collection of bounded WAF/LB signals.
- 15-minute scheduled reporting.
- Read-only monitoring of WAF decisions, WAF trigger patterns, LB health, listener compatibility, and LB fault/latency/error patterns.
- Aggregated evidence-first findings mapped into `security_suspicion_summary` and `security_suspicion_findings`.
- Compact Slack/report rendering through the existing Lucas output model.

### Out of scope

- OCI Flow and Audit integration in Phase 1.
- FE/BE application-log ingestion in Phase 1.
- Real-time alerting or sub-minute polling.
- Full request forensics.
- Automated policy changes or containment.

## Functional requirements

### FR-1 OCI SDK/API collection

Lucas must use OCI SDK/API calls to collect WAF and LB signals.

Phase 1 may query bounded log/metric/health data through OCI APIs, but it must not persist raw request rows as the reporting contract.

### FR-2 Scheduled cadence

The feature must run as part of the existing scheduled reporting cycle with a 15-minute default window.

### FR-3 Minimal evidence retention

Findings must preserve only the minimum evidence required for operator triage.

Phase 1 must not store or report:

- full HTTP headers
- full query strings
- raw request bodies
- long unbounded raw log excerpts

### FR-4 Existing finding contract reuse

The feature must reuse the existing Lucas reporting contract.

Required output shape:

- `security_suspicion_summary` with `findings`, `high`, `medium`, `evaluated_namespaces`
- `security_suspicion_findings` with `type`, `namespace`, `severity`, `resource`, `evidence`, `likely_scenario`, `impact_scope`, `recommended_actions`, and `category`

If OCI findings do not map to a real Kubernetes namespace, the implementation must still preserve payload compatibility through a stable synthetic reporting scope rather than inventing a separate top-level schema.

### FR-5 Compact operator output

Slack/report output must stay concise and evidence-first.

Phase 1 should show:

- a compact summary
- top findings only
- short evidence items rather than raw rows

### FR-6 Accurate wording

The feature must be described as read-only OCI edge monitoring.

It must not imply:

- full request forensics
- backend application visibility
- comprehensive DDoS mitigation
- ransomware detection from edge signals alone

## Prerequisites and assumptions

- **WAF listener compatibility**: WAF requires the relevant listener path to use HTTP/HTTPS rather than TCP. Listener conversion is a platform prerequisite, not a Lucas responsibility.
- **OCI access**: Lucas must have read-only OCI access to the target WAF/LB resources and supporting API surfaces needed for bounded signal retrieval.
- **Resource scoping**: Phase 1 can start with explicit OCI resource IDs and compartment scope before host/listener/path coverage is fully finalized.

## Success metrics

- Scheduled Lucas reports include bounded OCI WAF/LB findings.
- Reports run on the 15-minute cadence without materially bloating report size.
- Findings remain evidence-first and low-sensitivity.
- Operators can distinguish likely edge abuse, edge health degradation, and obvious configuration mismatch from the report alone.

## Acceptance criteria

- PRD, TRD, and implementation plan are internally consistent.
- `docs/specs/index.md` includes the new spec set.
- Phase 1 is explicitly limited to read-only OCI WAF/LB monitoring.
- The design preserves the existing Lucas finding/report contract.
- Missing operational inputs are captured as open items rather than silently guessed.

## Risks

- WAF/LB signals may be too coarse for root-cause certainty without later enrichment.
- Missing OCI IAM permissions may block collection.
- If listeners remain on TCP, WAF-based monitoring will be incomplete or misleading.
- If raw-field scope is not tightly bounded, token cost and sensitive-data exposure will rise quickly.

## Open items / deferred

- exact target hosts, listeners, backend sets, and paths
- high-severity thresholds for WAF/LB patterns
- production WAF policy mode assumptions (log-only, partial enforcement, stronger enforcement)
- Phase 2 correlation with OCI Flow/Audit
- later BE application-log enrichment for deeper incident explanation

## Recommended rollout

### Phase 1

Read-only OCI WAF/LB monitoring with bounded evidence, scheduled every 15 minutes.

### Phase 2

Add cross-correlation and selective OCI Flow/Audit enrichment.

### Phase 3

Add stronger triage workflows and more precise severity logic based on production operating data.
