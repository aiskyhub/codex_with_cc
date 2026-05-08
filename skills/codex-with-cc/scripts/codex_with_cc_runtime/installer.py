from __future__ import annotations

import argparse
import os
import re
import shutil
import stat
import sys
from pathlib import Path

from .common import DelegateError, SKILL_NAME, same_path
from .io_utils import read_text, write_text
from .paths import codex_home, workflow_root



def resolve_install_platform(value: str) -> str:
    if value and value.lower() != "auto":
        if value.lower() in ("macos", "darwin"):
            return "macOS"
        if value.lower() == "windows":
            return "Windows"
        raise DelegateError("Unsupported install platform. Pass Windows or macOS.")
    if sys.platform == "darwin":
        return "macOS"
    if os.name == "nt":
        return "Windows"
    raise DelegateError("Unsupported install platform. Pass --platform Windows or --platform macOS explicitly.")



def remove_agent_entrypoint_block(path: Path) -> bool:
    if not path.exists():
        return False
    text = read_text(path)
    pattern = re.compile(r"(?s)<!-- BEGIN CODEX_WITH_CC -->.*?<!-- END CODEX_WITH_CC -->")
    updated = pattern.sub("", text)
    if updated == text:
        return False
    if updated.strip():
        write_text(path, updated.strip() + "\n")
    else:
        path.unlink()
    return True



def update_installed_workflow_references(workflow: Path, workflow_relative: str) -> None:
    canonical = "docs/codex_with_cc"
    canonical_win = canonical.replace("/", "\\")
    replacement = workflow_relative.replace("\\", "/")
    replacement_win = replacement.replace("/", "\\")
    if replacement == canonical:
        return
    for path in workflow.rglob("*"):
        if not path.is_file() or path.suffix not in {".md", ".ps1", ".sh"}:
            continue
        text = read_text(path)
        updated = (
            text.replace(f"./{canonical}", replacement)
            .replace(f".\\{canonical_win}", replacement_win)
            .replace(canonical, replacement)
            .replace(canonical_win, replacement_win)
        )
        if updated != text:
            write_text(path, updated)



def update_gitignore_file(path: Path) -> None:
    entry = ".codex/codex_with_cc"
    if path.exists():
        text = read_text(path)
        for line in text.splitlines():
            if line.strip() in (entry, f"{entry}/"):
                return
        updated = text.rstrip()
        if updated:
            updated += "\n"
        updated += entry + "\n"
    else:
        updated = entry + "\n"
    write_text(path, updated)



def copy_workflow_source(source: Path, destination: Path, excluded_script_root: str) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        if item.name in (excluded_script_root, "__pycache__") or item.suffix == ".pyc":
            continue
        target = destination / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(item, target)



def remove_path_inside(target_root: Path, path: Path) -> bool:
    if not path.exists():
        return False
    try:
        path.resolve().relative_to(target_root)
    except ValueError as exc:
        raise DelegateError(f"Refusing to remove path outside target root: {path}") from exc
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()
    return True



def run_install(ns: argparse.Namespace) -> int:
    install_platform = resolve_install_platform(ns.platform)
    source_workflow = workflow_root()
    installer_root = source_workflow.parent.resolve()
    source_skill = source_workflow if source_workflow.name == SKILL_NAME else installer_root / "skills" / SKILL_NAME
    target_root = Path(ns.target_root).resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    if same_path(installer_root, target_root):
        raise DelegateError(
            f"Refusing to install codex_with_cc into its own source repository. Choose a different target root: {installer_root}"
        )
    if not source_workflow.exists():
        raise DelegateError(f"Workflow source was not found: {source_workflow}")
    if not source_skill.exists():
        raise DelegateError(f"Skill source was not found: {source_skill}")

    target_workflow = codex_home() / "skills" / SKILL_NAME
    target_local_skill = target_root / ".codex" / "skills" / SKILL_NAME
    workflow_relative = target_workflow.resolve().as_posix()
    task_root = target_root / ".codex" / "codex_with_cc" / "tasks"
    cleanup: list[str] = []

    if same_path(source_workflow, target_workflow) and not same_path(source_skill, target_workflow):
        raise DelegateError(
            f"Refusing to install codex_with_cc into its own source repository. Choose a different target root: {source_workflow}"
        )

    for candidate in (target_root / "docs" / "codex_with_cc", target_root / "doc" / "codex_with_cc"):
        if same_path(source_workflow, candidate):
            raise DelegateError(
                f"Refusing to install codex_with_cc into its own source repository. Choose a different target root: {source_workflow}"
            )
        if remove_path_inside(target_root, candidate):
            cleanup.append(candidate.relative_to(target_root).as_posix())
    if remove_agent_entrypoint_block(target_root / "AGENTS.md"):
        cleanup.append("AGENTS.md managed block")
    if remove_path_inside(target_root, target_local_skill):
        cleanup.append(target_local_skill.relative_to(target_root).as_posix())
    if not same_path(source_skill, target_workflow) and remove_path_inside(codex_home(), target_workflow):
        cleanup.append(str(target_workflow))

    if not same_path(source_skill, target_workflow):
        excluded = "macos_scripts" if install_platform == "Windows" else "windows_scripts"
        copy_workflow_source(source_skill, target_workflow, excluded)
    update_installed_workflow_references(target_workflow, workflow_relative)
    if install_platform == "macOS":
        mac_scripts = target_workflow / "macos_scripts"
        if mac_scripts.exists():
            for script in mac_scripts.glob("*.sh"):
                script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    task_root.mkdir(parents=True, exist_ok=True)
    gitkeep = task_root / ".gitkeep"
    if gitkeep.exists():
        gitkeep.unlink()
    update_gitignore_file(target_root / ".gitignore")
    print(f"codex_with_cc global skill installed into: {target_workflow}")
    print(f"Old install artifacts cleaned: {', '.join(cleanup) if cleanup else 'none'}")
    print("Next: restart Codex, then use $codex-with-cc or the subagent/delegation trigger words.")
    return 0
