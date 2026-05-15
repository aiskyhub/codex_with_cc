from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path



def runtime_python_root() -> Path:
    return Path(__file__).resolve().parents[1]



def workflow_root() -> Path:
    return runtime_python_root().parent



def repo_root() -> Path:
    return Path.cwd().resolve()


def project_artifact_root(root: Path | None = None) -> Path:
    base = root.resolve() if root else repo_root()
    return (base / ".codex" / "codex_with_cc" / "claude-delegate").resolve()


def codex_home() -> Path:
    value = os.environ.get("CODEX_HOME")
    if value and value.strip():
        return Path(value).expanduser().resolve()
    return (Path.home() / ".codex").resolve()


def project_artifact_key(root: Path | None = None) -> str:
    base = root.resolve() if root else repo_root()
    name = re.sub(r"[^A-Za-z0-9_.-]+", "_", base.name).strip("._") or "project"
    digest = hashlib.sha256(str(base).encode("utf-8")).hexdigest()[:12]
    return f"{name}-{digest}"


def user_artifact_root(root: Path | None = None) -> Path:
    return (codex_home() / "codex_with_cc" / "claude-delegate" / project_artifact_key(root)).resolve()



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
