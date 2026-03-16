# Drift Auditor Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only, deterministic drift auditor to Lucas scheduled reporting that detects storage, ConfigMap code, and runtime configuration drift and emits operator-ready remediation guidance.

**Architecture:** Implement a new `drift_auditor.py` module that evaluates live Kubernetes/runtime inputs into a structured drift report. Integrate it into the scheduled cron path first, store the new fields additively in the existing report payload, and format a concise Slack drift section without changing cluster state.

**Tech Stack:** Python 3.12, `unittest`, kubectl-driven runtime inspection, existing Lucas scheduled reporting pipeline, VitePress docs.

---

## Scope Lock

This plan covers **Phase 1 only** from the drift-auditor TRD:

- scheduled-path integration
- read-only detection
- deterministic evidence
- remediation guidance output

This plan does **not** implement:

- interactive Slack drift diagnosis routing
- automatic remediation
- dashboard redesign or schema migration
- broad rule externalization

For this repository, **do not create git commits during execution unless the user explicitly asks for them.**

## File Structure

### New files

- `src/agent/main/drift_auditor.py` — deterministic drift classification and report generation
- `tests/agent/test_drift_auditor.py` — unit tests for drift-family detection and output shape

### Modified files

- `src/agent/main/cron_runner.py` — invoke drift auditor and append drift data to scheduled reports
- `src/agent/main/report_utils.py` — add drift-aware Slack formatting while keeping compatibility
- `tests/agent/test_cron_runner.py` — scheduled-path integration coverage
- `tests/agent/test_report_utils.py` — Slack formatting coverage for drift output
- `docs/specs/index.md` — include this implementation-plan document in the spec set
- `docs/ops/operations.md` — optional short operator note for interpreting drift findings

### Existing files to reference while implementing

- `src/agent/main/cluster_snapshot.py`
- `src/agent/main/llm.py`
- `k8s/agent-deployment.yaml`
- `k8s/cronjob.yaml`
- `docs/specs/prd-drift-auditor.md`
- `docs/specs/trd-drift-auditor.md`
- `docs/specs/status-first-reporting.md`

### Live resource names to assume in validation

- Deployment: `a2w-lucas-agent`
- CronJob: `a2w-lucas`
- Dev namespace: `a2w-lucas`
- Prod namespace: `lucas`

When implementation needs live collection examples, make the collection layer target these known resource names rather than inventing generic placeholders.

## Chunk 1: Deterministic Drift Core

### Task 1: Create failing tests for drift classification

**Files:**
- Create: `tests/agent/test_drift_auditor.py`
- Reference: `docs/specs/prd-drift-auditor.md`
- Reference: `docs/specs/trd-drift-auditor.md`

- [ ] **Step 1: Write failing storage-drift tests**

Add tests that cover at least:

```python
def test_detects_storage_node_placement_mismatch():
    ...

def test_detects_attach_error_from_pod_events():
    ...
```

- [ ] **Step 2: Write failing ConfigMap code-drift tests**

Add tests that cover at least:

```python
def test_detects_missing_provider_branch_in_mounted_llm_code_when_configmap_mounts_exist():
    ...

def test_detects_agent_and_cron_runtime_surface_mismatch():
    ...
```

For this MVP, interpret “runtime surface mismatch” as:

- ConfigMap-mounted code mismatch when ConfigMap mounts exist
- image/tag mismatch when ConfigMap mounts do not exist

- [ ] **Step 3: Write failing runtime-config drift tests**

Add tests that cover at least:

```python
def test_detects_provider_model_mismatch_between_deployment_and_cronjob():
    ...

def test_detects_secret_ref_mismatch_for_selected_provider():
    ...
```

- [ ] **Step 4: Write failing output-shape test**

Add a test that asserts the top-level output shape:

```python
def test_build_drift_audit_result_returns_expected_top_level_shape():
    ...
```

- [ ] **Step 5: Run test file to confirm expected failure**

Run:

```bash
python3 -m unittest tests/agent/test_drift_auditor.py -v
```

Expected:
- FAIL because `drift_auditor.py` does not exist yet

### Task 2: Implement the core drift auditor module

**Files:**
- Create: `src/agent/main/drift_auditor.py`
- Test: `tests/agent/test_drift_auditor.py`

- [ ] **Step 1: Define stable data shapes**

Add typed dictionaries or equivalent structures for:

- `DriftFinding`
- `DriftAuditResult`

Also define a test-friendly evaluator input shape. The core evaluator must accept already-parsed Kubernetes/runtime dictionaries or extracted primitives rather than calling `kubectl` directly.

Recommended split:

- collection wrapper -> gathers live data
- pure evaluator -> consumes dicts and returns deterministic findings

- [ ] **Step 2: Implement storage drift evaluators**

Implement deterministic helpers for:

- PVC selected-node vs workload node-placement mismatch
- attach-failure event detection
- storage/node placement evidence extraction

- [ ] **Step 3: Implement ConfigMap code drift evaluators**

Implement helpers that compare:

- agent runtime surface vs cron runtime surface
- mounted `llm.py` provider branch presence or absence when ConfigMap mounts exist
- image/tag mismatch when runtime code is image-backed instead of ConfigMap-backed

