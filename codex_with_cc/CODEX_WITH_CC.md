# Codex With Claude Code

This document is the portable entry point for the Codex -> Codex child agent -> Claude Code CLI workflow.

## Path Context

This file is written as a portable workflow contract, so command examples below use the **installed target-project paths** under `docs/codex_with_cc/...`.

When you are editing this source repository itself, the corresponding source paths are:

- `codex_with_cc/CODEX_WITH_CC.md`
- `codex_with_cc/windows_scripts/...`
- `codex_with_cc/unix_scripts/...`

When this workflow is installed into another repository, the corresponding target-project paths are:

- `docs/codex_with_cc/CODEX_WITH_CC.md`
- `docs/codex_with_cc/windows_scripts/...`
- `docs/codex_with_cc/unix_scripts/...`

Use source-repo paths when changing this repository. Use target-project paths when writing delegate commands, verification commands, or `AGENTS.md` guidance for an installed project.

## Required Reading
1. Read this file before using the workflow in this repository.

## Core Contract
1. The Codex main thread must not run `claude` directly.
2. The Codex main thread must not run `docs/codex_with_cc/windows_scripts/delegate_to_claude.ps1` or `docs/codex_with_cc/unix_scripts/delegate_to_claude.sh` directly, except for the trusted local terminal fallback below.
3. Every Claude Code delegation must be carried by a Codex `spawn_agent` child thread.
4. The child thread must set `CODEX_CLAUDE_CHILD_THREAD=1` before invoking the delegate script.
5. The child thread should use `model: gpt-5.3-codex`, `reasoning_effort: medium`, and `fork_context: false`.
6. The delegate script must not pass `--effort`; Claude Code should use its configured default effort.
7. Medium and large tasks should be written to a dated, uniquely named task file under `.codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-name>.md` and passed with `-TaskFile` (Windows) or `-f` (Linux/macOS).
8. Claude workers must keep changes inside the delegated scope, run the required verification, and finish with the exact report headings defined in this document.
9. If the Codex sandbox or delegated runner cannot execute the same worker command, run that exact command in a trusted local terminal instead.
10. Claude workers must read and follow all applicable Codex project skills under `.codex` before implementing or changing behavior.

## Trusted Local Terminal Fallback
This fallback is an execution-location fallback only. Preserve the same `CODEX_CLAUDE_CHILD_THREAD=1` marker, task file, session mode, session key, artifact root, and permission flags that the child thread would have used.

Do not replace this with the default Codex subagent flow, a direct `claude` command, or a modified worker command. Report that the trusted terminal fallback was used and include the command outcome in verification.

## Roles
- Codex main thread: understand the request, define scope, create child threads, review results, and decide final acceptance.
- Codex child thread: provide a visible conversation-tree node and invoke the worker script.
- Claude Code CLI: execute the delegated task, run verification, and produce a structured report.

## Session Modes
- `PrimaryReuse`: default serial mode. Reuses the main Claude session for continuity.
- `PrimaryAnchor`: semantic marker for the anchor task in a parallel batch. Behaviorally identical to `PrimaryReuse` (reuses the main session), but signals that this run's result becomes the reusable context for subsequent serial work in the same session.
- `ParallelPool`: independent parallel side work. Uses reusable pool sessions without writing to the main session.

Only use `-AllowParallel` when task scopes are independent.

## Worker Output
Claude Code must finish with these exact headings:

```text
Process Log
Summary
Changed Files
Verification
Final Result
Risks Or Follow-ups
```

Verification must list the commands actually run and their outcomes. If verification is blocked, the report must explain the blocker and whether it is unrelated to the delegated change.

## Artifacts
Delegation artifacts are written under `.codex/codex_with_cc/claude-delegate` by default:
- `claude_<RunId>.md`
- `status_<RunId>.json`
- `config_<RunId>.json`
- `prompt_<RunId>.md`
- `stream_<RunId>.jsonl`
- `trace_<RunId>.log`
- `session-pools/<SessionKey>.json`

Use `verify_delegate_artifacts.ps1` (Windows) or `verify_delegate_artifacts.sh` (Linux/macOS) for each run and `verify_delegate_chain.ps1` (Windows) or `verify_delegate_chain.sh` (Linux/macOS) for multi-run continuity checks.

## Platform-Specific Scripts

- Windows: `docs/codex_with_cc/windows_scripts/delegate_to_claude.ps1`
- Linux/macOS: `docs/codex_with_cc/unix_scripts/delegate_to_claude.sh`

## Standard Worker Command (Windows)

Normally run this inside a Codex child thread. If the Codex sandbox or delegated runner cannot execute it, use the trusted local terminal fallback above:

```powershell
$env:CODEX_CLAUDE_CHILD_THREAD = '1'
pwsh -NoProfile -File .\docs\codex_with_cc\windows_scripts\delegate_to_claude.ps1 `
  -TaskFile .\.codex\codex_with_cc\tasks\<yyyyMMdd>\<HHmmssfff>-<short-id>-<task-file>.md `
  -SessionMode PrimaryReuse `
  -SessionKey <stable-session-key> `
  -BypassPermissions
```

## Standard Worker Command (Linux/macOS)

```bash
export CODEX_CLAUDE_CHILD_THREAD=1
bash docs/codex_with_cc/unix_scripts/delegate_to_claude.sh \
  -f .codex/codex_with_cc/tasks/<yyyyMMdd>/<HHmmssfff>-<short-id>-<task-file>.md \
  --session-mode PrimaryReuse \
  --session-key <stable-session-key> \
  --bypass-permissions
```

Use `PrimaryAnchor --allow-parallel` for the main branch of a parallel batch and `ParallelPool --allow-parallel` for independent side work.

## Verification

Run the local regression tests after installing or changing this workflow:

### Windows

```powershell
pwsh -NoProfile -File .\docs\codex_with_cc\windows_scripts\test_delegate_runtime.ps1
pwsh -NoProfile -File .\docs\codex_with_cc\windows_scripts\test_delegate_session_pool.ps1
```

### Linux/macOS

```bash
bash docs/codex_with_cc/unix_scripts/test_delegate_runtime.sh
bash docs/codex_with_cc/unix_scripts/test_delegate_session_pool.sh
```

Generate a real chain validation scaffold with:

### Windows

```powershell
pwsh -NoProfile -File .\docs\codex_with_cc\windows_scripts\run_real_delegate_chain_validation.ps1
```

### Linux/macOS

```bash
bash docs/codex_with_cc/unix_scripts/run_real_delegate_chain_validation.sh
```
