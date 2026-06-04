#!/usr/bin/env python3
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.task_helpers import compliant_task


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "codex-with-cc" / "scripts"
DELEGATE = SCRIPTS / "delegate_to_claude.py"
VERIFY_ARTIFACTS = SCRIPTS / "verify_delegate_artifacts.py"
sys.path.insert(0, str(SCRIPTS))

from codex_with_cc_runtime.reports import text_has_required_report_headings
from codex_with_cc_runtime.sessions import task_fingerprint


REPORT = "\n".join(
    (
        "Status",
        "DONE",
        "",
        "Role",
        "implementer",
        "",
        "Summary",
        "Fake Claude completed.",
        "",
        "Changed Files",
        "None",
        "",
        "Verification",
        "- fake verification passed",
        "",
        "Findings",
        "- fake delegate execution",
        "",
        "Final Result",
        "DONE",
        "",
        "Risks Or Follow-ups",
        "None",
    )
)


def run_id_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("RunId:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"RunId line missing from output:\n{output}")


def make_fake_claude_bin(root: Path) -> Path:
    fake_bin = root / "fake-claude-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    assistant = json.dumps(
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": REPORT}]}},
        separators=(",", ":"),
    )
    result = json.dumps({"type": "result", "subtype": "success"}, separators=(",", ":"))
    if os.name == "nt":
        (fake_bin / "claude.cmd").write_text(
            "@echo off\n"
            "more > nul\n"
            f"echo {assistant}\n"
            f"echo {result}\n"
            "exit /b 0\n",
            encoding="utf-8",
        )
    else:
        script = fake_bin / "claude"
        script.write_text(
            "#!/bin/sh\n"
            "cat >/dev/null\n"
            f"printf '%s\\n' '{assistant}'\n"
            f"printf '%s\\n' '{result}'\n",
            encoding="utf-8",
        )
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return fake_bin


