# TRD: OCI WAF/LB Monitoring

## Objective

Design a read-only OCI edge-monitoring subsystem for WAF and Load Balancer resources that can feed deterministic, compact findings into the current Lucas scheduled reporting path every 15 minutes.

The design must preserve the existing Lucas `security_suspicion_summary` / `security_suspicion_findings` contract while staying strict about two boundaries:

- Phase 1 is WAF/LB only.
- Phase 1 aggregates evidence; it does not persist raw request data as the report contract.

## Design principles

### Deterministic first

AI does not generate the source signal. OCI APIs and bounded query results provide the source signal.

### Read-only first

Phase 1 may inspect OCI state, logs, health, and metrics through read-only APIs only.

### Aggregate before reporting

The collector may read multiple OCI rows or datapoints, but the classifier must emit compact findings rather than raw records.

### Minimal evidence retention

Evidence must stay small, low-sensitivity, and operator-usable.

### Contract compatibility

The subsystem must fit the current Lucas reporting model additively instead of introducing a separate OCI-only top-level report schema.

## Target architecture

### New logical subsystem

Suggested file targets:

- `src/agent/main/oci_waf_lb_signal_collection.py`
- `src/agent/main/oci_waf_lb_compensating_control.py`
- `src/agent/main/oci_utils.py`

The system should separate:

- OCI signal collection
- deterministic aggregation and severity assignment
- reuse of the existing Lucas scheduled report formatting path

## Data sources

The first release should collect from OCI SDK/API surfaces that can support bounded 15-minute analysis windows.

### WAF sources

- WAF policy state and configuration
- bounded WAF log retrieval or log-search results queried through OCI APIs
- WAF-side rule, rate-limit, access-control, and action outcomes when exposed by the OCI API surface in use

### Load Balancer sources

- LB listener configuration
- LB health and backend-set health
- LB access/error log results queried through OCI APIs in bounded windows
- LB fault, timeout, latency, and HTTP status metrics where available through OCI APIs

## Static scope control

Recommended Phase 1 config:

- `OCI_MONITOR_ENABLED=true`
- `OCI_COMPARTMENT_ID=ocid1.compartment.oc1..example`
- `OCI_WAF_POLICY_IDS=...`
- `OCI_LB_IDS=...`
- `OCI_MONITOR_WINDOW_MINUTES=15`

The collector must inspect only explicitly configured resources or the configured compartment scope.

## Phase 1 input fields

The goal is not to store every available field. The goal is to keep only the fields that materially improve finding quality.

### Essential WAF fields

- `timestamp`
- `action`
- `logType`
- `clientAddr` or aggregated source identity
- normalized request path / URL path only
- request method
- request correlation key such as request ID or incident key when present
- response code
- backend status code when present
- matched rule IDs / matched rules / rate-limit or protection detections
- `responseProvider`

### Essential LB fields

- `timestamp`
- listener name
- host
- client address / forwarded address when present
- normalized request line or path target
- LB status code
- backend status code
- request processing time
- backend connect time
- backend processing time
- backend address
- `responseProvider`
- request ID when present
- error `type` and `errorDetails` for LB error logs

### Optional enrichment, not Phase 1 required

- country
- bytes sent/received
- full user-agent strings
- TLS protocol/cipher details
- full forwarded chain
- raw headers
- full query strings

## Aggregation and retention rules

Phase 1 must reduce OCI signals before they enter the Lucas finding payload.

Required rules:

- query only bounded windows aligned to the scheduled run
- normalize paths before evidence generation
- deduplicate repeated events
- emit 2 to 4 short evidence items per finding
- preserve only the smallest set of fields needed for triage
- do not persist raw headers, raw bodies, or full query strings in the report payload

One finding should summarize repeated WAF/LB events rather than embedding raw rows.

## Output model

The subsystem must reuse the current `security_suspicion_*` shape.

Because OCI edge findings do not belong to a real Kubernetes namespace, Phase 1 should preserve compatibility through a stable synthetic reporting scope such as `oci-edge`.

### Summary shape

```json
{
  "security_suspicion_summary": {
    "findings": 2,
    "high": 1,
    "medium": 1,
    "evaluated_namespaces": 1
  }
}
```

### Finding shape

```json
{
  "security_suspicion_findings": [
    {
      "type": "security.suspicious_behavior",
      "namespace": "oci-edge",
      "severity": "high",
      "resource": "LoadBalancer/app-main listener/443",
      "evidence": [
        "WAF block surge on normalized path /api/login within 15 minutes",
        "LB backend timeouts increased for the same listener window",
        "WAF response provider indicates edge-side enforcement activity"
      ],
      "likely_scenario": "Possible L7 entrypoint abuse affecting an authenticated endpoint.",
      "impact_scope": "edge/entrypoint with possible downstream backend risk",
      "recommended_actions": [
        "Review the bounded WAF/LB evidence window in OCI.",
        "Confirm listener and WAF policy configuration for the affected entrypoint.",
        "Escalate for deeper backend or cloud-log investigation if impact persists."
      ],
      "category": "suspicious_edge_abuse"
    }
  ]
}
```

## AI role

Lucas/AI may:

- correlate multiple deterministic OCI signals into one operator-facing finding
- explain likely scenarios in bounded human language
- rank severity and suggest next actions

Lucas/AI must not:

- invent raw request details that were not collected
- act as the source of truth for OCI resource state
- make automated enforcement decisions in Phase 1

## Integration points

### Scheduled reporting

The subsystem should integrate into the existing `cron_runner.py` scheduled path.

### Report payload

Phase 1 should reuse:

- `security_suspicion_summary`
- `security_suspicion_findings`

No separate OCI-specific top-level payload contract is required in Phase 1.

### Slack output

Phase 1 should rely on the existing compact security finding rendering rules:

- summary first
- top findings only
- short lines only

## Classification model

The first release should classify into a small fixed set:

- `suspicious_edge_abuse`
- `edge_health_degradation`
- `edge_config_mismatch`

Examples:

- repeated WAF rule/rate-limit hits concentrated on a path
- LB 5xx or backend timeout surge on the same listener window
- WAF-enabled entrypoint still using TCP listener shape

## Validation strategy

### Unit tests

- mocked OCI collector responses for WAF and LB
- aggregation tests for dedupe and evidence compaction
- schema tests proving payload compatibility with current `security_suspicion_*` fields
- tests proving forbidden sensitive fields are excluded from findings

### Live validation

- dev-only WAF/LB resources with read-only access
- bounded synthetic trigger generation for WAF/LB
- verification that stored/report payloads remain compact and schema-compatible

## Risks

- OCI API/log surfaces may return signals later than the 15-minute report window expects.
- WAF/LB-only signals may be too coarse for precise incident explanation.
- Synthetic namespace compatibility can become awkward if external-resource monitoring expands significantly.
- If operators need full request forensics immediately, Phase 1 will feel intentionally small.

## Open items

- exact OCI API surfaces to standardize on for bounded WAF/LB retrieval
- production resource inventory and host/listener mapping
- high-severity thresholds by listener, host, or path
- WAF policy mode assumptions for severity interpretation

## Recommended rollout

### Phase 1

Read-only bounded OCI WAF/LB monitoring on a 15-minute schedule.

### Phase 2

Selective correlation with OCI Flow/Audit and stronger severity logic.

### Phase 3

Expanded triage and richer operator workflows once production signal quality is known.
