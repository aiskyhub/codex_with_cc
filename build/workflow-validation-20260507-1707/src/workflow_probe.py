#!/usr/bin/env python3
"""Workflow probe — validates a JSON task list and prints a summary."""

import json
import sys
from pathlib import Path

VALID_STATUSES = {"pending", "running", "passed", "failed"}


def validate_task(task: dict, index: int) -> None:
    """Validate a single task. Raises ValueError with a clear message."""
    if not isinstance(task.get("id"), str) or not task["id"]:
        raise ValueError(f"tasks[{index}].id: must be a non-empty string")
    if not isinstance(task.get("title"), str) or not task["title"]:
        raise ValueError(f"tasks[{index}].title: must be a non-empty string")
    if task.get("status") not in VALID_STATUSES:
        raise ValueError(
            f"tasks[{index}].status: invalid status '{task.get('status')}'"
        )


def summarize(payload: dict | list[dict]) -> dict:
    """Validate a payload or task list and return a summary dict."""
    tasks = payload.get("tasks") if isinstance(payload, dict) else payload
    if not isinstance(tasks, list):
        raise ValueError("tasks: must be an array")

    counts: dict[str, int] = {"pending": 0, "running": 0, "passed": 0, "failed": 0}
    failed_ids: list[str] = []

    for i, task in enumerate(tasks):
        validate_task(task, i)
        status = task["status"]
        counts[status] += 1
        if status == "failed":
            failed_ids.append(task["id"])

    return {
        "total": len(tasks),
        "counts": counts,
        "failed_task_ids": failed_ids,
        "ready": len(tasks) > 0 and counts["failed"] == 0 and counts["running"] == 0 and counts["pending"] == 0,
    }


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: workflow_probe.py <tasks.json>", file=sys.stderr)
        sys.exit(1)

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"Error: invalid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        result = summarize(data)
    except ValueError as e:
        print(f"Validation error: {e}", file=sys.stderr)
        sys.exit(1)

    json.dump(result, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
