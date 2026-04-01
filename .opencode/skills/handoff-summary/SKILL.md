# Handoff Summary

Use this skill whenever you need to produce, update, or consume a handoff summary for the `lucas` project.

## Purpose

This skill keeps work continuity stable across:

- local terminal sessions
- Telegram/mobile fallback sessions
- external handoff between Hermes and OpenCode

## Required references

- `./.opencode/skills/handoff-summary/references/spec.md`
- `./docs/ops/current-handoff-state.md`

## Rules

1. Treat the canonical format in `references/spec.md` as the source of truth.
2. When asked to resume work, first read `docs/ops/current-handoff-state.md`.
3. When finishing meaningful planning or implementation work, output a handoff summary in the canonical format.
4. Keep the summary short and factual.
5. Do not invent progress, changed files, or verification results.

## Output contract

Always produce this structure:

```text
handoff:
- project: lucas
- engine: OpenCode
- goal: ...
- current_state: ...
- changed_files: ...
- verification: ...
- blocker: ...
- next_action: ...
```
