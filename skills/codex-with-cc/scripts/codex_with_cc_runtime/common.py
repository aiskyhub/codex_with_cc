from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_SCHEMA_VERSION = 3
INVOCATION_CONTRACT = "codex_with_cc_workflow"
CHILD_MARKER_NAME = "CODEX_CLAUDE_CHILD_THREAD"
CHILD_MARKER_VALUE = "1"
REPORT_HEADINGS = (
    "Status",
    "Role",
    "Summary",
    "Changed Files",
    "Verification",
    "Findings",
    "Final Result",
    "Risks Or Follow-ups",
)
REPORT_STATUS_VALUES = ("DONE", "DONE_WITH_CONCERNS", "NEEDS_CONTEXT", "BLOCKED", "FAIL")
WORKER_ROLES = ("planner", "implementer", "researcher", "reviewer", "final-verifier")
SKILL_NAME = "codex-with-cc"



class DelegateError(RuntimeError):
    pass



def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat()



def boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y")
    return bool(value)



def same_path(a: str | Path, b: str | Path) -> bool:
    left = os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(a))))
    right = os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(b))))
    return left == right
