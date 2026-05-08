from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .common import REPORT_HEADINGS
from .io_utils import read_text



def test_final_result_heading(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    return report_heading_match(text, "Final Result") is not None



def report_heading_match(text: str, heading: str) -> re.Match[str] | None:
    pattern = rf"(?m)^\s*(?:#+\s*)?(?:\*\*)?{re.escape(heading)}(?:\*\*)?\s*$"
    return re.search(pattern, text)



def text_has_required_report_headings(text: str | None) -> bool:
    if not text or not text.strip():
        return False
    positions: list[int] = []
    for heading in REPORT_HEADINGS:
        match = report_heading_match(text, heading)
        if match is None:
            return False
        positions.append(match.start())
    return positions == sorted(positions)



def path_has_final_result(path: Path | str | None) -> bool:
    if not path:
        return False
    path = Path(path)
    if not path.exists():
        return False
    return test_final_result_heading(read_text(path))



def path_has_required_report_headings(path: Path | str | None) -> bool:
    if not path:
        return False
    path = Path(path)
    if not path.exists():
        return False
    return text_has_required_report_headings(read_text(path))



def convert_unstructured_final_text(text: str | None) -> str:
    trimmed = (text or "").strip()
    if not trimmed:
        return ""
    if text_has_required_report_headings(trimmed):
        return trimmed
    return f"""Process Log
- Claude Code exited successfully but did not produce the required delegate report headings.
- The delegate wrapper rejected that unstructured response and preserved it below for audit.

Summary
Claude Code did not satisfy the delegate report contract. Treat this run as failed even though the Claude CLI process exited with code 0.

Changed Files
Unknown from unstructured response; inspect repository diff and raw delegate artifacts before accepting file-level conclusions.

Verification
Unknown from unstructured response; do not treat verification as proven unless the original response below lists exact commands and outcomes.

Final Result
UNSTRUCTURED_SUCCESS_REJECTED
{trimmed}

Risks Or Follow-ups
- Retry after fixing prompt/session handling, or rerun with a fresh session if the response indicates stale context.
"""



def get_output_resolution(
    final_text: str,
    output_path: Path,
    exit_code: int,
    saw_result_success: bool,
    captured_final_result_heading: bool,
) -> dict[str, Any]:
    final_has = text_has_required_report_headings(final_text)
    existing_structured = path_has_required_report_headings(output_path)
    normalized = (
        exit_code == 0
        and saw_result_success
        and not final_has
        and not existing_structured
        and bool(final_text.strip())
    )
    persisted = convert_unstructured_final_text(final_text) if normalized else final_text
    persisted_has = text_has_required_report_headings(persisted)
    should_persist = persisted_has or (not existing_structured and bool(final_text.strip()))
    delegate_succeeded = exit_code == 0 and saw_result_success and (final_has or existing_structured)
    return {
        "finalTextHasFinalResult": final_has,
        "existingStructuredOutput": existing_structured,
        "outputWasNormalized": normalized,
        "persistedFinalText": persisted,
        "shouldPersistFinalText": should_persist,
        "delegateSucceeded": delegate_succeeded,
    }



def build_report_repair_prompt(output_path: Path, previous_text: str) -> str:
    return f"""Your previous response did not satisfy the required delegate report contract.

Do not make new edits unless you discover your previous work was incomplete. Do not ask what to do next.
Use the completed work and verification from this same Claude session to write the final delegate report.

Write the report to this path if you choose to write a file, and also return the report as your final response:
{output_path}

Your final response must start with `Process Log` on the first line and must include exactly these headings in this order:

Process Log
- <what you did>

Summary
<brief result>

Changed Files
- <path or None>

Verification
- <command and outcome>

Final Result
<PASS, FAIL, or blocked result>

Risks Or Follow-ups
- <risk or None>

Previous non-compliant response:
{previous_text.strip()}
"""
