# OCI WAF/LB Monitoring Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only OCI WAF/LB monitoring feature to Lucas that runs on the 15-minute scheduled reporting path, produces compact evidence-first findings, and preserves the existing `security_suspicion_*` report contract.

**Architecture:** Implement a bounded OCI signal collector plus a deterministic classifier for WAF/LB evidence, then merge the resulting findings into the current Lucas scheduled report shape. Keep Phase 1 report-only, SDK/API-based, and intentionally small in retained evidence.

**Tech Stack:** Python 3.12, `unittest`, OCI Python SDK, existing Lucas scheduled reporting pipeline, VitePress docs.

---

## Scope Lock

This plan covers **Phase 1 only** from the OCI WAF/LB monitoring specs:

- explicit feature enable/disable
- bounded OCI SDK/API collection for WAF/LB signals
- 15-minute scheduled reporting integration
- minimal evidence retention
- reuse of existing `security_suspicion_summary` and `security_suspicion_findings`

This plan does **not** implement:

- OCI Flow, OCI Audit, or application-log ingestion
- automated blocking or OCI resource mutation
- real-time alerting
- full request forensics
- new OCI-specific top-level report schemas

For this repository, **do not create git commits during execution unless the user explicitly asks for them.**

## File Structure

### New files

- `src/agent/main/oci_waf_lb_signal_collection.py` — bounded OCI WAF/LB signal collection
- `src/agent/main/oci_waf_lb_compensating_control.py` — deterministic aggregation and finding generation
- `src/agent/main/oci_utils.py` — OCI client initialization and shared helpers
- `tests/agent/test_oci_waf_lb_signal_collection.py` — unit tests for OCI collection and feature gates
- `tests/agent/test_oci_waf_lb_compensating_control.py` — unit tests for classification, aggregation, and schema compatibility

### Modified files

- `src/agent/main/cron_runner.py` — call OCI collection path and merge findings into scheduled reporting
- `src/agent/main/report_utils.py` — ensure existing compact security-finding output works for OCI edge findings
- `tests/agent/test_cron_runner.py` — scheduled payload coverage for OCI-derived findings
- `tests/agent/test_report_utils.py` — formatting coverage for OCI-derived `security_suspicion_*` content
- `k8s/dev.env.template` — add OCI monitor flags
- `k8s/prod.env.template` — add OCI monitor flags, disabled by default
- `docs/ops/current-runtime-settings.md` — document runtime config defaults
- `docs/ops/operations.md` — operator-facing note for OCI edge monitoring scope and boundaries
- `docs/specs/index.md` — include this implementation plan in the spec set

### Existing files to reference while implementing

- `src/agent/main/security_signal_collection.py`
- `src/agent/main/security_compensating_control.py`
- `src/agent/main/cron_runner.py`
- `src/agent/main/report_utils.py`
- `docs/specs/prd-oci-waf-lb-monitoring.md`
- `docs/specs/trd-oci-waf-lb-monitoring.md`
- `docs/specs/status-first-reporting.md`

## Chunk 1: OCI Signal Collection Core

### Task 1: Add failing unit tests for bounded OCI collection

**Files:**
- Create: `tests/agent/test_oci_waf_lb_signal_collection.py`

- [ ] **Step 1: Write failing feature-gate tests**

Add tests for at least:

```python
def test_returns_empty_when_oci_monitor_disabled():
    ...

def test_returns_empty_when_no_target_resources_are_configured():
    ...
```

- [ ] **Step 2: Write failing collection-shape tests**

Add tests for at least:

```python
def test_collects_bounded_waf_signal_rows_without_raw_sensitive_fields():
    ...

def test_collects_lb_health_and_listener_state_for_target_resources():
    ...
```

- [ ] **Step 3: Run the new collection test file and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_oci_waf_lb_signal_collection.py -v
```

Expected:
- FAIL because the OCI collection module does not exist yet

### Task 2: Implement the OCI signal collector

**Files:**
- Create: `src/agent/main/oci_utils.py`
- Create: `src/agent/main/oci_waf_lb_signal_collection.py`
- Test: `tests/agent/test_oci_waf_lb_signal_collection.py`

- [ ] **Step 1: Implement OCI client helpers**

Create the minimal client/bootstrap helpers needed for:

- WAF-related API access
- Load Balancer API access
- Logging/Monitoring access needed for bounded Phase 1 queries

- [ ] **Step 2: Implement bounded collection rules**

Collector rules:

- inspect only configured OCI resources or compartment scope
- use a 15-minute bounded window by default
- normalize request targets/paths before they reach the classifier
- exclude forbidden raw sensitive fields from collector output

- [ ] **Step 3: Define stable collected-signal shapes**

The collected bundle should preserve enough data for deterministic aggregation, including:

- WAF signal rows or aggregates
- LB health/listener state
- LB bounded access/error evidence
- collection scope metadata

- [ ] **Step 4: Run collection tests**

Run:

```bash
python3 -m unittest tests/agent/test_oci_waf_lb_signal_collection.py -v
```

Expected:
- PASS

## Chunk 2: OCI Finding Generation

### Task 3: Add failing aggregation/classification tests

**Files:**
- Create: `tests/agent/test_oci_waf_lb_compensating_control.py`

- [ ] **Step 1: Write failing finding-shape tests**

Add tests for at least:

```python
def test_output_matches_existing_security_suspicion_finding_shape():
    ...