def make_name_rejecting_fake_claude_bin(root: Path) -> Path:
    fake_bin = root / "fake-name-rejecting-claude-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "fake_name_rejecting_claude.py"
    assistant = json.dumps(
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": REPORT}]}}
    )
    result = json.dumps({"type": "result", "subtype": "success"})
    script.write_text(
        "\n".join(
            (
                "import sys",
                "",
                "sys.stdin.read()",
                "if '--name' in sys.argv[1:]:",
                "    print(\"error: unknown option '--name'\")",
                "    raise SystemExit(1)",
                f"print({assistant!r})",
                f"print({result!r})",
            )
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        (fake_bin / "claude.cmd").write_text(
            f'@echo off\n"{sys.executable}" "{script}" %*\n',
            encoding="utf-8",
        )
    else:
        shim = fake_bin / "claude"
        shim.write_text(
            f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n",
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return fake_bin


def make_file_report_fake_claude_bin(root: Path) -> Path:
    fake_bin = root / "fake-file-report-claude-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "fake_file_report_claude.py"
    script.write_text(
        "\n".join(
            (
                "import json",
                "import re",
                "import sys",
                "",
                f"report = {REPORT!r}",
                "prompt = sys.stdin.read()",
                "match = re.search(r'Delegated output report path:\\n(.+)', prompt)",
                "if not match:",
                "    raise SystemExit('output path missing from prompt')",
                "with open(match.group(1).strip(), 'w', encoding='utf-8') as handle:",
                "    handle.write(report)",
                "print(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Report written to delegated output path.'}]}}))",
                "print(json.dumps({'type': 'result', 'subtype': 'success'}))",
            )
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        (fake_bin / "claude.cmd").write_text(
            f'@echo off\n"{sys.executable}" "{script}"\n',
            encoding="utf-8",
        )
    else:
        shim = fake_bin / "claude"
        shim.write_text(
            f"#!/bin/sh\nexec '{sys.executable}' '{script}'\n",
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return fake_bin


def make_socket_retry_fake_claude_bin(root: Path) -> Path:
    fake_bin = root / "fake-socket-retry-claude-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    script = fake_bin / "fake_socket_retry_claude.py"
    script.write_text(
        "\n".join(
            (
                "import json",
                "import os",
                "import sys",
                "from pathlib import Path",
                "",
                f"report = {REPORT!r}",
                "state_path = Path(os.environ['FAKE_SOCKET_RETRY_STATE'])",
                "log_path = Path(os.environ['FAKE_SOCKET_RETRY_LOG'])",
                "count = int(state_path.read_text(encoding='utf-8')) if state_path.exists() else 0",
                "count += 1",
                "state_path.write_text(str(count), encoding='utf-8')",
                "log_path.write_text(' '.join(sys.argv[1:]), encoding='utf-8')",
                "sys.stdin.read()",
                "if count == 1:",
                "    print(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'Working on the delegated task.'}]}}))",
                "    print(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': 'API Error: The socket connection was closed unexpectedly. For more information, pass `verbose: true` in the second argument to fetch()'}]}}))",
                "    print(json.dumps({'type': 'result', 'subtype': 'success'}))",
                "    raise SystemExit(1)",
                "if '--resume' not in sys.argv[1:]:",
                "    print('missing --resume on retry', file=sys.stderr)",
                "    raise SystemExit(2)",
                "print(json.dumps({'type': 'assistant', 'message': {'role': 'assistant', 'content': [{'type': 'text', 'text': report}]}}))",
                "print(json.dumps({'type': 'result', 'subtype': 'success'}))",
            )
        ),
        encoding="utf-8",
    )
    if os.name == "nt":
        (fake_bin / "claude.cmd").write_text(
            f'@echo off\n"{sys.executable}" "{script}" %*\n',
            encoding="utf-8",
        )
    else:
        shim = fake_bin / "claude"
        shim.write_text(
            f"#!/bin/sh\nexec '{sys.executable}' '{script}' \"$@\"\n",
            encoding="utf-8",
        )
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    return fake_bin


def write_task(root: Path, name: str, text: str) -> Path:
    task_file = root / f"{name}.md"
    task_file.write_text(compliant_task(text), encoding="utf-8")
    return task_file


def run_delegate(
    task_text: str,
    args: list[str],
    artifact_root: Path,
    env: dict[str, str] | None = None,
    role: str = "implementer",
) -> subprocess.CompletedProcess[str]:
    merged_env = {
        **os.environ,
        "CODEX_CLAUDE_CHILD_THREAD": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if env:
        merged_env.update(env)
    task_file = write_task(artifact_root.parent, f"task-{len(list(artifact_root.parent.glob('task-*.md')))}", task_text)
    return subprocess.run(
        [
            sys.executable,
            str(DELEGATE),
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-edge-contract",
            "-TaskId",
            task_file.stem,
            "-Role",
            role,
            *args,
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "edge-contract",
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        env=merged_env,
    )


def run_delegate_with_default_artifact_root(task_file: Path, cwd: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(DELEGATE),
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-default-artifact-fallback",
            "-TaskId",
            "task-default-artifact-fallback",
            "-Role",
            "researcher",
            "-SessionKey",
            "default-artifact-fallback",
            "-DryRun",
        ],
        cwd=cwd,
        text=True,
        capture_output=True,
        env=env,
    )


def verify_artifacts(run_id: str, artifact_root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VERIFY_ARTIFACTS), "-RunId", run_id, "-ArtifactRoot", str(artifact_root)],
        cwd=REPO,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )


def test_custom_output_path_is_verified_from_config() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_custom_output_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        output_path = root / "custom-report.md"
        fake_bin = make_fake_claude_bin(root)
        result = run_delegate(
            "custom output path",
            ["-OutputPath", str(output_path), "-BypassPermissions"],
            artifact_root,
            {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode == 0, verified.stdout + verified.stderr
        assert f"Artifact verification passed for RunId: {run_id}" in verified.stdout


def test_delegate_does_not_pass_removed_claude_name_option() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_no_claude_name_arg_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        fake_bin = make_name_rejecting_fake_claude_bin(root)

        result = run_delegate(
            "current Claude CLI compatibility",
            ["-BypassPermissions", "-MaxRetryCount", "0"],
            artifact_root,
            {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
        )

        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        verified = verify_artifacts(run_id, artifact_root)
        assert verified.returncode == 0, verified.stdout + verified.stderr


def test_verify_artifacts_repairs_stale_running_status_from_structured_report() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_stale_status_repair_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        fake_bin = make_fake_claude_bin(root)
        result = run_delegate(
            "stale status repair",
            ["-BypassPermissions", "-MaxRetryCount", "0"],
            artifact_root,
            {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        status_path = artifact_root / f"status_{run_id}.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["status"] = "running"
        status_path.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode == 0, verified.stdout + verified.stderr
        repaired_status = json.loads(status_path.read_text(encoding="utf-8"))
        assert repaired_status["status"] == "completed"
        assert repaired_status["statusRecoveredFromReport"] is True


def test_dry_run_writes_complete_verifiable_artifacts() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_dry_run_artifacts_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        result = run_delegate("dry run artifact contract", ["-DryRun"], artifact_root)
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode == 0, verified.stdout + verified.stderr


def test_default_artifact_root_falls_back_to_codex_home_when_project_path_is_unusable() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_default_artifact_fallback_") as tmp:
        root = Path(tmp)
        project_root = root / "project"
        codex_home = root / "codex-home"
        blocked_artifact_root = project_root / ".codex" / "codex_with_cc" / "claude-delegate"
        task_root = project_root / ".codex" / "codex_with_cc" / "tasks"
        task_root.mkdir(parents=True)
        blocked_artifact_root.parent.mkdir(parents=True, exist_ok=True)
        blocked_artifact_root.write_text("not a directory", encoding="utf-8")
        task_file = write_task(task_root, "default-artifact-fallback", "default artifact fallback contract")

        result = run_delegate_with_default_artifact_root(
            task_file,
            project_root,
            {
                **os.environ,
                "CODEX_HOME": str(codex_home),
                "CODEX_CLAUDE_CHILD_THREAD": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )

        output = result.stdout + result.stderr
        assert result.returncode == 0, output
        assert "Default artifact root is not writable" in output
        artifact_root_line = next(line for line in result.stdout.splitlines() if line.startswith("Artifact Root:"))
        artifact_root = Path(artifact_root_line.split(":", 1)[1].strip())
        assert codex_home.resolve() in artifact_root.resolve().parents
        assert artifact_root != blocked_artifact_root
        run_id = run_id_from_output(result.stdout)
        config = json.loads((artifact_root / f"config_{run_id}.json").read_text(encoding="utf-8"))
        assert config["artifactRoot"] == str(artifact_root)
        assert config["artifactRootFallbackReason"]
        verified = subprocess.run(
            [sys.executable, str(VERIFY_ARTIFACTS), "-RunId", run_id],
            cwd=project_root,
            text=True,
            capture_output=True,
            env={**os.environ, "CODEX_HOME": str(codex_home), "PYTHONDONTWRITEBYTECODE": "1"},
        )
        assert verified.returncode == 0, verified.stdout + verified.stderr


def test_explicit_unusable_artifact_root_fails_with_delegation_remediation() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_unusable_artifact_root_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        artifact_root.write_text("not a directory", encoding="utf-8")

        result = run_delegate("unusable artifact root contract", ["-DryRun"], artifact_root)

        output = result.stdout + result.stderr
        assert result.returncode != 0
        assert "Artifact root is not writable" in output
        assert "-ArtifactRoot" in output
        assert "trusted local terminal fallback" in output
        assert "Do not continue the delegated task in the main thread without delegate artifacts." in output


def test_artifact_verification_rejects_status_final_result_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_report_status_mismatch_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        result = run_delegate("status mismatch contract", ["-DryRun"], artifact_root)
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        output = artifact_root / f"claude_{run_id}.md"
        output.write_text(output.read_text(encoding="utf-8").replace("Final Result\nDONE", "Final Result\nFAIL"), encoding="utf-8")

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode != 0
        assert "Final Result" in (verified.stdout + verified.stderr)


def test_artifact_verification_rejects_report_role_mismatch() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_report_role_mismatch_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        result = run_delegate("role mismatch contract", ["-DryRun"], artifact_root, role="researcher")
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        output = artifact_root / f"claude_{run_id}.md"
        output.write_text(output.read_text(encoding="utf-8").replace("Role\nresearcher", "Role\nimplementer"), encoding="utf-8")

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode != 0
        assert "role" in (verified.stdout + verified.stderr).lower()


def test_artifact_verification_rejects_text_before_status() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_report_preamble_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        result = run_delegate("report preamble contract", ["-DryRun"], artifact_root)
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        output = artifact_root / f"claude_{run_id}.md"
        output.write_text("Here is the report.\n\n" + output.read_text(encoding="utf-8"), encoding="utf-8")

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode != 0
        assert "required report headings" in (verified.stdout + verified.stderr)


def test_missing_claude_writes_complete_verifiable_failure_artifacts() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_missing_claude_") as tmp:
        artifact_root = Path(tmp) / "artifacts"
        result = run_delegate("missing claude artifact contract", [], artifact_root, {"PATH": ""})
        assert result.returncode != 0
        run_id = run_id_from_output(result.stdout)

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode == 0, verified.stdout + verified.stderr
        output = (artifact_root / f"claude_{run_id}.md").read_text(encoding="utf-8")
        assert "STARTUP_FAILURE: Claude Code CLI was not found" in output


def test_structured_output_file_allows_unstructured_final_summary() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_file_report_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        fake_bin = make_file_report_fake_claude_bin(root)
        result = run_delegate(
            "write report file and summarize",
            ["-BypassPermissions", "-MaxRetryCount", "0"],
            artifact_root,
            {"PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}"},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)

        verified = verify_artifacts(run_id, artifact_root)

        assert verified.returncode == 0, verified.stdout + verified.stderr
        output = (artifact_root / f"claude_{run_id}.md").read_text(encoding="utf-8")
        assert output == REPORT


def test_socket_close_after_progress_retries_with_resume_session() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_socket_retry_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        fake_bin = make_socket_retry_fake_claude_bin(root)
        state_path = root / "socket-retry-count.txt"
        log_path = root / "socket-retry-args.txt"
        result = run_delegate(
            "socket retry after progress",
            ["-BypassPermissions", "-MaxRetryCount", "1"],
            artifact_root,
            {
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
                "FAKE_SOCKET_RETRY_STATE": str(state_path),
                "FAKE_SOCKET_RETRY_LOG": str(log_path),
            },
        )

        assert result.returncode == 0, result.stdout + result.stderr
        run_id = run_id_from_output(result.stdout)
        verified = verify_artifacts(run_id, artifact_root)
        status = json.loads((artifact_root / f"status_{run_id}.json").read_text(encoding="utf-8"))

        assert verified.returncode == 0, verified.stdout + verified.stderr
        assert state_path.read_text(encoding="utf-8") == "2"
        assert "--resume" in log_path.read_text(encoding="utf-8")
        assert status["status"] == "completed"
        assert int(status["retryCount"]) == 1
        assert status["attempts"][0]["retryReason"] == "socket_transport_after_progress"


def test_task_fingerprint_uses_full_task_text() -> None:
    shared_prefix = "x" * 1000
    first = task_fingerprint(shared_prefix + "A", ["scope"], ["pytest"], "implementer")
    second = task_fingerprint(shared_prefix + "B", ["scope"], ["pytest"], "implementer")

    assert first != second


def test_report_headings_ignore_fenced_code_examples() -> None:
    fenced_example = f"```text\n{REPORT}\n```"
    decorated_report = "\n".join(f"**{line}**" if line in ("Status", "Role", "Summary", "Changed Files", "Verification", "Findings", "Final Result", "Risks Or Follow-ups") else line for line in REPORT.splitlines())

    assert not text_has_required_report_headings(fenced_example)
    assert not text_has_required_report_headings(decorated_report)
    assert not text_has_required_report_headings("Here is the report.\n\n" + REPORT)
    assert text_has_required_report_headings(REPORT)
