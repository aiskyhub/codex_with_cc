---
name: codex-with-cc-worker
description: Prepare codex-with-cc worker task files and report requirements for Claude Code execution roles.
---

# Codex With CC Worker

Read `../codex-with-cc/CODEX_WITH_CC.md` before preparing a worker task.

Worker task files must state:

- The exact assignment and intended role.
- Allowed scope and files that may be changed or inspected.
- Required verification commands.
- The report headings: Status, Role, Summary, Changed Files, Verification, Findings, Final Result, Risks Or Follow-ups.

Workers must not create nested delegate runs. If a worker needs more context, it reports `NEEDS_CONTEXT`.