def test_uses_stable_synthetic_scope_for_oci_findings():
    ...
```

- [ ] **Step 2: Write failing severity/aggregation tests**

Add tests for at least:

```python
def test_groups_repeated_waf_signals_into_compact_edge_abuse_finding():
    ...

def test_classifies_listener_protocol_mismatch_as_edge_config_mismatch():
    ...
```

- [ ] **Step 3: Write failing retention-boundary tests**

Add tests proving:

- raw headers are not emitted
- full query strings are not emitted
- evidence is limited to short summarized items

- [ ] **Step 4: Run the new classifier test file and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_oci_waf_lb_compensating_control.py -v
```

Expected:
- FAIL because the OCI finding module does not exist yet

### Task 4: Implement OCI finding generation

**Files:**
- Create: `src/agent/main/oci_waf_lb_compensating_control.py`
- Test: `tests/agent/test_oci_waf_lb_compensating_control.py`

- [ ] **Step 1: Define summary and finding output structures**

Reuse the current Lucas compatibility contract:

- `security_suspicion_summary`
- `security_suspicion_findings`

- [ ] **Step 2: Implement small fixed classification set**

Phase 1 classification set:

- `suspicious_edge_abuse`
- `edge_health_degradation`
- `edge_config_mismatch`

- [ ] **Step 3: Implement aggregation and severity rules**

Rules:

- one finding summarizes repeated OCI events for the bounded window
- evidence list is short and deduplicated
- severity is based on bounded signal combinations, not a single noisy raw row when possible
- wording stays within edge/entrypoint monitoring boundaries

- [ ] **Step 4: Run classifier tests**

Run:

```bash
python3 -m unittest tests/agent/test_oci_waf_lb_compensating_control.py -v
```

Expected:
- PASS

## Chunk 3: Scheduled Reporting Integration

### Task 5: Add failing report-path tests first

**Files:**
- Modify: `tests/agent/test_cron_runner.py`
- Modify: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Add failing payload test**

Add a test proving that stored report payloads preserve OCI-derived `security_suspicion_summary` and `security_suspicion_findings`.

- [ ] **Step 2: Add failing formatting test**

Add a test proving existing compact security output remains readable with OCI-derived findings.

- [ ] **Step 3: Run targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- FAIL because the scheduled/report path does not yet carry OCI-derived findings

### Task 6: Wire OCI findings into scheduled reporting

**Files:**
- Modify: `src/agent/main/cron_runner.py`
- Modify: `src/agent/main/report_utils.py`
- Test: `tests/agent/test_cron_runner.py`
- Test: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Run OCI collection only when enabled**

Feature gate with explicit config before calling OCI collection.

- [ ] **Step 2: Merge OCI findings additively**

Do not add a new top-level OCI report contract. Merge OCI findings through existing `security_suspicion_*` fields.

- [ ] **Step 3: Preserve compact formatting**

Maintain current output constraints:

- summary first
- top findings only
- short lines only

- [ ] **Step 4: Re-run targeted tests**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

## Chunk 4: Docs, Templates, and Verification

### Task 7: Document runtime flags and operator intent

**Files:**
- Modify: `k8s/dev.env.template`
- Modify: `k8s/prod.env.template`
- Modify: `docs/ops/current-runtime-settings.md`
- Modify: `docs/ops/operations.md`

- [ ] **Step 1: Add OCI monitor flags to env templates**

Add at least:

- `OCI_MONITOR_ENABLED=false`
- `OCI_COMPARTMENT_ID=`
- `OCI_WAF_POLICY_IDS=`
- `OCI_LB_IDS=`
- `OCI_MONITOR_WINDOW_MINUTES=15`

- [ ] **Step 2: Document the operator boundary**

State clearly that Phase 1 is:

- read-only
- WAF/LB only
- bounded evidence retention
- not a full DDoS or ransomware detector

- [ ] **Step 3: Build docs**

Run:

```bash
npm run build
```

from the `docs/` directory.

Expected:
- PASS

### Task 8: Final verification sweep

- [ ] **Step 1: Run all OCI feature tests together**

Run:

```bash
python3 -m unittest tests/agent/test_oci_waf_lb_signal_collection.py tests/agent/test_oci_waf_lb_compensating_control.py tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run Python syntax verification**

Run:

```bash
python3 -m py_compile src/agent/main/oci_waf_lb_signal_collection.py src/agent/main/oci_waf_lb_compensating_control.py src/agent/main/oci_utils.py
```

Expected:
- PASS

## Open implementation inputs

Implementation can start before these are fully finalized, but they must remain explicit:

- target hosts/listeners/backend sets
- high-severity threshold rules
- production WAF policy mode assumptions

## Out-of-scope follow-up

After this plan ships, the next follow-up plan should cover:

- OCI Flow and Audit enrichment
- BE application-log correlation
- richer interactive triage and escalation workflows
