#!/usr/bin/env python3
import subprocess
import sys
import tempfile
import json
import os
from pathlib import Path

repo = Path(__file__).resolve().parents[1]
installer = repo / "skills" / "codex-with-cc" / "scripts" / "install_codex_with_cc.py"
source_skill = repo / "skills" / "codex-with-cc"


def run_install(target: Path, platform: str, *extra: str) -> str:
    result = subprocess.run(
        [sys.executable, str(installer), "--target-root", str(target), "--platform", platform, *extra],
        cwd=repo,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CODEX_HOME": str(codex_home)},
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    return result.stdout + result.stderr


with tempfile.TemporaryDirectory(prefix="codex_with_cc_install_") as tmp:
    root = Path(tmp)
    codex_home = root / "codex-home"
    global_skill = codex_home / "skills" / "codex-with-cc"
    target = root / "host-project"
    target.mkdir()
    (target / "README.md").write_text("# Host Project\n", encoding="utf-8")
    (target / ".gitignore").write_text("build\n.claude\n", encoding="utf-8")
    (target / "AGENTS.md").write_text(
        "\n".join(
            (
                "# Existing Host Instructions",
                "",
                "Keep this project-specific rule.",
                "",
                "<!-- BEGIN CODEX_WITH_CC -->",
                "stale managed block",
                "<!-- END CODEX_WITH_CC -->",
                "",
            )
        ),
        encoding="utf-8",
    )
    (target / "docs" / "codex_with_cc").mkdir(parents=True)
    (target / "docs" / "codex_with_cc" / "obsolete.txt").write_text("stale docs workflow", encoding="utf-8")
    (target / "doc" / "codex_with_cc").mkdir(parents=True)
    (target / "doc" / "codex_with_cc" / "obsolete.txt").write_text("stale doc workflow", encoding="utf-8")
    (target / ".codex" / "skills" / "codex-with-cc").mkdir(parents=True)
    (target / ".codex" / "skills" / "codex-with-cc" / "obsolete.txt").write_text("stale local skill", encoding="utf-8")
    (target / ".codex" / "codex_with_cc" / "claude-delegate").mkdir(parents=True)
    (target / ".codex" / "codex_with_cc" / "claude-delegate" / "status_keep.json").write_text("{}", encoding="utf-8")

    out = run_install(target, "Windows")
    workflow = global_skill
    task_root = target / ".codex" / "codex_with_cc" / "tasks"
    assert (workflow / "SKILL.md").exists()
    assert (workflow / "agents" / "openai.yaml").exists()
    assert (workflow / "CODEX_WITH_CC.md").exists()
    assert (workflow / "scripts" / "delegate_to_claude.py").exists()
    assert (workflow / "scripts" / "runtime.py").exists()
    assert (workflow / "scripts" / "test_delegate_runtime.py").exists()
    assert (source_skill / "scripts" / "runtime.py").exists()
    installed_selftests = (workflow / "scripts" / "codex_with_cc_runtime" / "selftests.py").read_text(encoding="utf-8")
    assert "docs/codex_with_cc/windows_scripts;docs/codex_with_cc" in installed_selftests
    assert str(global_skill).replace("\\", "/") not in installed_selftests
    assert not (workflow / "scripts" / "__pycache__").exists()
    assert not (workflow / "tests").exists()
    assert (workflow / "windows_scripts" / "test_delegate_runtime.ps1").exists()
    assert (workflow / "windows_scripts" / "delegate_to_claude.ps1").exists()
    assert not (workflow / "macos_scripts").exists()
    installed_contract = (workflow / "CODEX_WITH_CC.md").read_text(encoding="utf-8")
    assert "docs/codex_with_cc" not in installed_contract
    assert ".\\C:" not in installed_contract
    assert not (target / ".codex" / "skills" / "codex-with-cc").exists()
    assert task_root.exists()
    assert not (task_root / ".gitkeep").exists()
    assert (target / ".codex" / "codex_with_cc" / "claude-delegate" / "status_keep.json").exists()
    assert ".codex/codex_with_cc" in (target / ".gitignore").read_text(encoding="utf-8")
    assert ".codex\n" not in (target / ".gitignore").read_text(encoding="utf-8")
    agents = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert "Keep this project-specific rule." in agents
    assert "<!-- BEGIN CODEX_WITH_CC -->" not in agents
    assert not (target / "docs" / "codex_with_cc").exists()
    assert not (target / "doc" / "codex_with_cc").exists()
    assert "codex_with_cc global skill installed into:" in out
    assert "Old install artifacts cleaned:" in out
    assert "Next: restart Codex, then use $codex-with-cc or the subagent/delegation trigger words." in out

    dry_root = target / ".codex" / "codex_with_cc" / "dry-run-root-probe"
    result = subprocess.run(
        [
            sys.executable,
            str(workflow / "scripts" / "delegate_to_claude.py"),
            "-Task",
            "dry run root probe",
            "-ArtifactRoot",
            str(dry_root),
            "-SessionKey",
            "root-probe",
            "-DryRun",
        ],
        cwd=target,
        text=True,
        capture_output=True,
        env={**os.environ, "CODEX_CLAUDE_CHILD_THREAD": "1", "PYTHONDONTWRITEBYTECODE": "1", "CODEX_HOME": str(codex_home)},
    )
    if result.returncode != 0:
        raise AssertionError(result.stdout + result.stderr)
    config_path = next(dry_root.glob("config_*.json"))
    config = json.loads(config_path.read_text(encoding="utf-8"))
    assert Path(config["repoRoot"]) == target.resolve()
    assert Path(config["workflowRoot"]) == global_skill.resolve()
    assert Path(config["workflowRelativePath"]) == global_skill.resolve()

    second_target = root / "second-host-project"
    second_target.mkdir()
    second_out = subprocess.run(
        [
            sys.executable,
            str(global_skill / "scripts" / "install_codex_with_cc.py"),
            "--target-root",
            str(second_target),
            "--platform",
            "Windows",
        ],
        cwd=second_target,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "CODEX_HOME": str(codex_home)},
    )
    if second_out.returncode != 0:
        raise AssertionError(second_out.stdout + second_out.stderr)
    assert (second_target / ".codex" / "codex_with_cc" / "tasks").exists()
    assert not (second_target / ".codex" / "skills" / "codex-with-cc").exists()

    (workflow / "obsolete.txt").write_text("stale", encoding="utf-8")
    (workflow / "HOST_PROJECT_RULES.md").write_text("stale host rules", encoding="utf-8")
    (workflow / "PROJECT_MEMORY.md").write_text("stale project memory", encoding="utf-8")
    stale_doc_workflow = target / "doc" / "codex_with_cc"
    stale_doc_workflow.mkdir(parents=True)
    (stale_doc_workflow / "obsolete.txt").write_text("stale doc workflow", encoding="utf-8")
    (target / "doc" / "keep.md").write_text("keep", encoding="utf-8")
    (task_root / ".gitkeep").write_text("", encoding="utf-8")
    run_install(target, "Windows")
    agents_after_reinstall = (target / "AGENTS.md").read_text(encoding="utf-8")
    assert not (workflow / "obsolete.txt").exists()
    assert not (workflow / "HOST_PROJECT_RULES.md").exists()
    assert not (workflow / "PROJECT_MEMORY.md").exists()
    assert not stale_doc_workflow.exists()
    assert (target / "doc" / "keep.md").exists()
    assert not (task_root / ".gitkeep").exists()
    assert "<!-- BEGIN CODEX_WITH_CC -->" not in agents_after_reinstall

    doc_only = root / "doc-only-host-project"
    (doc_only / "doc").mkdir(parents=True)
    doc_only_out = run_install(doc_only, "Windows")
    assert (global_skill / "CODEX_WITH_CC.md").exists()
    assert not (doc_only / ".codex" / "skills" / "codex-with-cc").exists()
    assert not (doc_only / "docs").exists()
    assert "Next: restart Codex" in doc_only_out

    both_docs = root / "both-docs-host-project"
    (both_docs / "doc").mkdir(parents=True)
    (both_docs / "docs").mkdir(parents=True)
    run_install(both_docs, "Windows", "--skip-agent-entrypoints")
    assert (global_skill / "CODEX_WITH_CC.md").exists()
    assert not (both_docs / ".codex" / "skills" / "codex-with-cc").exists()
    assert not (both_docs / "docs" / "codex_with_cc").exists()
    assert not (both_docs / "doc" / "codex_with_cc").exists()

    agents_only = root / "agents-only-host-project"
    agents_only.mkdir()
    (agents_only / "AGENTS.md").write_text(
        "<!-- BEGIN CODEX_WITH_CC -->\nstale managed block\n<!-- END CODEX_WITH_CC -->\n",
        encoding="utf-8",
    )
    run_install(agents_only, "Windows")
    assert not (agents_only / "AGENTS.md").exists()

    mac_target = root / "mac-host-project"
    (mac_target / "doc").mkdir(parents=True)
    run_install(mac_target, "macOS", "--skip-agent-entrypoints")
    mac_workflow = global_skill
    assert (mac_workflow / "SKILL.md").exists()
    assert (mac_workflow / "scripts" / "delegate_to_claude.py").exists()
    assert (mac_workflow / "scripts" / "runtime.py").exists()
    assert (mac_workflow / "scripts" / "test_delegate_runtime.py").exists()
    assert not (mac_workflow / "tests").exists()
    assert (mac_workflow / "macos_scripts" / "test_delegate_runtime.sh").exists()
    assert (mac_workflow / "macos_scripts" / "_runtime.sh").exists()
    assert (mac_workflow / "macos_scripts" / "delegate_to_claude.sh").exists()
    assert not (mac_workflow / "macos_scripts" / "README.md").exists()
    assert not (mac_workflow / "windows_scripts").exists()

print("install tests passed")
