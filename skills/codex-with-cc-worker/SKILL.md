---
name: codex-with-cc-worker
description: Prepare codex-with-cc worker task files and report requirements for Claude Code execution roles.
---

# Codex With CC Worker

Read `../codex-with-cc/CODEX_WITH_CC.md` before preparing a worker task.

Worker task files must use these exact sections:

- `Goal`: the exact assignment and intended role.
- `Allowed Scope`: files or behavior that may be changed or inspected.
- `Forbidden Actions`: out-of-scope files, behaviors, nested delegation, and follow-up work the worker must not execute.
- `Acceptance Criteria`: self-checks before reporting.
- `Verification`: exact commands the worker must run.
- `Report Requirements`: Status, Role, Summary, Changed Files, Verification, Findings, Final Result, Risks Or Follow-ups.

Worker behavior:

- If the Goal, scope, acceptance criteria, or verification commands are unclear, stop before editing and report `NEEDS_CONTEXT`.
- Execute the assigned task directly; do not create nested delegate runs.
- Implementers must use test-first or the smallest equivalent verification-first evidence before changing behavior when the repository has a practical test surface.
- Reviewers must perform exactly one review kind: `spec` or `quality`, for the provided `ReviewForTaskId`.
- Reviewers must not trust worker reports; they must verify code, artifacts, scope, and evidence independently.
- Keep noisy command output in artifacts and summarize only the evidence needed by the main thread.
- Before reporting, check scope compliance, changed files, verification results, and residual risks.
- Use `DONE_WITH_CONCERNS` only when required verification passed but meaningful risk remains.
- Use `NEEDS_CONTEXT` when the task cannot be completed without a main-thread decision.
- Use `BLOCKED` for external blockers and `FAIL` for failed work or invalid verification.
