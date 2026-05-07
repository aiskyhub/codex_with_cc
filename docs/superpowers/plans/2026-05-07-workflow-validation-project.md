# Workflow Validation Project Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a small runnable validation project under `build/workflow-validation-20260507-1707` and exercise the Codex child-agent to Claude Code delegation path.

**Architecture:** The validation project is independent from repository runtime code. A Python CLI exposes pure validation and summary functions, pytest verifies behavior, and the delegation report records the real child-agent outcome.

**Tech Stack:** Python 3, pytest, PowerShell, Codex child agent, `codex_with_cc/windows_scripts/delegate_to_claude.ps1`.

---

## File Structure

- Create `build/workflow-validation-20260507-1707/src/workflow_probe.py`: CLI entry point and pure functions.
- Create `build/workflow-validation-20260507-1707/tests/test_workflow_probe.py`: pytest tests.
- Create `build/workflow-validation-20260507-1707/samples/passed.json`: sample all-passed task file.
- Create `build/workflow-validation-20260507-1707/README.md`: usage notes.
- Create `build/workflow-validation-20260507-1707/reports/delegation.md`: real delegation outcome after child agent returns.
- Create `.codex/codex_with_cc/tasks/20260507/170707000-workflow-validation-project.md`: child-agent worker task.

## Task 1: Write Failing Tests

**Files:**
- Create: `build/workflow-validation-20260507-1707/tests/test_workflow_probe.py`

- [ ] **Step 1: Write tests first**

```python
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
SCRIPT = SRC / "workflow_probe.py"


def load_module():
    sys.path.insert(0, str(SRC))
    import workflow_probe

    return workflow_probe


def test_summarize_tasks_counts_statuses_and_failed_ids():
    workflow_probe = load_module()
    payload = {
        "tasks": [
            {"id": "plan", "title": "Plan", "status": "passed"},
            {"id": "delegate", "title": "Delegate", "status": "running"},
            {"id": "verify", "title": "Verify", "status": "failed"},
        ]
    }

    summary = workflow_probe.summarize(payload)

    assert summary == {
        "total": 3,
        "counts": {"pending": 0, "running": 1, "passed": 1, "failed": 1},
        "failed_task_ids": ["verify"],
        "ready": False,
    }


def test_ready_is_true_only_when_every_task_passed():
    workflow_probe = load_module()
    payload = {
        "tasks": [
            {"id": "tests", "title": "Tests", "status": "passed"},
            {"id": "docs", "title": "Docs", "status": "passed"},
        ]
    }

    assert workflow_probe.summarize(payload)["ready"] is True


def test_missing_task_field_raises_clear_validation_error():
    workflow_probe = load_module()
    payload = {"tasks": [{"id": "broken", "status": "pending"}]}

    try:
        workflow_probe.summarize(payload)
    except workflow_probe.ValidationError as exc:
        assert "tasks[0].title" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")


def test_invalid_status_raises_clear_validation_error():
    workflow_probe = load_module()
    payload = {"tasks": [{"id": "x", "title": "X", "status": "done"}]}

    try:
        workflow_probe.summarize(payload)
    except workflow_probe.ValidationError as exc:
        assert "tasks[0].status" in str(exc)
        assert "done" in str(exc)
    else:
        raise AssertionError("Expected ValidationError")


def test_cli_prints_summary_json(tmp_path):
    sample = tmp_path / "tasks.json"
    sample.write_text(
        json.dumps({"tasks": [{"id": "all", "title": "All", "status": "passed"}]}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(sample)],
        check=True,
        text=True,
        capture_output=True,
    )

    assert json.loads(result.stdout) == {
        "total": 1,
        "counts": {"pending": 0, "running": 0, "passed": 1, "failed": 0},
        "failed_task_ids": [],
        "ready": True,
    }
```

- [ ] **Step 2: Run test to verify RED**

Run:

```powershell
python -m pytest build\workflow-validation-20260507-1707\tests -q
```

Expected: fail because `workflow_probe.py` does not exist.

## Task 2: Implement CLI

**Files:**
- Create: `build/workflow-validation-20260507-1707/src/workflow_probe.py`
- Create: `build/workflow-validation-20260507-1707/samples/passed.json`
- Create: `build/workflow-validation-20260507-1707/README.md`

- [ ] **Step 1: Write minimal implementation**

