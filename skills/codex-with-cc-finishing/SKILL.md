---
name: codex-with-cc-finishing
description: Finish codex-with-cc workflows by verifying workflow artifacts, session continuity when needed, and final acceptance evidence.
---

# Codex With CC Finishing

Read `../codex-with-cc/CODEX_WITH_CC.md` before finishing a workflow.

Completion checklist:

- Run `verify_delegate_workflow.*` for the `WorkflowId`.
- Run `verify_delegate_chain.*` when the workflow used PrimaryAnchor, ParallelPool, or PrimaryReuse continuity checks.
- Run the repository's focused or full regression command after accepted implementation tasks.
- Confirm every implementer task has accepted `spec` and `quality` reviewer runs.
- Confirm every implementer workflow has an accepted `final-verifier` run.
- Confirm non-dry-run `DONE` reports include all commands passed with `-Tests`.
- Confirm parallel implementer tasks have explicit non-overlapping scopes.
- Confirm task files used the required Goal / Scope / Forbidden / Acceptance / Verification / Report contract.
- Confirm every accepted run has matching Status, Role, Final Result, and workflow artifact metadata.
- Summarize only accepted tasks, rejected tasks, blocked tasks, verification evidence, and residual risks.

Do not claim completion unless verification actually ran and passed or the blocker is explicitly reported.
