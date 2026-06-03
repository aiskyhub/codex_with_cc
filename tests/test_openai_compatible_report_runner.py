from __future__ import annotations

import argparse
import json
import socket
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "codex-with-cc" / "scripts"))

from codex_with_cc_runtime.artifacts import verify_artifacts
from codex_with_cc_runtime.cli import main as runtime_cli_main
from codex_with_cc_runtime.common import CHILD_MARKER_NAME, CHILD_MARKER_VALUE
from codex_with_cc_runtime.openai_compatible_report import run_openai_compatible_report_delegate
from tests.task_helpers import compliant_task


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False


def _base_args(task_file: Path, artifact_root: Path) -> argparse.Namespace:
    return argparse.Namespace(
        task_file=str(task_file),
        scope=["skills/codex-with-cc"],
        tests=["pytest -q tests/test_openai_compatible_report_runner.py"],
        workflow_id="wf-openai-report",
        task_id="task-openai-report",
        role="researcher",
        review_for_task_id=None,
        review_kind=None,
        depends_on=[],
        model="deepseek-v4-flash",
        name=None,
        name_prefix="codex-delegate",
        max_budget_usd=None,
        artifact_root=str(artifact_root),
        output_path=None,
        allow_parallel=False,
        session_mode="PrimaryReuse",
        session_key="openai-report-session",
        session_lease_timeout_seconds=60,
        session_lease_wait_seconds=0,
        reset_primary_session=False,
        reset_parallel_pool=False,
        lock_timeout_seconds=0,
        lock_poll_milliseconds=50,
        max_retry_count=0,
        bypass_permissions=True,
        dry_run=False,
    )


def _find_run_id(artifact_root: Path) -> str:
    config_files = sorted(artifact_root.glob("config_*.json"))
    assert config_files
    return config_files[-1].stem.replace("config_", "", 1)


def test_openai_compatible_report_wrappers_forward_to_runtime_subcommand() -> None:
    repo = Path(__file__).resolve().parents[1]
    py_entry = repo / "skills" / "codex-with-cc" / "scripts" / "delegate_to_openai_compatible_report.py"
    mac_entry = repo / "skills" / "codex-with-cc" / "macos_scripts" / "delegate_to_openai_compatible_report.sh"
    win_entry = repo / "skills" / "codex-with-cc" / "windows_scripts" / "delegate_to_openai_compatible_report.ps1"

    assert 'main(["openai-compatible-report", *sys.argv[1:]])' in py_entry.read_text(encoding="utf-8")
    mac_text = mac_entry.read_text(encoding="utf-8")
    assert mac_text.startswith("#!/bin/zsh\n")
    assert 'delegate_to_openai_compatible_report.py "$@"' in mac_text
    assert "delegate_to_openai_compatible_report.py" in win_entry.read_text(encoding="utf-8")


