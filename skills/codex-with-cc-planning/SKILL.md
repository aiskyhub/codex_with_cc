---
name: codex-with-cc-planning
description: Plan codex-with-cc workflows by turning a subagent or delegation request into scoped tasks, roles, acceptance criteria, and review gates before dispatch.
---

# Codex With CC Planning

Read `../codex-with-cc/CODEX_WITH_CC.md` before planning. Use this skill when a request needs child-agent, subagent, delegation, 子代理, 委派, or 派工 routing through codex-with-cc.

Produce a concise workflow design before any dispatch. The output must be usable as TaskFile content:

- Assign one `WorkflowId` for the user request.
- Split work into task-file-sized assignments with stable `TaskId` values and explicit dependencies recorded as `-DependsOn`.
- Choose one role per task: `planner`, `implementer`, `researcher`, `reviewer`, or `final-verifier`.
- Define `Scope`, allowed writes, forbidden writes, verification commands, and a stable `SessionKey` for each task.
- Mark each task as serial, parallel read-only, or parallel writable with non-overlapping scope.
- Define acceptance criteria and both required review gates for every implementer task: `spec` review first, then `quality` review.
- Include a final-verifier task for every workflow with implementer tasks; workflow verification rejects accepted implementation work without it.
- Give every task `Goal`, `Allowed Scope`, `Forbidden Actions`, `Acceptance Criteria`, `Verification`, and `Report Requirements`.
- Plan a `validate_delegate_task.*` pre-dispatch check for non-trivial task files and any task with `-Tests` or reviewer metadata.
- Use `../codex-with-cc/contract.json` values for roles, status tokens, and report headings; do not invent local variants.

Planning quality checks:

- Do not dispatch a task that depends on an unresolved product decision.
- Do not parallelize tasks that may write the same file or mutate the same behavior.
- Treat implementer tasks as writable; parallel implementers must have explicit non-overlapping scopes.
- Prefer a small researcher task before implementation when the code path is unknown.
- Do not plan inline `-Task`, legacy `-Mode`, or implicit session-key fallback.
- Return `NEEDS_CONTEXT` when safe decomposition is not possible from the current request and repository context.

Do not run `claude` or `delegate_to_claude.*` from the main thread.
