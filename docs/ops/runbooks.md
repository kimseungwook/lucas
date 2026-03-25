# Runbooks

Runbooks live in `src/agent/runbooks/` and are loaded by the agent. You can add your own runbooks (Markdown) to capture team-specific procedures and escalation rules, then rebuild the agent image.

## CrashLoopBackOff

- Check pod events and logs.
- Do not change app code.
- Escalate if the issue is not config or a simple health check.

## ImagePullBackOff

- Check pod events for auth, tag, or network errors.
- Do not change image tags or credentials.
- Escalate to the owning team.

## OOMKilled

- Verify memory limits and recent usage.
- Allowed fix: increase memory limit in small steps.
- Escalate if limits need to exceed 4Gi or if leaks are suspected.

## Pod Death Without Source Access

- Use when a pod dies or restarts but the workload source code is not available.
- Collect phase, reason, restart count, events, current logs, and previous logs first.
- Classify into one primary bucket: config/secret, image/startup, resource/probe, dependency, infra/placement, or pod-local transient failure.
- Prefer escalation over repeated restarts when the issue is not clearly isolated to one pod.
