from __future__ import annotations

import json
import re
import os
from pathlib import Path
from typing import Any

from .common import WORKER_ROLES, REPORT_STATUS_VALUES
from .io_utils import load_json, read_text
from .paths import project_artifact_root, user_artifact_root
from .workflow import workflow_path
from .reports import report_section, parse_report_status, parse_report_final_result, parse_report_role, report_summary_line

# Cost definitions per 1,000,000 tokens
MODEL_COSTS = {
    "deepseek-v4-pro": {"prompt": 0.14, "completion": 0.28},
    "deepseek-v4-flash": {"prompt": 0.08, "completion": 0.16},
    "deepseek-chat": {"prompt": 0.14, "completion": 0.28},
    "claude-3-5-sonnet": {"prompt": 3.0, "completion": 15.0},
    "claude-3.5-sonnet": {"prompt": 3.0, "completion": 15.0},
    "sonnet": {"prompt": 3.0, "completion": 15.0},
    "default": {"prompt": 0.50, "completion": 1.50}
}

def resolve_all_artifact_roots(explicit_root: str | None = None) -> list[Path]:
    roots = []
    if explicit_root:
        roots.append(Path(explicit_root).resolve())
    else:
        # Check project root and user root
        p_root = project_artifact_root()
        if p_root.exists():
            roots.append(p_root)
        u_root = user_artifact_root()
        if u_root.exists():
            roots.append(u_root)
    # Ensure they are unique
    unique_roots = []
    for r in roots:
        if r not in unique_roots:
            unique_roots.append(r)
    return unique_roots

def list_workflows(artifact_root_value: str | None = None) -> list[dict[str, Any]]:
    roots = resolve_all_artifact_roots(artifact_root_value)
    workflows = []
    
    for root in roots:
        for file in root.glob("workflow_*.json"):
            try:
                data = load_json(file)
                if not isinstance(data, dict) or "workflowId" not in data:
                    continue
                
                wf_id = data["workflowId"]
                tasks = data.get("tasks", {})
                runs = data.get("runs", {})
                
                total_tasks = len(tasks)
                completed_tasks = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("status") == "completed")
                failed_tasks = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("status") == "failed")
                running_tasks = sum(1 for t in tasks.values() if isinstance(t, dict) and t.get("status") == "running")
                
                # Calculate aggregate metrics
                total_tokens = 0
                total_cost_usd = 0.0
                min_start = None
                max_end = None
                
                for run_id, run_meta in runs.items():
                    # Parse stream for usage
                    stream_path = root / f"stream_{run_id}.jsonl"
                    usage = {}
                    model = "unknown"
                    if stream_path.exists():
                        try:
                            # Stream file usually has 1 line or a few lines
                            for line in stream_path.read_text(encoding="utf-8").splitlines():
                                if not line.strip():
                                    continue
                                line_data = json.loads(line)
                                if "usage" in line_data:
                                    usage = line_data["usage"]
                                if "model" in line_data:
                                    model = line_data["model"]
                        except Exception:
                            pass
                    
                    if not usage and isinstance(run_meta, dict):
                        # Try to get output or estimate
                        pass
                        
                    if usage:
                        prompt_tokens = usage.get("prompt_tokens", 0)
                        completion_tokens = usage.get("completion_tokens", 0)
                        total_tokens += usage.get("total_tokens", prompt_tokens + completion_tokens)
                        
                        # Calculate cost
                        cost_meta = MODEL_COSTS.get(model.lower()) or MODEL_COSTS.get("default")
                        for k, v in MODEL_COSTS.items():
                            if k in model.lower():
                                cost_meta = v
                                break
                        total_cost_usd += (prompt_tokens * cost_meta["prompt"] + completion_tokens * cost_meta["completion"]) / 1_000_000.0

                workflows.append({
                    "workflowId": wf_id,
                    "createdAt": data.get("createdAt"),
                    "updatedAt": data.get("updatedAt"),
                    "status": "completed" if data.get("finalAcceptance", {}).get("status") == "accepted" else "running",
                    "totalTasks": total_tasks,
                    "completedTasks": completed_tasks,
                    "failedTasks": failed_tasks,
                    "runningTasks": running_tasks,
                    "totalTokens": total_tokens,
                    "totalCostUsd": total_cost_usd,
                    "finalAcceptance": data.get("finalAcceptance", {}),
                    "artifactRoot": str(root)
                })
            except Exception:
                pass
                
    workflows.sort(key=lambda x: x.get("updatedAt", "") or "", reverse=True)
    return workflows

