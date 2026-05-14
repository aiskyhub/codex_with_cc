---
name: codex-with-cc-planning
description: Plan codex-with-cc workflows by turning a subagent or delegation request into scoped tasks, roles, acceptance criteria, and review gates before dispatch.
---

# Codex With CC Planning

Read `../codex-with-cc/CODEX_WITH_CC.md` before planning. Use this skill when a request needs child-agent, subagent, delegation, 子代理, 委派, or 派工 routing through codex-with-cc.

Produce a concise workflow design:

- Assign one `WorkflowId` for the user request.
- Split work into tasks with stable `TaskId` values.
- Choose one role per task: `planner`, `implementer`, `researcher`, `reviewer`, or `final-verifier`.
- Define `Scope` and verification commands for each task.
- Require implementer tasks to be reviewed before final acceptance.

Do not run `claude` or `delegate_to_claude.*` from the main thread.
