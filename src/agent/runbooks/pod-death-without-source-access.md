# Pod Death Without Source Access

## Use this runbook when
- A pod dies, restarts, or enters `CrashLoopBackOff` / `Error` / `Pending`
- The workload source code is not available for direct remediation
- The immediate goal is safe diagnosis, stabilization, and escalation

## Minimum evidence
Before recommending any action, collect:
1. `kubectl get pods -n <namespace> -o wide`
2. `kubectl describe pod <name> -n <namespace>`
3. `kubectl logs <name> -n <namespace> --tail=100 --timestamps`
4. `kubectl logs <name> -n <namespace> --previous --tail=100 --timestamps` if restart count is non-zero
5. `kubectl get events -n <namespace> --sort-by='.lastTimestamp'`

Also capture:
- owner workload (`Deployment`, `StatefulSet`, `Job`, `CronJob`)
- restart count
- current phase/reason
- whether sibling replicas are healthy

## Primary hypothesis buckets

### 1. Config or secret failure
Signals:
- `CreateContainerConfigError`
- missing `Secret` or `ConfigMap`
- invalid startup configuration

Action:
- Verify referenced config exists and matches the workload contract.
- Escalate to the manifest/config owner.
- Do **not** keep recycling pods.

### 2. Image or startup failure
Signals:
- `ImagePullBackOff`
- `ErrImagePull`
- image not found / unauthorized / registry timeout

Action:
- Verify image tag, digest, registry credentials, and recent rollout state.
- Escalate to image/release owner.
- Do **not** change tags or credentials without approval.

### 3. Resource or probe failure
Signals:
- `OOMKilled`
- liveness/readiness/startup probe failure
- repeated restart with no image/config error

Action:
- Verify limits/requests and probe timings.
- Escalate if manifest tuning is needed.
- If a restart is suggested, treat it as temporary relief only.

### 4. Dependency connectivity failure
Signals:
- connection refused
- timeout / DNS / TLS / auth errors to DB, Redis, queue, object storage, or internal API

Action:
- Verify dependency reachability and credentials.
- Check whether sibling workloads show the same issue.
- Escalate to the dependency owner if the backend itself is degraded.

### 5. Infra or placement failure
Signals:
- `AttachVolume.Attach failed`
- mount/attach error
- scheduling or node-placement mismatch
- PVC/PV or zone/shape incompatibility clues

Action:
- Verify PVC/PV state, selected node, actual node, and scheduling events.
- Escalate to platform/storage owner.
- Do **not** keep deleting pods as the main response.

### 6. Pod-local transient failure
Signals:
- one pod unhealthy while peers are healthy
- no clear config/image/infra signal
- restart appears isolated

Action:
- Inspect current and previous logs first.
- If no rollout or infra-wide symptom exists, one shallow recycle may be reasonable.
- Escalate if the same pattern spreads to sibling replicas.

## Decision rules
- Evidence first, likely cause second, recommended action last.
- Prefer the shallowest reversible action.
- If the issue is not clearly pod-local, avoid restart churn.
- If source access is unavailable, bias toward escalation with a clean incident package.

## Escalation package
When escalating, include:
- namespace / pod / workload
- phase / reason / restart count
- top 2-3 evidence lines
- chosen hypothesis bucket
- blast radius (`isolated_pod`, `single_workload`, `multi_workload`)
- actions already tried
