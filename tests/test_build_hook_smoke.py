#!/usr/bin/env python3
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys


REPO = Path(__file__).resolve().parents[1]
BUILD_ROOT = REPO / "build"
SMOKE_ROOT = BUILD_ROOT / "codex-with-cc-hook-smoke"


def reset_smoke_project() -> tuple[Path, Path, Path]:
    build_root = BUILD_ROOT.resolve()
    smoke_root = SMOKE_ROOT.resolve()
    if not smoke_root.is_relative_to(build_root):
        raise AssertionError(f"Refusing to reset smoke project outside build: {smoke_root}")

    if smoke_root.exists():
        shutil.rmtree(smoke_root)

    plugin_root = smoke_root / "installed-plugin"
    project_root = smoke_root / "project"
    workflow_root = plugin_root / "skills" / "codex-with-cc"
    plugin_root.mkdir(parents=True)
    project_root.mkdir(parents=True)

    shutil.copytree(REPO / ".codex-plugin", plugin_root / ".codex-plugin")
    shutil.copytree(REPO / "hooks", plugin_root / "hooks")
    shutil.copytree(
        REPO / "skills",
        plugin_root / "skills",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (project_root / "AGENTS.md").write_text(
        "# Smoke Project\n\nAny 子代理 task here must route through codex-with-cc.\n",
        encoding="utf-8",
    )
    return plugin_root, workflow_root, project_root


def hooks_config(plugin_root: Path) -> dict:
    manifest = json.loads((plugin_root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
    hooks_path = plugin_root / manifest["hooks"].removeprefix("./")
    return json.loads(hooks_path.read_text(encoding="utf-8"))


def run_hook(plugin_root: Path, project_root: Path, config: dict, event_name: str, payload: dict) -> dict:
    command = config["hooks"][event_name][0]["hooks"][0]["command"]
    command = command.replace("${CLAUDE_PLUGIN_ROOT}", plugin_root.as_posix())
    result = subprocess.run(
        command,
        input=json.dumps(payload, ensure_ascii=False),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=project_root,
        encoding="utf-8",
        shell=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    if not result.stdout.strip():
        return {}
    return json.loads(result.stdout)


def delegate_command(workflow_root: Path, task_file: Path, artifact_root: Path) -> tuple[list[str], str]:
    if os.name == "nt":
        script = workflow_root / "windows_scripts" / "delegate_to_claude.ps1"
        argv = [
            "pwsh",
            "-NoProfile",
            "-File",
            str(script),
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-smoke",
            "-TaskId",
            "task-smoke",
            "-Role",
            "researcher",
            "-Scope",
            "AGENTS.md",
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionMode",
            "PrimaryReuse",
            "-SessionKey",
            "smoke",
            "-DryRun",
        ]
        hook_text = (
            "$env:CODEX_CLAUDE_CHILD_THREAD = '1'; "
            f'pwsh -NoProfile -File "{script.as_posix()}" '
            f'-TaskFile "{task_file.as_posix()}" '
            "-WorkflowId wf-smoke -TaskId task-smoke -Role researcher -Scope AGENTS.md "
            f'-ArtifactRoot "{artifact_root.as_posix()}" '
            "-SessionMode PrimaryReuse -SessionKey smoke -DryRun"
        )
        return argv, hook_text

    script = workflow_root / "macos_scripts" / "delegate_to_claude.sh"
    argv = [
        str(script),
        "-TaskFile",
        str(task_file),
        "-WorkflowId",
        "wf-smoke",
        "-TaskId",
        "task-smoke",
        "-Role",
        "researcher",
        "-Scope",
        "AGENTS.md",
        "-ArtifactRoot",
        str(artifact_root),
        "-SessionMode",
        "PrimaryReuse",
        "-SessionKey",
        "smoke",
        "-DryRun",
    ]
    hook_text = (
        "export CODEX_CLAUDE_CHILD_THREAD=1; "
        f'"{script.as_posix()}" '
        f'-TaskFile "{task_file.as_posix()}" '
        "-WorkflowId wf-smoke -TaskId task-smoke -Role researcher -Scope AGENTS.md "
        f'-ArtifactRoot "{artifact_root.as_posix()}" '
        "-SessionMode PrimaryReuse -SessionKey smoke -DryRun"
    )
    return argv, hook_text


def test_build_project_smoke_runs_hook_gate_and_delegate_dry_run() -> None:
    plugin_root, workflow_root, project_root = reset_smoke_project()
    config = hooks_config(plugin_root)

    session_output = run_hook(
        plugin_root,
        project_root,
        config,
        "SessionStart",
        {"hook_event_name": "SessionStart", "source": "startup"},
    )
    session_context = session_output["hookSpecificOutput"]["additionalContext"]
    assert "<EXTREMELY_IMPORTANT>" in session_context
    assert "Below is the full content of your 'codex-with-cc' skill" in session_context
    assert "## Core Contract" in session_context

    prompt_output = run_hook(
        plugin_root,
        project_root,
        config,
        "UserPromptSubmit",
        {"hook_event_name": "UserPromptSubmit", "prompt": "请开启子代理并行委派两个 worker 处理"},
    )
    assert "delegate_to_claude" in prompt_output["hookSpecificOutput"]["additionalContext"]

    blocked = run_hook(
        plugin_root,
        project_root,
        config,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": "claude -p \"do delegated work\""},
        },
    )
    assert blocked["hookSpecificOutput"]["permissionDecision"] == "deny"

    task_dir = project_root / ".codex" / "codex_with_cc" / "tasks" / "20260514"
    task_dir.mkdir(parents=True)
    task_file = task_dir / "120000000-smoke-task.md"
    task_file.write_text(
        "# Smoke Task\n\nInspect this fake project and report the routing contract. Do not modify files.\n",
        encoding="utf-8",
    )
    artifact_root = project_root / ".codex" / "codex_with_cc" / "claude-delegate"
    argv, hook_text = delegate_command(workflow_root, task_file, artifact_root)

    allowed = run_hook(
        plugin_root,
        project_root,
        config,
        "PreToolUse",
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "Bash",
            "tool_input": {"command": hook_text},
        },
    )
    assert allowed == {}

    env = os.environ.copy()
    env["CODEX_CLAUDE_CHILD_THREAD"] = "1"
    result = subprocess.run(
        argv,
        cwd=project_root,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Dry run enabled; Claude Code was not invoked." in result.stdout
    assert list(artifact_root.glob("claude_*.md"))
    assert list(artifact_root.glob("status_*.json"))