```python
import json
import sys
from pathlib import Path

STATUSES = ("pending", "running", "passed", "failed")


class ValidationError(ValueError):
    pass


def _require_text(task, index, field):
    value = task.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"tasks[{index}].{field} must be a non-empty string")
    return value


def _validate_task(task, index):
    if not isinstance(task, dict):
        raise ValidationError(f"tasks[{index}] must be an object")
    task_id = _require_text(task, index, "id")
    _require_text(task, index, "title")
    status = _require_text(task, index, "status")
    if status not in STATUSES:
        allowed = ", ".join(STATUSES)
        raise ValidationError(f"tasks[{index}].status {status!r} must be one of: {allowed}")
    return task_id, status


def summarize(payload):
    if not isinstance(payload, dict):
        raise ValidationError("input must be a JSON object")
    tasks = payload.get("tasks")
    if not isinstance(tasks, list):
        raise ValidationError("tasks must be an array")

    counts = {status: 0 for status in STATUSES}
    failed_task_ids = []
    for index, task in enumerate(tasks):
        task_id, status = _validate_task(task, index)
        counts[status] += 1
        if status == "failed":
            failed_task_ids.append(task_id)

    return {
        "total": len(tasks),
        "counts": counts,
        "failed_task_ids": failed_task_ids,
        "ready": bool(tasks) and counts["passed"] == len(tasks),
    }


def load_payload(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValidationError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"invalid JSON in {path}: {exc}") from exc


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: workflow_probe.py <tasks.json>", file=sys.stderr)
        return 2
    try:
        summary = summarize(load_payload(args[0]))
    except ValidationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Add all-passed sample**

```json
{
  "tasks": [
    {"id": "plan", "title": "Write plan", "status": "passed"},
    {"id": "delegate", "title": "Run child delegation", "status": "passed"},
    {"id": "verify", "title": "Run local verification", "status": "passed"}
  ]
}
```

- [ ] **Step 3: Add README**

```markdown
# Workflow Validation Project

This project is a small validation target for the Codex with Claude Code workflow.

## Test

```powershell
python -m pytest tests -q
```

## Run

```powershell
python src\workflow_probe.py samples\passed.json
```
```

- [ ] **Step 4: Run tests to verify GREEN**

Run:

```powershell
python -m pytest build\workflow-validation-20260507-1707\tests -q
```

Expected: all tests pass.

## Task 3: Delegate Through Child Agent

**Files:**
- Create: `.codex/codex_with_cc/tasks/20260507/170707000-workflow-validation-project.md`
- Create: `build/workflow-validation-20260507-1707/reports/delegation.md`

- [ ] **Step 1: Write worker task file**

The task file must instruct the child worker to implement Task 1 and Task 2, run pytest, and finish with these exact headings:

```text
Process Log
Summary
Changed Files
Verification
Final Result
Risks Or Follow-ups
```

- [ ] **Step 2: Dispatch Codex child agent**

The child agent must set `CODEX_CLAUDE_CHILD_THREAD=1` before invoking `codex_with_cc/windows_scripts/delegate_to_claude.ps1`.

- [ ] **Step 3: Record real delegation outcome**

Write `build/workflow-validation-20260507-1707/reports/delegation.md` with the command outcome, changed files reported by the child, verification reported by the child, and any real blocker.

## Task 4: Main Thread Verification

**Files:**
- Read: `build/workflow-validation-20260507-1707/src/workflow_probe.py`
- Read: `build/workflow-validation-20260507-1707/tests/test_workflow_probe.py`
- Read: `build/workflow-validation-20260507-1707/reports/delegation.md`

- [ ] **Step 1: Run pytest**

```powershell
python -m pytest build\workflow-validation-20260507-1707\tests -q
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI sample**

```powershell
python build\workflow-validation-20260507-1707\src\workflow_probe.py build\workflow-validation-20260507-1707\samples\passed.json
```

Expected stdout:

```json
{"counts": {"failed": 0, "passed": 3, "pending": 0, "running": 0}, "failed_task_ids": [], "ready": true, "total": 3}
```

- [ ] **Step 3: Inspect git diff**

```powershell
git status --short
git diff -- docs/superpowers/specs/2026-05-07-workflow-validation-project-design.md docs/superpowers/plans/2026-05-07-workflow-validation-project.md
```

Expected: only scoped files and ignored `build` project files exist.
