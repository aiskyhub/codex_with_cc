from __future__ import annotations

import argparse
import sys
from typing import Callable

from .artifacts import run_verify_artifacts, run_verify_chain, run_verify_workflow
from .common import DelegateError, WORKER_ROLES
from .delegate import run_delegate
from .openai_compatible_report import run_openai_compatible_report_delegate
from .real_chain import run_real_chain_validation
from .selftests import run_test_runtime, run_test_session_pool
from .task_contract import run_validate_task
from .ccviz_parser import list_workflows, get_workflow_details
from .ccviz_renderer import render_list, render_show, render_audit



def choice_arg(choices: list[str]) -> Callable[[str], str]:
    lookup = {choice.lower(): choice for choice in choices}

    def parse(value: str) -> str:
        selected = lookup.get(value.lower())
        if selected is None:
            expected = ", ".join(choices)
            raise argparse.ArgumentTypeError(f"invalid choice: {value!r} (choose from {expected})")
        return selected

    return parse



def int_range_arg(name: str, minimum: int, maximum: int) -> Callable[[str], int]:
    def parse(value: str) -> int:
        try:
            parsed = int(value)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc
        if parsed < minimum or parsed > maximum:
            raise argparse.ArgumentTypeError(f"{name} must be between {minimum} and {maximum}")
        return parsed

    return parse



def add_delegate_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-TaskFile", dest="task_file", required=True)
    parser.add_argument("-Scope", dest="scope", action="append", default=[])
    parser.add_argument("-Tests", dest="tests", action="append", default=[])
    parser.add_argument("-WorkflowId", dest="workflow_id", required=True)
    parser.add_argument("-TaskId", dest="task_id", required=True)
    parser.add_argument("-Role", dest="role", type=choice_arg(list(WORKER_ROLES)), required=True)
    parser.add_argument("-ReviewForTaskId", dest="review_for_task_id")
    parser.add_argument("-ReviewKind", dest="review_kind", type=choice_arg(["spec", "quality"]))
    parser.add_argument("-DependsOn", dest="depends_on", action="append", default=[])
    parser.add_argument("-Model", dest="model", default="sonnet")
    parser.add_argument("-Name", dest="name")
    parser.add_argument("-NamePrefix", dest="name_prefix", default="codex-delegate")
    parser.add_argument("-MaxBudgetUsd", dest="max_budget_usd")
    parser.add_argument("-ArtifactRoot", dest="artifact_root")
    parser.add_argument("-OutputPath", dest="output_path")
    parser.add_argument("-AllowParallel", dest="allow_parallel", action="store_true")
    parser.add_argument("-SessionMode", dest="session_mode", type=choice_arg(["PrimaryReuse", "PrimaryAnchor", "ParallelPool"]), default="PrimaryReuse")
    parser.add_argument("-SessionKey", dest="session_key", required=True)
    parser.add_argument("-SessionLeaseTimeoutSeconds", dest="session_lease_timeout_seconds", type=int, default=21600)
    parser.add_argument("-SessionLeaseWaitSeconds", dest="session_lease_wait_seconds", type=int, default=120)
    parser.add_argument("-ResetPrimarySession", dest="reset_primary_session", action="store_true")
    parser.add_argument("-ResetParallelPool", dest="reset_parallel_pool", action="store_true")
    parser.add_argument("-LockTimeoutSeconds", dest="lock_timeout_seconds", type=int, default=120)
    parser.add_argument("-LockPollMilliseconds", dest="lock_poll_milliseconds", type=int, default=500)
    parser.add_argument("-MaxRetryCount", dest="max_retry_count", type=int_range_arg("MaxRetryCount", 0, 100), default=5)
    parser.add_argument("-BypassPermissions", dest="bypass_permissions", action="store_true")
    parser.add_argument("-DryRun", dest="dry_run", action="store_true")


