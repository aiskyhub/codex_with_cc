# Workflow Validation Project Design

## Goal

Create a new project under `build/workflow-validation-20260507-1707` that validates the repository's Codex with Claude Code workflow using a real Codex child-agent delegation attempt and locally runnable tests.

## Scope

The project is a small Python CLI named `workflow_probe`. It reads a JSON file containing workflow tasks, validates each task, computes status counts, and prints a normalized JSON summary. The project must include source code, tests, a README, and a report file describing the delegation result.

## Architecture

The validation project is intentionally independent from the repository's production workflow code. It is a build artifact project that exercises the surrounding delegation protocol without modifying `codex_with_cc` runtime scripts.

The CLI has three units:

- `workflow_probe.py`: command-line entry point and pure functions for loading, validating, and summarizing tasks.
- `tests/test_workflow_probe.py`: pytest coverage for valid input, missing fields, invalid statuses, and CLI output.
- `README.md`: commands for running tests and invoking the CLI.

## Data Contract

Input JSON must be an object with a `tasks` array. Each task must include:

- `id`: non-empty string
- `title`: non-empty string
- `status`: one of `pending`, `running`, `passed`, or `failed`

The CLI prints an object with:

- `total`: integer task count
- `counts`: object containing all four statuses
- `failed_task_ids`: array of IDs whose status is `failed`
- `ready`: boolean, true only when every task status is `passed`

Invalid input exits non-zero and prints a clear error to stderr.

## Delegation Flow

The main Codex thread must not run `delegate_to_claude.ps1` directly. The main thread writes a task file under `.codex/codex_with_cc/tasks/20260507/`, then dispatches a Codex child agent. The child agent sets `CODEX_CLAUDE_CHILD_THREAD=1` and runs:

```powershell
pwsh -NoProfile -File .\codex_with_cc\windows_scripts\delegate_to_claude.ps1 `
  -TaskFile <task-file> `
  -SessionMode PrimaryReuse `
  -SessionKey workflow-validation-20260507-1707 `
  -BypassPermissions
```

The delegated worker must finish with the headings required by `codex_with_cc/CODEX_WITH_CC.md` if Claude Code CLI is available. If the local environment cannot run the worker, the failure is recorded as a real delegation failure, not replaced with a fake success.

## Testing

The project uses Python standard library plus pytest. Required verification:

```powershell
python -m pytest build\workflow-validation-20260507-1707\tests -q
python build\workflow-validation-20260507-1707\src\workflow_probe.py build\workflow-validation-20260507-1707\samples\passed.json
```

## Risks

- Claude Code CLI may not be installed or authenticated on this machine.
- The workflow delegation script may fail before creating complete artifacts.
- Build artifacts under `build` are ignored by git, so final delivery must summarize created files explicitly.
