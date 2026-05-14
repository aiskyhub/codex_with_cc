---
name: codex-with-cc-reviewing
description: Review codex-with-cc worker reports, verification evidence, changed files, and findings before accepting or returning delegated work.
---

# Codex With CC Reviewing

Read `../codex-with-cc/CODEX_WITH_CC.md` before reviewing delegated results.

Review duties:

- Verify the run artifact with `verify_delegate_run.*` or `verify_delegate_artifacts.*`.
- Check that Status and Final Result use the same valid status token.
- Inspect Changed Files and Verification for concrete evidence.
- Treat `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, `BLOCKED`, and `FAIL` as requiring main-thread judgment before acceptance.
- Return the task for rework when findings are valid and actionable.

Do not accept a report that lacks the required headings or exact verification outcomes.
