from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# ANSI codes
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
RESET = "\033[0m"
DIM = "\033[2m"

def is_pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False

def format_time(iso_str: str | None) -> str:
    if not iso_str:
        return "N/A"
    try:
        # e.g., 2026-06-01T14:32:13.912334+08:00
        dt = datetime.fromisoformat(iso_str)
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:16].replace("T", " ")

def color_status(status: str) -> str:
    status_upper = status.upper()
    if status_upper in ("COMPLETED", "ACCEPTED", "DONE"):
        return f"{GREEN}{status}{RESET}"
    elif status_upper in ("FAILED", "REJECTED", "FAIL"):
        return f"{RED}{status}{RESET}"
    elif status_upper in ("RUNNING", "STARTING", "PENDING-REVIEW", "NEEDS-REVIEW", "DONE_WITH_CONCERNS"):
        return f"{YELLOW}{status}{RESET}"
    return status

def render_list(workflows: list[dict[str, Any]]) -> None:
    if not workflows:
        print(f"{YELLOW}No workflows found in any artifact roots.{RESET}")
        return

    print(f"\n{BOLD}{CYAN}=== codex-with-cc Workflows ==={RESET}")
    
    # Define columns
    col_wf = "Workflow ID"
    col_created = "Created At"
    col_tasks = "Tasks (C/F/R/T)"
    col_status = "Status"
    col_tokens = "Tokens"
    col_cost = "Cost (USD)"
    
    # Calculate widths
    w_wf = max(len(col_wf), max(len(w["workflowId"]) for w in workflows))
    w_created = 16
    w_tasks = 15
    w_status = 12  # raw length (without ANSI)
    w_tokens = 10
    w_cost = 10

    # Header border
    border = f"┌{'─'*(w_wf+2)}┬{'─'*(w_created+2)}┬{'─'*(w_tasks+2)}┬{'─'*(w_status+2)}┬{'─'*(w_tokens+2)}┬{'─'*(w_cost+2)}┐"
    header = f"│ {BOLD}{col_wf:<{w_wf}}{RESET} │ {BOLD}{col_created:<{w_created}}{RESET} │ {BOLD}{col_tasks:<{w_tasks}}{RESET} │ {BOLD}{col_status:<{w_status}}{RESET} │ {BOLD}{col_tokens:<{w_tokens}}{RESET} │ {BOLD}{col_cost:<{w_cost}}{RESET} │"
    divider = f"├{'─'*(w_wf+2)}┼{'─'*(w_created+2)}┼{'─'*(w_tasks+2)}┼{'─'*(w_status+2)}┼{'─'*(w_tokens+2)}┼{'─'*(w_cost+2)}┤"
    footer = f"└{'─'*(w_wf+2)}┴{'─'*(w_created+2)}┴{'─'*(w_tasks+2)}┴{'─'*(w_status+2)}┴{'─'*(w_tokens+2)}┴{'─'*(w_cost+2)}┘"

    print(border)
    print(header)
    print(divider)

    for w in workflows:
        wf_id = w["workflowId"]
        created = format_time(w["createdAt"])
        
        # Tasks counts
        c = w["completedTasks"]
        f = w["failedTasks"]
        r = w["runningTasks"]
        t = w["totalTasks"]
        tasks_str = f"{c}/{f}/{r}/{t}"
        
        # Status
        status_val = w["status"].upper()
        if f > 0:
            status_str = f"{RED}FAILED{RESET}"
        elif r > 0:
            status_str = f"{YELLOW}RUNNING{RESET}"
        elif status_val == "COMPLETED":
            status_str = f"{GREEN}COMPLETED{RESET}"
        else:
            status_str = color_status(w["status"])
            
        tokens = f"{w['totalTokens']:,}"
        cost = f"${w['totalCostUsd']:.4f}"
        
        # Prepare status with raw padding since ANSI increases length
        status_padding = " " * (w_status - len(w["status"]))
        print(f"│ {wf_id:<{w_wf}} │ {created:<{w_created}} │ {tasks_str:<{w_tasks}} │ {status_str}{status_padding} │ {tokens:<{w_tokens}} │ {cost:<{w_cost}} │")

    print(footer)
    print(f"{DIM}Found {len(workflows)} workflow(s) across project/user artifact directories.{RESET}\n")