def _clear_provider_env(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for name in (
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_API_BASE_URL",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_COMPATIBLE_API_KEY",
        "OPENAI_COMPATIBLE_BASE_URL",
        "OPENAI_COMPATIBLE_MODEL",
        "OPENAI_COMPATIBLE_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)


def _enable_child_thread(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv(CHILD_MARKER_NAME, CHILD_MARKER_VALUE)


def _report(status: str = "DONE", role: str = "researcher", final_result: str | None = None) -> str:
    return "\n".join(
        [
            "Status",
            status,
            "",
            "Role",
            role,
            "",
            "Summary",
            "Report generated.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            "- report-only runner generated a structured workflow report; no shell commands executed",
            "",
            "Findings",
            "- none",
            "",
            "Final Result",
            final_result or status,
            "",
            "Risks Or Follow-ups",
            "- none",
        ]
    )


def test_openai_compatible_runner_writes_report_artifacts(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "DEEPSEEK_API_KEY=dotenv-key",
                "DEEPSEEK_BASE_URL=https://example.invalid/v1",
                "DEEPSEEK_MODEL=deepseek-v4-flash",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        assert request.full_url == "https://example.invalid/v1/chat/completions"
        return _FakeResponse({"choices": [{"message": {"content": _report()}}], "usage": {"total_tokens": 42}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))
    assert code == 0

    run_id = _find_run_id(artifact_root)
    output = (artifact_root / f"report_{run_id}.md").read_text(encoding="utf-8")
    config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
    status = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))
    workflow = json.loads((artifact_root / "workflow_wf-openai-report.json").read_text(encoding="utf-8"))
    stream = (artifact_root / f"stream_{run_id}.jsonl").read_text(encoding="utf-8")

    assert "Status\nDONE" in output
    assert config["runnerType"] == "openai_compatible_report"
    assert config["model"] == "deepseek-v4-flash"
    assert config["timeoutSeconds"] == 600
    assert status["runnerType"] == "openai_compatible_report"
    assert workflow["runs"][run_id]["runnerType"] == "openai_compatible_report"
    assert status["status"] == "completed"
    assert "dotenv-key" not in json.dumps(config)
    assert "dotenv-key" not in json.dumps(status)
    assert "dotenv-key" not in stream
    assert "dotenv-key" not in output
    verify_artifacts(run_id, str(artifact_root))


def test_openai_compatible_runner_uses_env_over_dotenv(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    (tmp_path / ".env").write_text("DEEPSEEK_API_KEY=dotenv-key\n", encoding="utf-8")

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        auth = request.headers.get("Authorization")
        assert auth == "Bearer env-key"
        return _FakeResponse({"choices": [{"message": {"content": _report("DONE")}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "env-key")

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))
    assert code == 0


def test_openai_compatible_report_runtime_cli_subcommand(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        return _FakeResponse({"choices": [{"message": {"content": _report()}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    code = runtime_cli_main(
        [
            "openai-compatible-report",
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-openai-cli",
            "-TaskId",
            "task-openai-cli",
            "-Role",
            "researcher",
            "-SessionKey",
            "openai-report-session",
            "-ArtifactRoot",
            str(artifact_root),
        ]
    )

    assert code == 0
    run_id = _find_run_id(artifact_root)
    config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
    assert config["model"] == "deepseek-v4-flash"
    assert config["apiBaseUrl"] == "https://api.deepseek.com"
    verify_artifacts(run_id, str(artifact_root))


def test_openai_compatible_runner_normalizes_markdown_headings(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    markdown_report = _report().replace("Status", "## Status", 1).replace("Role", "**Role**", 1).replace("Final Result", "Final Result:", 1)

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        return _FakeResponse({"choices": [{"message": {"content": markdown_report}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))

    assert code == 0
    run_id = _find_run_id(artifact_root)
    output = (artifact_root / f"report_{run_id}.md").read_text(encoding="utf-8")
    stream = json.loads((artifact_root / f"stream_{run_id}.jsonl").read_text(encoding="utf-8"))
    assert output.startswith("Status\nDONE")
    assert "\nRole\nresearcher" in output
    assert "\nFinal Result\nDONE" in output
    assert stream["normalizedReportHeadings"] is True
    verify_artifacts(run_id, str(artifact_root))


@pytest.mark.parametrize(
    ("content", "expected_summary"),
    [
        ("I will start implementing now.", "required report headings"),
        (_report("DONE", final_result="FAIL"), "mismatched Status and Final Result"),
        (_report("DONE", role="reviewer"), "role mismatch"),
    ],
)
def test_openai_compatible_runner_structures_invalid_model_output(
    monkeypatch,
    tmp_path: Path,
    content: str,
    expected_summary: str,
) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        return _FakeResponse({"choices": [{"message": {"content": content}}]})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))

    assert code == 1
    run_id = _find_run_id(artifact_root)
    output = (artifact_root / f"report_{run_id}.md").read_text(encoding="utf-8")
    status = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))
    assert "Status\nFAIL" in output
    assert expected_summary in status["failureSummary"]
    verify_artifacts(run_id, str(artifact_root))


def test_openai_compatible_runner_redacts_secret_from_failure_artifacts(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        raise ValueError("provider echoed env-secret in an error")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-secret")

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))

    assert code == 1
    combined = "\n".join(path.read_text(encoding="utf-8") for path in artifact_root.glob("*"))
    assert "env-secret" not in combined
    assert "<redacted>" in combined


def test_openai_compatible_runner_structures_socket_timeout(monkeypatch, tmp_path: Path) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"

    def fake_urlopen(request, timeout=0):  # type: ignore[no-untyped-def]
        raise socket.timeout("provider read timed out")

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")

    code = run_openai_compatible_report_delegate(_base_args(task_file, artifact_root))

    assert code == 1
    run_id = _find_run_id(artifact_root)
    output = (artifact_root / f"report_{run_id}.md").read_text(encoding="utf-8")
    config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
    status = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))
    stream = json.loads((artifact_root / f"stream_{run_id}.jsonl").read_text(encoding="utf-8"))
    assert "Status\nFAIL" in output
    assert status["status"] == "failed"
    assert status["exitCode"] == 1
    assert status["failureDisposition"] == "NEED_HUMAN_INTERVENTION"
    assert status["failureSummary"] == "provider read timed out"
    assert config["failureSummary"] == status["failureSummary"]
    assert stream["status"] == "error"
    verify_artifacts(run_id, str(artifact_root))


def test_openai_compatible_report_cli_requires_api_key(monkeypatch, tmp_path: Path, capsys) -> None:
    _clear_provider_env(monkeypatch)
    _enable_child_thread(monkeypatch)
    task_file = tmp_path / "task.md"
    task_file.write_text(compliant_task("generate a report-only audit"), encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    monkeypatch.chdir(tmp_path)

    code = runtime_cli_main(
        [
            "openai-compatible-report",
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-openai-missing-key",
            "-TaskId",
            "task-openai-missing-key",
            "-Role",
            "researcher",
            "-SessionKey",
            "openai-report-session",
            "-ArtifactRoot",
            str(artifact_root),
        ]
    )

    assert code == 1
    assert "Missing API key" in capsys.readouterr().err