def get_workflow_details(workflow_id: str, artifact_root_value: str | None = None) -> dict[str, Any] | None:
    roots = resolve_all_artifact_roots(artifact_root_value)
    
    for root in roots:
        file = workflow_path(root, workflow_id)
        if file.exists():
            try:
                workflow = load_json(file)
                # Supplement runs with stream and report info
                runs = workflow.setdefault("runs", {})
                for run_id, run_meta in list(runs.items()):
                    if not isinstance(run_meta, dict):
                        continue
                    
                    # Resolve absolute paths if relative
                    for path_key in ("configPath", "statusPath", "outputPath", "promptPath", "rawStreamPath", "tracePath"):
                        if run_meta.get(path_key):
                            p = Path(run_meta[path_key])
                            if not p.is_absolute():
                                run_meta[path_key] = str((root / p.name).resolve())
                    
                    # 1. Parse Status JSON
                    status_path = Path(run_meta.get("statusPath") or (root / f"status_{run_id}.json"))
                    exit_code = None
                    attempt_count = 1
                    retry_count = 0
                    attempts = []
                    if status_path.exists():
                        try:
                            status_data = load_json(status_path)
                            exit_code = status_data.get("exitCode")
                            attempt_count = status_data.get("attemptCount", 1)
                            retry_count = status_data.get("retryCount", 0)
                            attempts = status_data.get("attempts", [])
                            # Supplement running status with PID check
                            if status_data.get("status") == "running" and attempts:
                                final_att = attempts[-1]
                                pid = final_att.get("pid")
                                # If we have pid in attempt (we can add it if needed), we check it
                                # For now, check if PID exists on host if recorded
                        except Exception:
                            pass
                            
                    run_meta["exitCode"] = exit_code
                    run_meta["attemptCount"] = attempt_count
                    run_meta["retryCount"] = retry_count
                    run_meta["attempts"] = attempts
                    
                    # 2. Parse Config JSON
                    config_path = Path(run_meta.get("configPath") or (root / f"config_{run_id}.json"))
                    tests = []
                    session_mode = "PrimaryReuse"
                    session_key = ""
                    if config_path.exists():
                        try:
                            config_data = load_json(config_path)
                            tests = config_data.get("tests", [])
                            session_mode = config_data.get("sessionMode", "PrimaryReuse")
                            session_key = config_data.get("sessionKey", "")
                        except Exception:
                            pass
                    run_meta["tests"] = tests
                    run_meta["sessionMode"] = session_mode
                    run_meta["sessionKey"] = session_key

                    # 3. Parse Stream JSONL
                    stream_path = Path(run_meta.get("rawStreamPath") or (root / f"stream_{run_id}.jsonl"))
                    tokens = {"prompt": 0, "completion": 0, "reasoning": 0, "total": 0}
                    model = "unknown"
                    mcp_invocations = 0
                    generic_search_violations = 0
                    
                    if stream_path.exists():
                        try:
                            for line in stream_path.read_text(encoding="utf-8").splitlines():
                                if not line.strip():
                                    continue
                                line_data = json.loads(line)
                                if "usage" in line_data:
                                    usage = line_data["usage"]
                                    tokens["prompt"] += usage.get("prompt_tokens", 0)
                                    tokens["completion"] += usage.get("completion_tokens", 0)
                                    tokens["total"] += usage.get("total_tokens", tokens["prompt"] + tokens["completion"])
                                    if "completion_tokens_details" in usage:
                                        tokens["reasoning"] += usage["completion_tokens_details"].get("reasoning_tokens", 0)
                                if "model" in line_data:
                                    model = line_data["model"]
                                # Search for tool calls / MCP invocations in the stream lines
                                # (e.g. if the CLI logged its tool uses inside JSONL events)
                                line_str = line.lower()
                                if "minimax" in line_str or "coding-plan-search" in line_str:
                                    mcp_invocations += 1
                                elif any(x in line_str for x in ("search_web", "web_search", "google_search", "read_url", "read_browser_page")):
                                    generic_search_violations += 1
                        except Exception:
                            pass
                            
                    # Cost calculation
                    cost_meta = MODEL_COSTS.get(model.lower()) or MODEL_COSTS.get("default")
                    for k, v in MODEL_COSTS.items():
                        if k in model.lower():
                            cost_meta = v
                            break
                    cost_usd = (tokens["prompt"] * cost_meta["prompt"] + tokens["completion"] * cost_meta["completion"]) / 1_000_000.0
                    
                    run_meta["tokens"] = tokens
                    run_meta["model"] = model
                    run_meta["costUsd"] = cost_usd
                    run_meta["mcpInvocations"] = mcp_invocations
                    run_meta["genericSearchViolations"] = generic_search_violations

                    # 4. Parse MD Report
                    output_path = Path(run_meta.get("outputPath") or (root / f"claude_{run_id}.md"))
                    report_details = {}
                    if output_path.exists():
                        try:
                            content = output_path.read_text(encoding="utf-8")
                            report_details = {
                                "status": parse_report_status(content),
                                "role": parse_report_role(content),
                                "summary": report_summary_line(content),
                                "changed_files": report_section(content, "Changed Files"),
                                "verification": report_section(content, "Verification"),
                                "findings": report_section(content, "Findings"),
                                "risks_or_followups": report_section(content, "Risks Or Follow-ups")
                            }
                            # Check for tools inside markdown findings/verification as well
                            verif_lower = report_details["verification"].lower()
                            find_lower = report_details["findings"].lower()
                            if "minimax" in verif_lower or "minimax" in find_lower:
                                run_meta["mcpInvocations"] += 1
                            if any(x in verif_lower or x in find_lower for x in ("search_web", "web_search", "google_search", "read_url", "read_browser_page")):
                                # Avoid double counting, only count if it wasn't captured in stream
                                if run_meta["genericSearchViolations"] == 0:
                                    run_meta["genericSearchViolations"] = 1
                        except Exception:
                            pass
                    run_meta["reportDetails"] = report_details

                return workflow
            except Exception:
                pass
    return None