def render_show(workflow: dict[str, Any]) -> None:
    wf_id = workflow["workflowId"]
    created = format_time(workflow.get("createdAt"))
    updated = format_time(workflow.get("updatedAt"))
    final_acc = workflow.get("finalAcceptance") or {}
    
    # Calculate status
    status = "RUNNING"
    if final_acc.get("status") == "accepted":
        status = "COMPLETED"
    
    print(f"\n{BOLD}{CYAN}=== Workflow: {wf_id} ==={RESET}")
    print(f"{BOLD}Status:{RESET} {color_status(status)}")
    print(f"{BOLD}Created:{RESET} {created} | {BOLD}Updated:{RESET} {updated}")
    if final_acc:
        print(f"{BOLD}Final Acceptance:{RESET} {color_status(final_acc.get('status', ''))} ({final_acc.get('reason') or 'Review done'})")
    print(f"{BOLD}Artifact Root:{RESET} {DIM}{workflow.get('artifactRoot', '')}{RESET}")
    
    tasks = workflow.get("tasks", {})
    
    # Build dependency map
    parents = {}
    children = {}
    for task_id, t_data in tasks.items():
        children[task_id] = []
        parents[task_id] = t_data.get("dependsOn", [])
        
    for task_id, deps in parents.items():
        for dep in deps:
            if dep in children:
                children[dep].append(task_id)
                
    roots = [t_id for t_id in tasks if not parents[t_id]]
    
    print(f"\n{BOLD}Dependency Tree:{RESET}")
    
    def print_tree(t_id: str, indent: str = "", is_last: bool = True) -> None:
        t_data = tasks.get(t_id) or {}
        role = t_data.get("role", "unknown")
        task_status = t_data.get("status", "unknown")
        report_status = t_data.get("lastReportStatus") or "N/A"
        
        marker = "└─" if is_last else "├─"
        bullet = f"{GREEN}●{RESET}" if task_status == "completed" else (f"{RED}✖{RESET}" if task_status == "failed" else f"{YELLOW}○{RESET}")
        
        print(f"{indent}{marker} {bullet} {BOLD}{t_id}{RESET} [{DIM}{role}{RESET}] (Report: {color_status(report_status)})")
        
        child_ids = children.get(t_id, [])
        new_indent = indent + ("   " if is_last else "│  ")
        for i, c_id in enumerate(child_ids):
            print_tree(c_id, new_indent, i == len(child_ids) - 1)

    for i, root_id in enumerate(roots):
        print_tree(root_id, "", i == len(roots) - 1)

    print(f"\n{BOLD}Task List & Review Gates:{RESET}")
    
    # Task list table
    col_task = "Task ID"
    col_role = "Role"
    col_status = "Run Status"
    col_report = "Report Status"
    col_spec = "Spec Gate"
    col_quality = "Quality Gate"
    
    w_task = max(len(col_task), max(len(t_id) for t_id in tasks) if tasks else 0)
    w_role = 15
    w_status = 12
    w_report = 15
    w_spec = 10
    w_quality = 12

    border = f"┌{'─'*(w_task+2)}┬{'─'*(w_role+2)}┬{'─'*(w_status+2)}┬{'─'*(w_report+2)}┬{'─'*(w_spec+2)}┬{'─'*(w_quality+2)}┐"
    header = f"│ {BOLD}{col_task:<{w_task}}{RESET} │ {BOLD}{col_role:<{w_role}}{RESET} │ {BOLD}{col_status:<{w_status}}{RESET} │ {BOLD}{col_report:<{w_report}}{RESET} │ {BOLD}{col_spec:<{w_spec}}{RESET} │ {BOLD}{col_quality:<{w_quality}}{RESET} │"
    divider = f"├{'─'*(w_task+2)}┼{'─'*(w_role+2)}┼{'─'*(w_status+2)}┼{'─'*(w_report+2)}┼{'─'*(w_spec+2)}┼{'─'*(w_quality+2)}┤"
    footer = f"└{'─'*(w_task+2)}┴{'─'*(w_role+2)}┴{'─'*(w_status+2)}┴{'─'*(w_report+2)}┴{'─'*(w_spec+2)}┴{'─'*(w_quality+2)}┘"

    print(border)
    print(header)
    print(divider)

    for t_id, t in tasks.items():
        role = t.get("role", "unknown")
        r_status = t.get("status", "unknown")
        rep_status = t.get("lastReportStatus") or "N/A"
        
        # Review decisions
        spec_str = "-"
        qual_str = "-"
        
        if role == "implementer":
            reviews = t.get("reviews", {})
            
            def get_gate_char(kind: str) -> str:
                rev = reviews.get(kind)
                if not isinstance(rev, dict):
                    return f"{YELLOW}○ Pending{RESET}"
                dec = rev.get("reviewDecision")
                if dec == "accepted":
                    return f"{GREEN}● Approved{RESET}"
                elif dec == "rejected":
                    return f"{RED}✖ Rejected{RESET}"
                return f"{YELLOW}○ Needs Review{RESET}"
                
            spec_str = get_gate_char("spec")
            qual_str = get_gate_char("quality")

        # Color run status
        r_status_colored = color_status(r_status)
        r_status_pad = " " * (w_status - len(r_status))
        
        # Color report status
        rep_status_colored = color_status(rep_status)
        rep_status_pad = " " * (w_report - len(rep_status))
        
        # Handle ANSI padding for spec/quality
        spec_clean_len = len(spec_str.replace(GREEN, "").replace(RED, "").replace(YELLOW, "").replace(RESET, ""))
        spec_pad = " " * (w_spec - spec_clean_len)
        
        qual_clean_len = len(qual_str.replace(GREEN, "").replace(RED, "").replace(YELLOW, "").replace(RESET, ""))
        qual_pad = " " * (w_quality - qual_clean_len)

        print(f"│ {t_id:<{w_task}} │ {role:<{w_role}} │ {r_status_colored}{r_status_pad} │ {rep_status_colored}{rep_status_pad} │ {spec_str}{spec_pad} │ {qual_str}{qual_pad} │")

    print(footer)
    print(f"{DIM}* Gate Legends: ● Approved, ○ Pending, ✖ Rejected, - N/A{RESET}\n")

