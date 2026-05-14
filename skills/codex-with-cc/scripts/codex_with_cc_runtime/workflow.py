from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any

from .common import ARTIFACT_SCHEMA_VERSION, INVOCATION_CONTRACT, WORKER_ROLES, now_iso
from .io_utils import load_json, write_json


def safe_workflow_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value.strip())
    return safe or "workflow"


def safe_task_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", value.strip())
    return safe or "task"


def workflow_path(artifact_root: Path | str, workflow_id: str) -> Path:
    return Path(artifact_root).resolve() / f"workflow_{safe_workflow_id(workflow_id)}.json"


def new_workflow_id(session_key: str) -> str:
    return safe_workflow_id(f"wf-{session_key}") if session_key.strip() else f"wf-{uuid.uuid4().hex[:12]}"


def role_for_mode(mode: str) -> str:
    if mode.lower() == "review":
        return "reviewer"
    return "implementer"


def normalize_role(role: str) -> str:
    value = role.strip().lower()
    if value not in WORKER_ROLES:
        expected = ", ".join(WORKER_ROLES)
        raise ValueError(f"invalid role: {role!r} (choose from {expected})")
    return value


def empty_workflow(workflow_id: str) -> dict[str, Any]:
    now = now_iso()
    return {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "workflowId": workflow_id,
        "createdAt": now,
        "updatedAt": now,
        "tasks": {},
        "runs": {},
    }


def update_workflow_record(
    artifact_root: Path,
    workflow_id: str,
    task_id: str,
    role: str,
    scope: list[str],
    verification: list[str],
    run_id: str,
    config_path: Path,
    status_path: Path,
    output_path: Path,
    prompt_path: Path,
    raw_stream_path: Path,
    trace_path: Path,
    run_status: str,
) -> Path:
    path = workflow_path(artifact_root, workflow_id)
    if path.exists():
        workflow = load_json(path)
    else:
        workflow = empty_workflow(workflow_id)
    workflow["artifactSchema"] = ARTIFACT_SCHEMA_VERSION
    workflow["invocationContract"] = INVOCATION_CONTRACT
    workflow["workflowId"] = workflow_id
    workflow["updatedAt"] = now_iso()
    workflow.setdefault("tasks", {})
    workflow.setdefault("runs", {})
    task = workflow["tasks"].setdefault(
        task_id,
        {
            "taskId": task_id,
            "role": role,
            "scope": scope,
            "verification": verification,
            "runs": [],
            "status": run_status,
        },
    )
    task["role"] = role
    task["scope"] = scope
    task["verification"] = verification
    task["status"] = run_status
    if run_id not in task["runs"]:
        task["runs"].append(run_id)
    workflow["runs"][run_id] = {
        "runId": run_id,
        "taskId": task_id,
        "role": role,
        "status": run_status,
        "configPath": str(config_path),
        "statusPath": str(status_path),
        "outputPath": str(output_path),
        "promptPath": str(prompt_path),
        "rawStreamPath": str(raw_stream_path),
        "tracePath": str(trace_path),
    }
    write_json(path, workflow)
    return path
