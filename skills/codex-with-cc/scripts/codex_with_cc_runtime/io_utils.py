from __future__ import annotations

import contextlib
import json
import os
import uuid
from pathlib import Path
from typing import Any

from .common import DelegateError, now_iso



def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")



def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")



def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data["updatedAt"] = now_iso()
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    temp_path = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        temp_path.write_text(payload, encoding="utf-8")
        os.replace(temp_path, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            temp_path.unlink()



def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)



def test_path_writable(path: Path) -> None:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    probe = path.parent / f".write_probe_{uuid.uuid4().hex}.tmp"
    try:
        write_text(probe, "ok")
        probe.unlink()
    except Exception as exc:  # pragma: no cover - message path
        raise DelegateError(f"Path is not writable: {path}. {exc}") from exc