- [ ] **Step 4: Implement runtime-config drift evaluators**

Implement helpers that compare:

- `LLM_PROVIDER`
- `LLM_MODEL`
- `LLM_BASE_URL`
- provider-related secret refs

- [ ] **Step 5: Implement final aggregator**

Implement a top-level function such as:

```python
def build_drift_audit_result(...):
    ...
```

It should return:

- `status`
- `drift_summary`
- `drifts`

It should accept explicit inputs for at least:

- deployment spec/env snapshot
- cronjob spec/env snapshot
- PVC/PV summaries
- node placement metadata
- runtime surface metadata (ConfigMap files and/or image identifiers)

- [ ] **Step 6: Run the new drift-auditor tests**

Run:

```bash
python3 -m unittest tests/agent/test_drift_auditor.py -v
```

Expected:
- PASS

## Chunk 2: Scheduled Reporting Integration

### Task 3: Add scheduled-path integration tests first

**Files:**
- Modify: `tests/agent/test_cron_runner.py`
- Modify: `tests/agent/test_report_utils.py`
- Reference: `src/agent/main/cron_runner.py`
- Reference: `src/agent/main/report_utils.py`

- [ ] **Step 1: Add failing cron integration test**

Add a test that proves scheduled reporting can include a drift section without breaking existing report fields.

- [ ] **Step 2: Add failing Slack formatting test**

Add a test that proves drift findings are rendered as a concise additive section and do not replace the existing summary/report contract.

- [ ] **Step 2.5: Add failing parser-plumbing test**

Add a test that proves drift fields survive the current `extract_report_payload()` -> `parse_run_report()` -> `format_slack_scan_message()` pipeline.

- [ ] **Step 3: Run targeted tests and confirm failure**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- FAIL because cron/report formatting does not yet know about drift output

### Task 4: Integrate drift auditor into cron reporting

**Files:**
- Modify: `src/agent/main/cron_runner.py`
- Modify: `src/agent/main/report_utils.py`
- Test: `tests/agent/test_cron_runner.py`
- Test: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Add data collection wiring in `cron_runner.py`**

Integrate deterministic drift input collection using the existing scheduled runtime path.

Recommended rule:
- collect drift inputs after snapshot collection and before final report formatting

- [ ] **Step 2: Append drift fields additively**

Update the report payload contract to include:

- `drift_summary`
- `drifts`

without removing or renaming existing compatibility keys.

Important plumbing rule:

- either extend `parse_run_report()` to preserve drift fields
- or pass drift data separately from `cron_runner.py`

Do not assume the existing parser keeps unknown fields.

- [ ] **Step 3: Add concise Slack drift formatting**

Update `format_slack_scan_message()` to render drift findings in a small additive section only when findings exist.

Formatting constraints:
- no command transcripts
- no excessive detail
- preserve current status-first message shape

- [ ] **Step 4: Run targeted scheduled/report tests**

Run:

```bash
python3 -m unittest tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

## Chunk 3: Operator Docs and Final Verification

### Task 5: Document the new drift-auditor behavior briefly

**Files:**
- Modify: `docs/specs/index.md`
- Modify: `docs/ops/operations.md`

- [ ] **Step 1: Link this implementation plan in the specs index**

Add this plan document to the drift-auditor document set.

- [ ] **Step 2: Add a short operator-facing note**

Describe that the first release:

- is read-only
- reports evidence, likely cause, and remediation steps
- covers storage/code/runtime drift only

- [ ] **Step 3: Verify docs still build**

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

### Task 6: Final verification sweep

**Files:**
- Verify: `src/agent/main/drift_auditor.py`
- Verify: `src/agent/main/cron_runner.py`
- Verify: `src/agent/main/report_utils.py`
- Verify: `tests/agent/test_drift_auditor.py`
- Verify: `tests/agent/test_cron_runner.py`
- Verify: `tests/agent/test_report_utils.py`

- [ ] **Step 1: Run all drift-related tests together**

Run:

```bash
python3 -m unittest tests/agent/test_drift_auditor.py tests/agent/test_cron_runner.py tests/agent/test_report_utils.py -v
```

Expected:
- PASS

- [ ] **Step 2: Run Python syntax verification on touched runtime files**

Run:

```bash
python3 -m py_compile src/agent/main/drift_auditor.py src/agent/main/cron_runner.py src/agent/main/report_utils.py
```

Expected:
- PASS

- [ ] **Step 3: Re-read the output wording against the spec**

Manual review checklist:

- evidence is factual
- likely cause is not overclaimed
- remediation steps are actionable
- no auto-fix promise appears in first-release wording

## Out-of-Scope Follow-Up

After this plan ships, the next follow-up plan should cover:

- interactive Slack drift diagnosis
- optional safe-case auto-remediation
- dashboard surfacing for drift history

## Atomic Commit Strategy (only if the user explicitly asks for commits during execution)

- Commit 1: add `drift_auditor.py` and `tests/agent/test_drift_auditor.py`
- Commit 2: integrate scheduled path in `cron_runner.py` and update `tests/agent/test_cron_runner.py`
- Commit 3: add drift-aware formatting/parser plumbing in `report_utils.py` and update `tests/agent/test_report_utils.py`
- Commit 4: docs/index/operator notes only
