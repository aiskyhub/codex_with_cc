"""Tests for workflow_probe CLI."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
PROBE_SCRIPT = SRC / "workflow_probe.py"

sys.path.insert(0, str(SRC))

from workflow_probe import summarize  # noqa: E402


# --- Unit: summarize() ---

def test_counts_each_status() -> None:
    tasks = [
        {"id": "a", "title": "A", "status": "passed"},
        {"id": "b", "title": "B", "status": "failed"},
        {"id": "c", "title": "C", "status": "running"},
        {"id": "d", "title": "D", "status": "pending"},
        {"id": "e", "title": "E", "status": "passed"},
    ]
    result = summarize(tasks)
    assert result["total"] == 5
    assert result["counts"]["passed"] == 2
    assert result["counts"]["failed"] == 1
    assert result["counts"]["running"] == 1
    assert result["counts"]["pending"] == 1
    assert result["failed_task_ids"] == ["b"]


def test_summarize_accepts_top_level_payload_object() -> None:
    payload = {
        "tasks": [
            {"id": "a", "title": "A", "status": "passed"},
        ]
    }
    result = summarize(payload)
    assert result["total"] == 1
    assert result["ready"] is True


def test_ready_true_when_all_passed() -> None:
    tasks = [
        {"id": "x", "title": "X", "status": "passed"},
        {"id": "y", "title": "Y", "status": "passed"},
    ]
    result = summarize(tasks)
    assert result["ready"] is True


def test_ready_false_when_not_all_passed() -> None:
    tasks = [
        {"id": "x", "title": "X", "status": "passed"},
        {"id": "y", "title": "Y", "status": "pending"},
    ]
    result = summarize(tasks)
    assert result["ready"] is False


def test_ready_false_when_no_tasks() -> None:
    result = summarize([])
    assert result["ready"] is False


# --- Unit: validate_task() ---

def test_missing_id_reports_field_path() -> None:
    task = {"title": "No ID", "status": "passed"}
    with pytest.raises(ValueError, match="tasks\\[0\\].id"):
        summarize([task])


def test_missing_title_reports_field_path() -> None:
    task = {"id": "1", "status": "passed"}
    with pytest.raises(ValueError, match="tasks\\[0\\].title"):
        summarize([task])


def test_invalid_status_reports_bad_value() -> None:
    task = {"id": "1", "title": "Bad", "status": "invalid_status"}
    with pytest.raises(ValueError, match="invalid_status"):
        summarize([task])


# --- CLI integration ---

def test_cli_prints_expected_json(tmp_path: Path) -> None:
    data = {
        "tasks": [
            {"id": "a", "title": "A", "status": "passed"},
            {"id": "b", "title": "B", "status": "failed"},
        ]
    }
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), str(input_file)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0
    parsed = json.loads(result.stdout)
    assert parsed["total"] == 2
    assert parsed["counts"]["failed"] == 1
    assert parsed["failed_task_ids"] == ["b"]
    assert parsed["ready"] is False


def test_cli_invalid_input_exits_nonzero(tmp_path: Path) -> None:
    data = {"tasks": [{"id": "1", "title": "X", "status": "bogus"}]}
    input_file = tmp_path / "bad.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(PROBE_SCRIPT), str(input_file)],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "bogus" in result.stderr
