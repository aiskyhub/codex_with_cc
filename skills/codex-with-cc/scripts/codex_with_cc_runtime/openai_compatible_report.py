from __future__ import annotations

import argparse
import json
import os
import re
import socket
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .common import ARTIFACT_SCHEMA_VERSION, CHILD_MARKER_NAME, CHILD_MARKER_VALUE, INVOCATION_CONTRACT, REPORT_HEADINGS, DelegateError, now_iso
from .io_utils import read_text, test_path_writable, write_json, write_text
from .paths import project_artifact_root, repo_root, user_artifact_root, workflow_relative_path, workflow_root
from .reports import parse_report_final_result, parse_report_role, parse_report_status, text_has_required_report_headings
from .sessions import normalize_delegate_list
from .task_contract import validate_task_file_contract
from .workflow import normalize_role, safe_task_id, update_workflow_record

RUNNER_TYPE = "openai_compatible_report"


def _load_dotenv_values(dotenv_path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not dotenv_path.exists():
        return values
    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def _env_value(name: str, dotenv: dict[str, str], default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value is not None and value.strip():
        return value.strip()
    dot = dotenv.get(name)
    if dot is not None and dot.strip():
        return dot.strip()
    return default


def _resolve_env_alias(names: list[str], dotenv: dict[str, str], default: str | None = None) -> str | None:
    for name in names:
        value = os.environ.get(name)
        if value is not None and value.strip():
            return value.strip()
    for name in names:
        value = dotenv.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def _redact_secrets(text: str, secrets: list[str | None]) -> str:
    redacted = text
    for secret in secrets:
        if secret and secret.strip():
            redacted = redacted.replace(secret.strip(), "<redacted>")
    return redacted


def _build_report_prompt(
    task_text: str,
    role: str,
    run_id: str,
    workflow_id: str,
    task_id: str,
    scope: list[str],
    tests: list[str],
) -> str:
    headings = "\n".join(REPORT_HEADINGS)
    scope_text = "\n".join(f"- {item}" for item in scope) if scope else "- None"
    tests_text = "\n".join(f"- {item}" for item in tests) if tests else "- None"
    return (
        "Produce only a workflow/process report. Do not execute shell commands, do not propose file edits, and do not claim code was changed.\n"
        "Return plain text only, with no Markdown heading markers, no bullets before headings, and no fenced code blocks.\n"
        "Each required heading must appear alone on its own line, exactly as listed below, in the same order. Status and Final Result must match.\n\n"
        f"RunId: {run_id}\nWorkflowId: {workflow_id}\nTaskId: {task_id}\nRole: {role}\n\n"
        "Scope:\n"
        f"{scope_text}\n\n"
        "Tests (informational only; do not execute):\n"
        f"{tests_text}\n\n"
        "Required report headings:\n"
        f"{headings}\n\n"
        "Allowed status values: DONE, DONE_WITH_CONCERNS, NEEDS_CONTEXT, BLOCKED, FAIL\n\n"
        "Task file content:\n"
        f"{task_text.strip()}\n"
    )


def _failure_report(role: str, message: str) -> str:
    return f"""Status
FAIL

Role
{role}

Summary
OpenAI-compatible report runner failed before producing a valid report.

Changed Files
None

Verification
- not run; report-only runner does not execute shell verification commands

Findings
- {message}

Final Result
FAIL

Risks Or Follow-ups
- Resolve configuration or API failures, then rerun.
"""


def _build_paths(artifact_root: Path, run_id: str, output_path: str | None) -> dict[str, Path]:
    output = Path(output_path).resolve() if output_path else (artifact_root / f"report_{run_id}.md").resolve()
    return {
        "output": output,
        "status": artifact_root / f"status_{run_id}.json",
        "config": artifact_root / f"config_{run_id}.json",
        "prompt": artifact_root / f"prompt_{run_id}.md",
        "stream": artifact_root / f"stream_{run_id}.jsonl",
        "trace": artifact_root / f"trace_{run_id}.log",
    }


def _ensure_artifact_root(artifact_root: Path) -> None:
    artifact_root.mkdir(parents=True, exist_ok=True)
    test_path_writable(artifact_root / ".root_write_probe")


def _resolve_artifact_root(explicit: str | None) -> tuple[Path, str | None]:
    if explicit:
        root = Path(explicit).resolve()
        _ensure_artifact_root(root)
        return root, None

    primary = project_artifact_root(repo_root())
    try:
        _ensure_artifact_root(primary)
        return primary, None
    except DelegateError as exc:
        fallback = user_artifact_root(repo_root())
        _ensure_artifact_root(fallback)
        return fallback, str(exc)


def _openai_chat_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    url = base_url.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a report generator following strict heading contracts."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
        text = response.read().decode("utf-8")
    return json.loads(text)


def _extract_report_text(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") if isinstance(response_json.get("choices"), list) else []
    if not choices:
        return ""
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def _normalize_report_heading_line(line: str) -> str | None:
    candidate = line.strip()
    candidate = re.sub(r"^#{1,6}\s+", "", candidate)
    candidate = re.sub(r"^\d+[\.)]\s+", "", candidate)
    candidate = candidate.strip().strip("`").strip()
    candidate = re.sub(r"^\*\*(.*?)\*\*$", r"\1", candidate).strip()
    candidate = re.sub(r"^__(.*?)__$", r"\1", candidate).strip()
    if candidate.endswith(":"):
        candidate = candidate[:-1].strip()
    for heading in REPORT_HEADINGS:
        if candidate.lower() == heading.lower():
            return heading
    return None


def _normalize_model_report_text(text: str) -> tuple[str, bool]:
    normalized_lines: list[str] = []
    changed = False
    for line in text.strip().splitlines():
        normalized_heading = _normalize_report_heading_line(line)
        if normalized_heading is not None:
            normalized_lines.append(normalized_heading)
            changed = changed or normalized_heading != line.strip()
            continue
        normalized_lines.append(line.rstrip())
    normalized = "\n".join(normalized_lines).strip()
    return normalized, changed


def run_openai_compatible_report_delegate(ns: argparse.Namespace) -> int:
    if os.environ.get(CHILD_MARKER_NAME) != CHILD_MARKER_VALUE:
        raise DelegateError(
            "delegate_to_openai_compatible_report may only run inside a Codex child thread. "
            f"Missing required child-thread marker '{CHILD_MARKER_NAME}={CHILD_MARKER_VALUE}'."
        )

    task_file = Path(ns.task_file)
    if not task_file.exists():
        raise DelegateError(f"Task file was not found: {task_file}")
    task_text = read_text(task_file)
    if not task_text.strip():
        raise DelegateError("Task text cannot be empty.")
    validate_task_file_contract(task_text)

    role = normalize_role(ns.role)
    if role == "reviewer" and (not ns.review_for_task_id or not ns.review_kind):
        raise DelegateError("Reviewer runs must pass -ReviewForTaskId and -ReviewKind.")

    wf_root = workflow_root()
    if not (wf_root / "CODEX_WITH_CC.md").exists():
        raise DelegateError(f"Missing workflow entry document: {wf_root / 'CODEX_WITH_CC.md'}")

    workflow_id = ns.workflow_id.strip()
    task_id = safe_task_id(ns.task_id)
    scope = normalize_delegate_list(ns.scope)
    tests = normalize_delegate_list(ns.tests)
    depends_on = [safe_task_id(item) for item in normalize_delegate_list(ns.depends_on)]

    artifact_root, fallback_reason = _resolve_artifact_root(ns.artifact_root)
    run_id = f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}_{uuid.uuid4().hex[:8]}"
    paths = _build_paths(artifact_root, run_id, ns.output_path)

    for path in paths.values():
        test_path_writable(path)

    dotenv = _load_dotenv_values(repo_root() / ".env")
    api_key = _resolve_env_alias(
        ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"],
        dotenv,
    )
    base_url = _resolve_env_alias(
        ["DEEPSEEK_BASE_URL", "DEEPSEEK_API_BASE_URL", "OPENAI_BASE_URL", "OPENAI_COMPATIBLE_BASE_URL"],
        dotenv,
        "https://api.deepseek.com",
    )
    model = _resolve_env_alias(
        ["DEEPSEEK_MODEL", "OPENAI_MODEL", "OPENAI_COMPATIBLE_MODEL"],
        dotenv,
        ns.model or "deepseek-v4-flash",
    )
    timeout_seconds = int(_env_value("OPENAI_COMPATIBLE_TIMEOUT_SECONDS", dotenv, "600") or "600")
    if not api_key:
        raise DelegateError(
            "Missing API key. Set DEEPSEEK_API_KEY, OPENAI_API_KEY, or OPENAI_COMPATIBLE_API_KEY in environment or project .env."
        )

    prompt = _build_report_prompt(task_text, role, run_id, workflow_id, task_id, scope, tests)
    write_text(paths["prompt"], prompt)

    config: dict[str, Any] = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "role": role,
        "runnerType": RUNNER_TYPE,
        "childThreadMarkerName": CHILD_MARKER_NAME,
        "childThreadMarkerValidated": True,
        "repoRoot": str(repo_root()),
        "workflowRoot": str(workflow_root()),
        "workflowRelativePath": workflow_relative_path(),
        "artifactRoot": str(artifact_root),
        "artifactRootFallbackReason": fallback_reason,
        "taskFile": str(task_file.resolve()),
        "scope": scope,
        "tests": tests,
        "dependsOn": depends_on,
        "reviewForTaskId": ns.review_for_task_id,
        "reviewKind": ns.review_kind,
        "outputPath": str(paths["output"]),
        "statusPath": str(paths["status"]),
        "promptPath": str(paths["prompt"]),
        "rawStreamPath": str(paths["stream"]),
        "tracePath": str(paths["trace"]),
        "sessionMode": ns.session_mode,
        "sessionKey": ns.session_key,
        "outputFormat": "report",
        "apiBaseUrl": base_url,
        "model": model,
        "apiKeyEnvNames": ["DEEPSEEK_API_KEY", "OPENAI_API_KEY", "OPENAI_COMPATIBLE_API_KEY"],
        "timeoutSeconds": timeout_seconds,
        "initialSessionId": "",
        "initialResume": False,
        "sessionId": "",
        "resume": False,
        "attemptCount": 1,
        "retryCount": 0,
    }

    status: dict[str, Any] = {
        "artifactSchema": ARTIFACT_SCHEMA_VERSION,
        "invocationContract": INVOCATION_CONTRACT,
        "runId": run_id,
        "workflowId": workflow_id,
        "taskId": task_id,
        "role": role,
        "runnerType": RUNNER_TYPE,
        "childThreadMarkerName": CHILD_MARKER_NAME,
        "childThreadMarkerValidated": True,
        "status": "running",
        "outputPath": str(paths["output"]),
        "statusPath": str(paths["status"]),
        "promptPath": str(paths["prompt"]),
        "rawStreamPath": str(paths["stream"]),
        "tracePath": str(paths["trace"]),
        "attemptCount": 1,
        "retryCount": 0,
    }

    write_json(paths["config"], config)
    write_json(paths["status"], status)

    report_text = ""
    exit_code = 0
    failure_summary = ""
    response_json: dict[str, Any] = {}
    normalized_headings = False

    try:
        response_json = _openai_chat_completion(
            base_url=base_url,
            api_key=api_key,
            model=model or "deepseek-v4-flash",
            prompt=prompt,
            timeout_seconds=timeout_seconds,
        )
        report_text = _extract_report_text(response_json)
        report_text, normalized_headings = _normalize_model_report_text(report_text)
        if not text_has_required_report_headings(report_text):
            raise DelegateError("Model response did not satisfy required report headings.")
        if parse_report_status(report_text) != parse_report_final_result(report_text):
            raise DelegateError("Model response has mismatched Status and Final Result.")
        if parse_report_role(report_text) != role:
            raise DelegateError(f"Model response role mismatch. Expected {role}.")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, socket.timeout, OSError, DelegateError, ValueError, json.JSONDecodeError) as exc:
        exit_code = 1
        failure_summary = _redact_secrets(str(exc), [api_key])
        report_text = _failure_report(role, failure_summary)

    write_text(paths["output"], report_text)

    usage = response_json.get("usage") if isinstance(response_json.get("usage"), dict) else {}
    stream_event = {
        "runId": run_id,
        "runnerType": RUNNER_TYPE,
        "timestamp": now_iso(),
        "model": model,
        "usage": usage,
        "status": "ok" if exit_code == 0 else "error",
        "normalizedReportHeadings": normalized_headings,
    }
    write_text(paths["stream"], json.dumps(stream_event, ensure_ascii=False) + "\n")
    write_text(paths["trace"], f"[{now_iso()}] runner={RUNNER_TYPE} status={stream_event['status']}\n")

    status.update(
        {
            "status": "completed" if exit_code == 0 else "failed",
            "exitCode": exit_code,
            "outputBytes": paths["output"].stat().st_size,
            "attempts": [
                {
                    "attempt": 1,
                    "sessionId": "",
                    "resume": False,
                    "retryReason": None,
                    "exitCode": exit_code,
                    "sawAssistantText": True,
                    "sawResultSuccess": exit_code == 0,
                    "capturedFinalResult": True,
                    "runnerType": RUNNER_TYPE,
                }
            ],
        }
    )
    if exit_code != 0:
        status["failureDisposition"] = "NEED_HUMAN_INTERVENTION"
        status["failureSummary"] = failure_summary
        status["maxRetryCount"] = 0
        config["failureDisposition"] = "NEED_HUMAN_INTERVENTION"
        config["failureSummary"] = failure_summary
        config["maxRetryCount"] = 0

    write_json(paths["config"], config)
    write_json(paths["status"], status)

    update_workflow_record(
        artifact_root,
        workflow_id=workflow_id,
        task_id=task_id,
        role=role,
        scope=scope,
        verification=tests,
        depends_on=depends_on,
        run_id=run_id,
        config_path=paths["config"],
        status_path=paths["status"],
        output_path=paths["output"],
        prompt_path=paths["prompt"],
        raw_stream_path=paths["stream"],
        trace_path=paths["trace"],
        run_status=status["status"],
        review_for_task_id=ns.review_for_task_id,
        review_kind=ns.review_kind,
        runner_type=RUNNER_TYPE,
    )

    print(f"RunId: {run_id}")
    print(f"Output: {paths['output']}")
    print(f"Status: {paths['status']}")
    return exit_code
