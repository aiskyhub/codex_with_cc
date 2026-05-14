# Codex With Claude Code

This document is the portable entry point for the Codex -> Codex child agent -> Claude Code CLI workflow.

## Required Reading
1. Read this file before using the workflow in this repository.

## Core Contract
1. The Codex main thread must not run `claude` directly.
2. The Codex main thread must not run the installed plugin delegate entrypoint directly (`windows_scripts/delegate_to_claude.ps1` on Windows or `macos_scripts/delegate_to_claude.sh` on macOS inside the installed workflow root), except for the trusted local terminal fallback below.
3. Every Claude Code delegation must be carried by a Codex `spawn_agent` child thread.
4. The child thread must set `CODEX_CLAUDE_CHILD_THREAD=1` before invoking `delegate_to_claude.*`.
5. The child thread should use `model: gpt-5.3-codex`, `reasoning_effort: medium`, and `fork_context: false`.
6. `delegate_to_claude.*` must not pass `--effort`; Claude Code should use its configured default effort.
7. Medium and large tasks should be written to a dated, uniquely named task file under `.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-name>.md` and passed with `-TaskFile`.
8. Each delegated run must carry routing metadata: `-WorkflowId`, `-TaskId`, and `-Role`.
9. Claude workers must keep changes inside the delegated scope, run the required verification, and finish with the exact report headings defined in this document.
10. If the Codex sandbox or delegated runner cannot execute the same worker command, run that exact command in a trusted local terminal instead.
11. Claude workers must read and follow all applicable Codex project skills under `.codex` before implementing or changing behavior.

## Trigger Rule
Any user mention of child-agent, subagent, sub-agent, child-thread, subthread, delegation, worker-execution, or Chinese equivalents such as 子代理、子线程、多代理、委派、派工、执行层 is a workflow trigger. When triggered, the main Codex thread must use this custom delegation workflow and must not satisfy the request with the default Codex subagent flow, a host-provided agent shortcut, direct `claude` execution, or direct main-thread execution of `delegate_to_claude.*`.

## workflow/task/run Protocol
The protocol models every request as:

- `WorkflowId`: one user-level orchestration.
- `TaskId`: one scoped child-thread assignment inside that workflow.
- `RunId`: one concrete Claude Code execution attempt for a task.
- `Role`: one of `planner`, `implementer`, `researcher`, `reviewer`, or `final-verifier`.

Artifacts use the current artifact schema. Each run writes `config_<RunId>.json`, `status_<RunId>.json`, `prompt_<RunId>.md`, `stream_<RunId>.jsonl`, `trace_<RunId>.log`, and `claude_<RunId>.md`. Each workflow also writes `workflow_<WorkflowId>.json`, which indexes all tasks and runs.

## Multi-Skill Chain
The plugin exposes the entry skill plus stage-specific sibling skills:

- `codex-with-cc-planning`: create the task graph, acceptance criteria, and review gates.
- `codex-with-cc-dispatching`: select serial/parallel execution and assign workflow metadata.
- `codex-with-cc-worker`: prepare one worker task file and command.
- `codex-with-cc-reviewing`: judge worker reports and decide whether to accept, reject, or rework.
- `codex-with-cc-finishing`: run final workflow verification and summarize delivery.

## Platform Hook Gate
The Codex plugin declares `./hooks/hooks.json` as a platform hook layer. When the host has Codex hooks enabled, `SessionStart` injects the full `SKILL.md` and `CODEX_WITH_CC.md` contract inside an `<EXTREMELY_IMPORTANT>` bootstrap context, `UserPromptSubmit` reinforces that full contract whenever the user prompt mentions subagents or delegation, and `PreToolUse` denies supported tool calls that try direct `claude`, direct main-thread `delegate_to_claude.*`, missing workflow metadata, or parallel writable work without scope.

This is a semi-hard platform gate, not a full kernel boundary. Codex `PreToolUse` only blocks tool surfaces the host exposes to hooks; `SessionStart` and `UserPromptSubmit` carry the workflow contract for the rest of the model path.

## Trusted Local Terminal Fallback
This fallback is an execution-location fallback only. Preserve the same `CODEX_CLAUDE_CHILD_THREAD=1` marker, task file, `WorkflowId`, `TaskId`, `Role`, session mode, session key, artifact root, and permission flags that the child thread would have used.

Do not replace this with the default Codex subagent flow, a direct `claude` command, or a modified worker command. Report that the trusted terminal fallback was used and include the command outcome in verification.

## Roles
- Codex main thread: understand the request, define workflow/tasks, create child threads, review results, and decide final acceptance.
- Codex child thread: provide a visible conversation-tree node and invoke the worker script.
- Claude Code CLI: execute the delegated task, run verification, and produce a structured report.

Worker roles:

- `planner`: read-only task decomposition and acceptance criteria.
- `implementer`: code or file changes inside the assigned scope.
- `researcher`: read-only codebase or architecture investigation.
- `reviewer`: review worker output, changed files, and verification evidence.
- `final-verifier`: workflow-level acceptance and residual risk summary.

