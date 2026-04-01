# Lucas Handoff Summary Spec

## Canonical format

```text
handoff:
- project: <project name>
- engine: <OpenCode | Codex>
- goal: <final goal in one line>
- current_state: <where the work currently stands in 1-2 lines>
- changed_files: <comma-separated file list, or none>
- verification: <what was verified, or not run>
- blocker: <blocking issue, or none>
- next_action: <single next step>
```

## Field meanings

- `project`: canonical project name
- `engine`: coding engine used for the work
- `goal`: the final goal in one line
- `current_state`: current implementation/planning state in 1-2 lines
- `changed_files`: real changed files, or `none`
- `verification`: only real verification results, or `not run`
- `blocker`: current blocker, or `none`
- `next_action`: the single next step

## Writing rules

1. Keep every field short.
2. Use facts only.
3. Use `none` or `not run` instead of guessing.
4. `next_action` must be exactly one next step.

## When to write one

- before switching from terminal to Telegram/mobile
- before switching from Telegram/mobile back to terminal
- after meaningful planning work
- after meaningful implementation work
