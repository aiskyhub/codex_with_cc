from __future__ import annotations

import os
from pathlib import Path

from .common import SKILL_NAME, same_path



def runtime_python_root() -> Path:
    return Path(__file__).resolve().parents[1]



def workflow_root() -> Path:
    return runtime_python_root().parent



def codex_home() -> Path:
    raw = os.environ.get("CODEX_HOME")
    return Path(raw).expanduser().resolve() if raw else (Path.home() / ".codex").resolve()



def repo_root() -> Path:
    root = workflow_root()
    container = root.parent
    if root.name == SKILL_NAME and container.name == "skills":
        if same_path(container.parent, codex_home()):
            return Path.cwd().resolve()
        if container.parent.name == ".codex":
            return container.parent.parent.resolve()
    if container.name in ("docs", "doc"):
        return container.parent.resolve()
    return container.resolve()



def workflow_relative_path() -> str:
    root = workflow_root().resolve()
    repo = repo_root().resolve()
    try:
        return root.relative_to(repo).as_posix()
    except ValueError:
        return root.as_posix()



def script_family() -> str:
    return "windows_scripts" if os.name == "nt" else "macos_scripts"



def script_ext() -> str:
    return ".ps1" if os.name == "nt" else ".sh"