## Session Modes
- `PrimaryReuse`: default serial mode. Reuses the main Claude session for continuity.
- `PrimaryAnchor`: parallel-batch anchor. Its result becomes the main reusable context for later serial work.
- `ParallelPool`: independent parallel side work. Uses reusable pool sessions without writing to the main session.

Only use `-AllowParallel` when task scopes are independent. Parallel writable tasks must pass explicit `-Scope` values.

## Worker Output
Claude Code must finish with these exact headings:

```text
Status
Role
Summary
Changed Files
Verification
Findings
Final Result
Risks Or Follow-ups
```

`Status` and `Final Result` must be one of:

```text
DONE
DONE_WITH_CONCERNS
NEEDS_CONTEXT
BLOCKED
FAIL
```

Verification must list commands actually run and their outcomes. If verification is blocked, the report must explain the blocker and whether it is unrelated to the delegated change.

## Artifacts
Delegation artifacts are written under `.codex/codex_with_cc/claude-delegate` by default:

- `workflow_<WorkflowId>.json`
- `claude_<RunId>.md`
- `status_<RunId>.json`
- `config_<RunId>.json`
- `prompt_<RunId>.md`
- `stream_<RunId>.jsonl`
- `trace_<RunId>.log`
- `session-pools/<SessionKey>.json`

Use `verify_delegate_run.*` or `verify_delegate_artifacts.*` for each run, `verify_delegate_workflow.*` for the workflow aggregate, and `verify_delegate_chain.*` for multi-run session continuity checks. The shared implementation lives under `scripts/*.py`; platform wrappers should stay thin. macOS entrypoints are native shell wrappers around the same Python runtime, preserve the same Codex main thread -> child thread -> delegate entrypoint boundary as Windows, and only check for Python at runtime.

`<installed-workflow-root>` means the installed `skills/codex-with-cc` directory, for example `<codex-home>/plugins/cache/aiskyhub/codex-with-cc/<version-or-hash>/skills/codex-with-cc`. Do not use the package root `<version-or-hash>` directory; it does not contain `scripts`, `windows_scripts`, or `macos_scripts` directly.

## Standard Worker Command
Normally run this inside a Codex child thread. If the Codex sandbox or delegated runner cannot execute it, use the trusted local terminal fallback above.

Windows:

```powershell
$workflowRoot = '<installed-workflow-root>'
$env:CODEX_CLAUDE_CHILD_THREAD = '1'
pwsh -NoProfile -File (Join-Path $workflowRoot 'windows_scripts\delegate_to_claude.ps1') `
  -TaskFile .\.codex\codex_with_cc\tasks\<yyyyMMdd>\<HHmmssfff>-<short-id>-<task-file>.md `
  -WorkflowId <workflow-id> `
  -TaskId <task-id> `
  -Role implementer `
  -Scope <changed-or-inspected-path> `
  -SessionMode PrimaryReuse `
  -SessionKey <stable-session-key> `
  -BypassPermissions
```

macOS:

```bash
WORKFLOW_ROOT="<installed-workflow-root>"
export CODEX_CLAUDE_CHILD_THREAD=1
"$WORKFLOW_ROOT/macos_scripts/delegate_to_claude.sh" \
  -TaskFile ./.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md \
  -WorkflowId <workflow-id> \
  -TaskId <task-id> \
  -Role implementer \
  -Scope <changed-or-inspected-path> \
  -SessionMode PrimaryReuse \
  -SessionKey <stable-session-key> \
  -BypassPermissions
```

Use `PrimaryAnchor -AllowParallel` for the main branch of a parallel batch and `ParallelPool -AllowParallel` for independent side work.

## Verification
Run the local regression tests after installing or changing this workflow.

Windows:

```powershell
$workflowRoot = '<installed-workflow-root>'
pwsh -NoProfile -File (Join-Path $workflowRoot 'windows_scripts\test_delegate_runtime.ps1')
pwsh -NoProfile -File (Join-Path $workflowRoot 'windows_scripts\test_delegate_session_pool.ps1')
```

macOS:

```bash
WORKFLOW_ROOT="<installed-workflow-root>"
"$WORKFLOW_ROOT/macos_scripts/test_delegate_runtime.sh"
"$WORKFLOW_ROOT/macos_scripts/test_delegate_session_pool.sh"
```

Verify a run and workflow:

```powershell
pwsh -NoProfile -File (Join-Path $workflowRoot 'windows_scripts\verify_delegate_run.ps1') -RunId <run-id>
pwsh -NoProfile -File (Join-Path $workflowRoot 'windows_scripts\verify_delegate_workflow.ps1') -WorkflowId <workflow-id>
```

or on macOS:

```bash
"$WORKFLOW_ROOT/macos_scripts/verify_delegate_run.sh" -RunId <run-id>
"$WORKFLOW_ROOT/macos_scripts/verify_delegate_workflow.sh" -WorkflowId <workflow-id>
```