def add_validate_task_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-TaskFile", dest="task_file", required=True)
    parser.add_argument("-Role", dest="role", type=choice_arg(list(WORKER_ROLES)), required=True)
    parser.add_argument("-ReviewForTaskId", dest="review_for_task_id")
    parser.add_argument("-ReviewKind", dest="review_kind", type=choice_arg(["spec", "quality"]))
    parser.add_argument("-Tests", dest="tests", action="append", default=[])



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex_with_cc scripts", allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    delegate = sub.add_parser("delegate", allow_abbrev=False)
    add_delegate_args(delegate)
    delegate.set_defaults(func=run_delegate)

    report = sub.add_parser("openai-compatible-report", allow_abbrev=False)
    add_delegate_args(report)
    report.set_defaults(func=run_openai_compatible_report_delegate, model="deepseek-v4-flash")

    validate_task = sub.add_parser("validate-task", allow_abbrev=False)
    add_validate_task_args(validate_task)
    validate_task.set_defaults(func=run_validate_task)

    verify = sub.add_parser("verify-artifacts", allow_abbrev=False)
    verify.add_argument("-RunId", dest="run_id", required=True)
    verify.add_argument("-ArtifactRoot", dest="artifact_root")
    verify.set_defaults(func=run_verify_artifacts)

    verify_run = sub.add_parser("verify-run", allow_abbrev=False)
    verify_run.add_argument("-RunId", dest="run_id", required=True)
    verify_run.add_argument("-ArtifactRoot", dest="artifact_root")
    verify_run.set_defaults(func=run_verify_artifacts)

    workflow = sub.add_parser("verify-workflow", allow_abbrev=False)
    workflow.add_argument("-WorkflowId", dest="workflow_id", required=True)
    workflow.add_argument("-ArtifactRoot", dest="artifact_root")
    workflow.set_defaults(func=run_verify_workflow)

    chain = sub.add_parser("verify-chain", allow_abbrev=False)
    chain.add_argument("-ArtifactRoot", dest="artifact_root", required=True)
    chain.add_argument("-SessionKey", dest="session_key", required=True)
    chain.add_argument("-AnchorRunId", dest="anchor_run_id", required=True)
    chain.add_argument("-ParallelRunIds", dest="parallel_run_ids", nargs="+", required=True)
    chain.add_argument("-ReuseRunIds", dest="reuse_run_ids", nargs="+", required=True)
    chain.set_defaults(func=run_verify_chain)

    validation = sub.add_parser("run-real-chain-validation", allow_abbrev=False)
    validation.add_argument("-ValidationRoot", dest="validation_root")
    validation.add_argument("-Name", dest="name")
    validation.add_argument("-SessionKey", dest="session_key")
    validation.set_defaults(func=run_real_chain_validation)

    sub.add_parser("test-runtime").set_defaults(func=run_test_runtime)
    sub.add_parser("test-session-pool").set_defaults(func=run_test_session_pool)

    # ccviz subcommands
    ccviz = sub.add_parser("ccviz", allow_abbrev=False)
    ccviz_sub = ccviz.add_subparsers(dest="ccviz_command", required=True)
    
    ccviz_list = ccviz_sub.add_parser("list", allow_abbrev=False)
    ccviz_list.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_list.set_defaults(func=run_ccviz_list)
    
    ccviz_show = ccviz_sub.add_parser("show", allow_abbrev=False)
    ccviz_show.add_argument("workflow_id")
    ccviz_show.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_show.set_defaults(func=run_ccviz_show)
    
    ccviz_audit = ccviz_sub.add_parser("audit", allow_abbrev=False)
    ccviz_audit.add_argument("workflow_id")
    ccviz_audit.add_argument("-ArtifactRoot", dest="artifact_root")
    ccviz_audit.set_defaults(func=run_ccviz_audit)

    return parser


def run_ccviz_list(ns: argparse.Namespace) -> int:
    workflows = list_workflows(ns.artifact_root)
    render_list(workflows)
    return 0


def run_ccviz_show(ns: argparse.Namespace) -> int:
    wf = get_workflow_details(ns.workflow_id, ns.artifact_root)
    if not wf:
        print(f"\033[91mError: Workflow '{ns.workflow_id}' not found.\033[0m", file=sys.stderr)
        return 1
    render_show(wf)
    return 0


def run_ccviz_audit(ns: argparse.Namespace) -> int:
    wf = get_workflow_details(ns.workflow_id, ns.artifact_root)
    if not wf:
        print(f"\033[91mError: Workflow '{ns.workflow_id}' not found.\033[0m", file=sys.stderr)
        return 1
    render_audit(wf)
    return 0



def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    ns = parser.parse_args(argv)
    try:
        return int(ns.func(ns))
    except DelegateError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        return 130
