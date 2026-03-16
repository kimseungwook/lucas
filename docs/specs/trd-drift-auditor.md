# TRD: Drift Auditor

## Objective

Design a deterministic, read-only drift-auditor layer for Lucas that compares live Kubernetes runtime state against expected Lucas runtime intent and returns actionable operational guidance.

The first release focuses on three drift families:

- storage and node-placement drift
- ConfigMap code drift
- runtime configuration drift

## Current state

Lucas already has deterministic cluster inspection for scheduled monitoring and reduced-capability non-Claude execution.

Relevant implemented runtime pieces:

- `src/agent/main/cluster_snapshot.py`
- `src/agent/main/cron_runner.py`
- `src/agent/main/main.py`
- `src/agent/main/report_utils.py`
- `src/agent/main/llm.py`

Recent live rollout work established a concrete need for a drift auditor:

- env-only provider changes were insufficient while code was still mounted from stale ConfigMaps
- production rollout was blocked by OCI volume attach and node-placement mismatch before Lucas itself started
- interactive and cron runtime surfaces needed explicit comparison rather than assuming they matched

## Design principles

### Deterministic first

Kubernetes object state and mounted runtime file contents are the source of truth. The LLM may help explain findings, but the auditor must not depend on the LLM to determine whether drift exists.

### Read-only first

The first release only reports and guides. It does not patch, restart, or mutate cluster resources.

### Evidence before recommendation

Every detected drift should include the evidence chain that led to the conclusion.

## Target architecture

### New logical component

Add a drift-auditor module in the agent runtime that can be called by both scheduled and interactive paths.

Suggested file target:

- `src/agent/main/drift_auditor.py`

Possible supporting utility targets if needed:

- `src/agent/main/drift_rules.py`
- `src/agent/main/drift_formatting.py`

### Inputs

The auditor should consume deterministic runtime inputs such as:

- Deployment spec and pod status
- CronJob spec and latest Job/Pod status
- PVC and PV objects
- selected-node annotations and node labels
- ConfigMap contents for mounted Lucas code
- env and secret refs relevant to provider selection

### Output

The auditor should return a structured drift report that can be embedded into scheduled reporting and summarized in interactive Slack replies.

Suggested types:

```python
class DriftFinding(TypedDict):
    type: str
    severity: str
    resource: str
    evidence: list[str]
    likely_cause: str
    recommended_actions: list[str]

class DriftAuditResult(TypedDict):
    status: str
    drift_summary: dict[str, int]
    drifts: list[DriftFinding]
```

## Drift family design

### 1. Storage and node-placement drift

Compare:

- PVC selected-node annotations
- PV driver and volume attributes
- node labels and selected workload placement
- pod events related to volume attach

Primary findings to detect:

- workload scheduled to a node pool inconsistent with PVC-selected lineage
- attach failures that prevent startup
- storage class and live node placement combination incompatible with current workload scheduling

Suggested evidence examples:

- `volume.kubernetes.io/selected-node`
- `topology.kubernetes.io/zone`
- `goyo-svc` or similar node-pool labels
- pod event messages containing attach errors

### 2. ConfigMap code drift

Compare:

- repo-intended provider runtime files
- `lucas-agent-code` mounted files
- `lucas-cron-code` mounted files

Primary findings to detect:

- interactive and cron ConfigMaps differ for key runtime files
- mounted `llm.py` does not contain provider support required by runtime env
- prompt or report logic files differ across interactive and cron surfaces in ways that affect provider/runtime behavior

Suggested evidence examples:

- presence or absence of provider branches in mounted `llm.py`
- hash or diff mismatch across key ConfigMap entries

### 3. Runtime configuration drift

Compare:

- Deployment env
- CronJob env
- secret refs
- provider/model/base URL combinations

Primary findings to detect:

- deployment and cron use different provider/model unintentionally
- provider-specific secret refs do not match selected provider
- generic and provider-specific envs conflict in a way that changes effective runtime selection

Suggested evidence examples:

- `LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`
- `OPENROUTER_API_KEY`, `GEMINI_API_KEY`, `LLM_API_KEY`
- actual selected provider resolution rules from `llm.py`

## Integration points

### Scheduled path

The scheduled path should run drift auditing after deterministic cluster snapshot collection and before final Slack summary formatting.

Recommended behavior:

- append drift findings to the stored report payload
- keep the existing health report intact
- allow Slack summary to include a short `drift_summary` section when findings exist

### Interactive path

The interactive path should allow operators to request drift diagnosis for the current runtime without requiring arbitrary mutation privileges.

Recommended behavior:

- surface the top findings only
- include exact remediation steps
- clearly mark findings as evidence-backed diagnostics, not actions already taken

## First-release output policy

The first release should use these wording boundaries:

- `evidence`: factual observed state
- `likely_cause`: best deterministic explanation from rule evaluation
- `recommended_actions`: operator steps only

Never claim:

- that a remediation has been applied when it has not
- that a drift cause is certain if multiple plausible causes remain
- that the auditor can always infer rollout intent from repo files alone

## Validation strategy

### Deterministic tests

Unit tests should cover at least:

- storage drift classification from fixture objects
- ConfigMap code drift detection from fixture text inputs
- env/provider drift detection from fixture Deployment/CronJob inputs
- formatting of evidence, cause, and remediation output

### Live validation

Use `goyo-dev` first with known drift scenarios derived from recent rollout history:

- stale code ConfigMap vs new env
- deployment-vs-cron provider mismatch
- PVC/node-placement mismatch if reproducible in a safe environment

### Acceptance behavior

The drift auditor is correct when:

- the same deterministic input always produces the same finding set
- the findings match real operator diagnosis for known recent failures
- the output gives actionable remediation without hidden assumptions

## Risks

- If drift rules are too loose, the auditor will become noisy and ignored.
- If drift rules are too strict, real rollout failures will be missed.
- If repo-vs-runtime comparison is treated as authoritative without context, it may misclassify intentionally drifted prod objects.

## Recommended rollout

### Phase 1

Implement read-only drift findings in scheduled reporting only.

### Phase 2

Expose the same findings through interactive operator requests.

### Phase 3

Consider limited auto-remediation only for narrowly proven-safe classes.
