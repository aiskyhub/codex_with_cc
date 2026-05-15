from __future__ import annotations

import re
from pathlib import Path

from .contract import load_contract
from .common import DelegateError, REPORT_HEADINGS, WORKER_ROLES
from .io_utils import read_text


def _normalize_heading(value: str) -> str:
    value = value.strip().strip("#").strip().rstrip(":").strip().lower()
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def _present_headings(text: str) -> set[str]:
    headings: set[str] = set()
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if clean.startswith(("-", "*", ">")):
            continue
        if len(clean) > 80:
            continue
        headings.add(_normalize_heading(clean))
    return headings


def _heading_aliases() -> dict[str, str]:
    task_file = load_contract().get("taskFile", {})
    required = list(task_file.get("requiredSections") or [])
    aliases = task_file.get("sectionAliases") if isinstance(task_file.get("sectionAliases"), dict) else {}
    mapping: dict[str, str] = {}
    for section in required:
        candidates = aliases.get(section) if isinstance(aliases.get(section), list) else [section]
        for candidate in candidates:
            mapping[_normalize_heading(str(candidate))] = str(section)
    return mapping


def task_file_sections(text: str) -> dict[str, str]:
    aliases = _heading_aliases()
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in text.splitlines():
        clean = line.strip()
        normalized = _normalize_heading(clean)
        if clean and not clean.startswith(("-", "*", ">")) and len(clean) <= 80 and normalized in aliases:
            current = aliases[normalized]
            sections.setdefault(current, [])
            continue
        if current is not None:
            sections.setdefault(current, []).append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _placeholder_matches(text: str) -> list[str]:
    pattern = re.compile(r"\b(?:TBD|TODO|FIXME|FILL\s+IN|PLACEHOLDER)\b|待定|稍后补充", re.IGNORECASE)
    return sorted({match.group(0) for match in pattern.finditer(text)})


def _missing_report_headings(text: str) -> list[str]:
    normalized = _normalize_heading(text)
    return [heading for heading in REPORT_HEADINGS if _normalize_heading(heading) not in normalized]


def validate_task_file_contract(text: str) -> None:
    task_file = load_contract().get("taskFile", {})
    required = list(task_file.get("requiredSections") or [])
    aliases = task_file.get("sectionAliases") if isinstance(task_file.get("sectionAliases"), dict) else {}
    present = _present_headings(text)
    missing: list[str] = []
    for section in required:
        candidates = aliases.get(section) if isinstance(aliases.get(section), list) else [section]
        normalized = {_normalize_heading(str(candidate)) for candidate in candidates}
        if not present.intersection(normalized):
            missing.append(str(section))
    if missing:
        raise DelegateError("Task file contract failed. Missing required sections: " + ", ".join(missing) + ".")
    sections = task_file_sections(text)
    empty = [section for section in required if not sections.get(str(section), "").strip()]
    if empty:
        raise DelegateError("Task file contract failed. Empty required sections: " + ", ".join(empty) + ".")
    placeholders = _placeholder_matches(text)
    if placeholders:
        raise DelegateError("Task file contract failed. Remove placeholder text: " + ", ".join(placeholders) + ".")
    missing_report = _missing_report_headings(sections.get("Report Requirements", ""))
    if missing_report:
        raise DelegateError("Task file contract failed. Report Requirements is missing headings: " + ", ".join(missing_report) + ".")


def validate_delegate_task_file(
    task_file: Path | str,
    role: str,
    review_for_task_id: str | None = None,
    review_kind: str | None = None,
    tests: list[str] | None = None,
) -> None:
    role_value = role.strip().lower()
    if role_value not in WORKER_ROLES:
        expected = ", ".join(WORKER_ROLES)
        raise DelegateError(f"Task validation failed. Invalid role: {role!r} (choose from {expected}).")
    if role_value == "reviewer" and (not review_for_task_id or not review_kind):
        raise DelegateError("Task validation failed. Reviewer tasks require -ReviewForTaskId and -ReviewKind.")
    task_text = read_text(Path(task_file))
    validate_task_file_contract(task_text)
    sections = task_file_sections(task_text)
    verification_text = sections.get("Verification", "")
    missing_tests = [item for item in tests or [] if item.strip() and item.strip() not in verification_text]
    if missing_tests:
        raise DelegateError("Task validation failed. Verification section is missing -Tests commands: " + "; ".join(missing_tests) + ".")


def run_validate_task(ns) -> int:
    validate_delegate_task_file(
        ns.task_file,
        ns.role,
        ns.review_for_task_id,
        ns.review_kind,
        ns.tests,
    )
    print(f"Task validation passed: {ns.task_file}")
    return 0