def render_audit(workflow: dict[str, Any]) -> None:
    wf_id = workflow["workflowId"]
    print(f"\n{BOLD}{CYAN}================================================================================{RESET}")
    print(f"{BOLD}{CYAN}FORENSIC AUDIT REPORT FOR WORKFLOW: {wf_id}{RESET}")
    print(f"{BOLD}{CYAN}================================================================================{RESET}")

    tasks = workflow.get("tasks", {})
    runs = workflow.get("runs", {})
    
    audit_passed = True
    warnings = []
    successes = []

    # 1. Check Artifact Schema
    schema = workflow.get("artifactSchema")
    if schema == 3:
        successes.append("Contract Schema: Version 3 validated.")
    else:
        warnings.append(f"Contract Schema: Invalid schema version {schema}. Expected 3.")
        audit_passed = False

    # 1.5 Check Task Failures
    failed_tasks = [t_id for t_id, t in tasks.items() if isinstance(t, dict) and t.get("status") == "failed"]
    if failed_tasks:
        for t_id in failed_tasks:
            warnings.append(f"Task Failure: Task {t_id} status is failed.")
        audit_passed = False
    else:
        successes.append("Task Failures: No failed tasks detected.")

    # 2. Check Roles Chain & Final Verifier Compliance
    has_implementer = any(t.get("role") == "implementer" for t in tasks.values())
    if has_implementer:
        has_verifier = any(t.get("role") == "final-verifier" for t in tasks.values())
        if has_verifier:
            verifier_completed = any(t.get("role") == "final-verifier" and t.get("status") == "completed" and t.get("lastReportStatus") == "DONE" for t in tasks.values())
            if verifier_completed:
                successes.append("Verifier Compliance: final-verifier task executed and accepted.")
            else:
                warnings.append("Verifier Compliance: final-verifier task exists but is not completed or report is not DONE.")
                audit_passed = False
        else:
            warnings.append("Verifier Compliance: Workflow has implementer tasks but is missing a final-verifier task.")
            audit_passed = False
    else:
        successes.append("Verifier Compliance: No implementer tasks; final-verifier not required.")

    # 3. Check Review Gates for Implementers
    review_issues = []
    for t_id, t in tasks.items():
        if t.get("role") == "implementer":
            reviews = t.get("reviews", {})
            for kind in ("spec", "quality"):
                rev = reviews.get(kind)
                if not isinstance(rev, dict):
                    review_issues.append(f"Task {t_id} is missing {kind} review gate.")
                elif rev.get("reviewDecision") != "accepted":
                    review_issues.append(f"Task {t_id} review gate {kind} status is {rev.get('reviewDecision')}.")
                    
    if not review_issues:
        successes.append("Review Gates: All implementer tasks have accepted spec & quality review gates.")
    else:
        for issue in review_issues:
            warnings.append(f"Review Gates: {issue}")
        audit_passed = False

    # 4. Check Exit Codes, Stream usage, and Stale PIDs
    stale_runs = 0
    total_tokens = 0
    total_cost = 0.0
    mcp_searches = 0
    generic_searches = 0

    for run_id, run in runs.items():
        total_tokens += run.get("tokens", {}).get("total", 0)
        total_cost += run.get("costUsd", 0.0)
        mcp_searches += run.get("mcpInvocations", 0)
        generic_searches += run.get("genericSearchViolations", 0)

        # Check exit codes
        exit_code = run.get("exitCode")
        status = run.get("status")
        rep_status = run.get("reportStatus")
        rep_final = run.get("reportFinalResult")
        
        if status == "completed" and exit_code is not None and exit_code != 0:
            warnings.append(f"Run {run_id}: Status is completed but exitCode is non-zero ({exit_code}).")
            audit_passed = False
        elif status == "failed" and exit_code == 0:
            warnings.append(f"Run {run_id}: Status is failed but exitCode is 0.")
            audit_passed = False

        # Status and Final Result consistency
        if rep_status and rep_final and rep_status != rep_final:
            warnings.append(f"Run {run_id}: Report status ('{rep_status}') and Final Result ('{rep_final}') mismatch.")
            audit_passed = False

        # Stale Process check
        if status == "running":
            attempts = run.get("attempts", [])
            if attempts:
                pid = attempts[-1].get("pid")
                if pid and not is_pid_running(pid):
                    warnings.append(f"Run {run_id}: Stale process detected! PID {pid} is dead but status is still running.")
                    stale_runs += 1
                    audit_passed = False

        # Verification Evidence check
        if rep_status == "DONE" and run.get("role") in ("implementer", "reviewer"):
            # Check verification text
            rep_details = run.get("reportDetails", {})
            verif_text = rep_details.get("verification", "").strip().lower()
            if not verif_text or any(x in verif_text for x in ("not run", "none", "- none", "placeholder")):
                warnings.append(f"Run {run_id}: Completed with DONE but report contains no valid verification evidence.")
                audit_passed = False

    if stale_runs == 0:
        successes.append("Process Check: No stale running tasks detected.")

    # 5. Network Audit (Minimax MCP vs Generic Web Search)
    network_line = f"Network Audit: Total Token Cost: {total_tokens:,} tokens (${total_cost:.4f}). Minimax MCP Search calls: {mcp_searches}."
    if generic_searches > 0:
        warnings.append(f"Network Audit: DETECTED {generic_searches} VIOLATIONS of generic web search / URL fetching instead of Minimax MCP!")
        audit_passed = False
    else:
        successes.append(f"{network_line} Generic Web Search Violations: 0.")

    # Print Results
    print(f"\n{BOLD}Audit Successes:{RESET}")
    for success in successes:
        print(f"  {GREEN}[✓]{RESET} {success}")

    if warnings:
        print(f"\n{BOLD}{RED}Audit Failures / Warnings:{RESET}")
        for warning in warnings:
            print(f"  {RED}[✖]{RESET} {warning}")

    print(f"\n{BOLD}{CYAN}================================================================================{RESET}")
    if audit_passed:
        print(f"{BOLD}{GREEN}AUDIT RESULT: TRUSTED & APPROVED{RESET}")
    else:
        print(f"{BOLD}{RED}AUDIT RESULT: UNTRUSTED / REJECTED{RESET}")
    print(f"{BOLD}{CYAN}================================================================================{RESET}\n")
