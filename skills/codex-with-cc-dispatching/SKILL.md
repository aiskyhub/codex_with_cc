---
name: codex-with-cc-dispatching
description: Dispatch codex-with-cc tasks through the required Codex child thread -> delegate_to_claude.* -> Claude Code CLI chain with WorkflowId, TaskId, Role, and Scope metadata.
---

# Codex With CC Dispatching

Read `../codex-with-cc/CODEX_WITH_CC.md` before dispatching. Use this skill after planning has produced task boundaries.

Dispatch rules:

- Every child thread uses `model: gpt-5.3-codex`, `reasoning_effort: medium`, and `fork_context: false`.
- Every worker command sets `CODEX_CLAUDE_CHILD_THREAD=1`.
- Every worker command passes `-TaskFile`, `-WorkflowId`, `-TaskId`, and `-Role`.
- Parallel writable tasks require explicit non-overlapping `-Scope` values.
- Use `PrimaryAnchor` for a parallel batch anchor, `ParallelPool` for independent side work, and `PrimaryReuse` for serial follow-up.

Do not dispatch default Codex workers outside the codex-with-cc chain.
