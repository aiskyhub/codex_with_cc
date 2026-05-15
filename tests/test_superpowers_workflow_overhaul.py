#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from tests.task_helpers import compliant_task


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "skills" / "codex-with-cc" / "scripts"
DELEGATE = SCRIPTS / "delegate_to_claude.py"
VALIDATE_TASK = SCRIPTS / "validate_delegate_task.py"
VERIFY_ARTIFACTS = SCRIPTS / "verify_delegate_artifacts.py"
VERIFY_WORKFLOW = SCRIPTS / "verify_delegate_workflow.py"


def write_task(root: Path, name: str, text: str = "dry run delegated task") -> Path:
    task = root / f"{name}.md"
    task.write_text(compliant_task(text), encoding="utf-8")
    return task


def write_raw_task(root: Path, name: str, text: str) -> Path:
    task = root / f"{name}.md"
    task.write_text(text, encoding="utf-8")
    return task


def run_python(script: Path, *args: str, cwd: Path = REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(script), *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        env={**os.environ, "CODEX_CLAUDE_CHILD_THREAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )


def run_id_from_output(output: str) -> str:
    for line in output.splitlines():
        if line.startswith("RunId:"):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"RunId line missing from output:\n{output}")


def run_delegate(root: Path, artifact_root: Path, task_id: str, role: str, *extra: str) -> subprocess.CompletedProcess[str]:
    task_file = write_task(root, task_id, f"{task_id} delegated task")
    return run_python(
        DELEGATE,
        "-TaskFile",
        str(task_file),
        "-WorkflowId",
        "wf-review-gate",
        "-TaskId",
        task_id,
        "-Role",
        role,
        "-SessionKey",
        "review-gate",
        "-ArtifactRoot",
        str(artifact_root),
        *extra,
        "-DryRun",
    )


def make_fake_claude_bin(root: Path, role: str, verification: str) -> Path:
    fake_bin = root / "fake-claude-bin"
    fake_bin.mkdir(parents=True, exist_ok=True)
    report = "\n".join(
        (
            "Status",
            "DONE",
            "",
            "Role",
            role,
            "",
            "Summary",
            "Fake Claude completed the delegated task.",
            "",
            "Changed Files",
            "None",
            "",
            "Verification",
            verification,
            "",
            "Findings",
            "None",
            "",
            "Final Result",
            "DONE",
            "",
            "Risks Or Follow-ups",
            "None",
        )
    )
    assistant_record = json.dumps(
        {"type": "assistant", "message": {"role": "assistant", "content": [{"type": "text", "text": report}]}},
        separators=(",", ":"),
    )
    result_record = json.dumps({"type": "result", "subtype": "success"}, separators=(",", ":"))
    if os.name == "nt":
        (fake_bin / "claude.cmd").write_text(
            '@echo off\n'
            'more > nul\n'
            f"echo {assistant_record}\n"
            f"echo {result_record}\n"
            "exit /b 0\n",
            encoding="utf-8",
        )
    else:
        script = fake_bin / "claude"
        script.write_text(
            "#!/usr/bin/env sh\n"
            "cat >/dev/null\n"
            f"printf '%s\\n' '{assistant_record}'\n"
            f"printf '%s\\n' '{result_record}'\n",
            encoding="utf-8",
        )
        script.chmod(0o755)
    return fake_bin


def test_task_file_contract_rejects_empty_sections_placeholders_and_incomplete_report_requirements() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_task_contract_strict_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        empty_goal = write_raw_task(
            root,
            "empty-goal",
            """# Bad Task

Goal

Allowed Scope
- skills/codex-with-cc

Forbidden Actions
- Do not edit README.md.

Acceptance Criteria
- The task stays inside scope.

Verification
- pytest -q

Report Requirements
- Status / Role / Summary
""",
        )
        rejected_empty = run_python(
            VALIDATE_TASK,
            "-TaskFile",
            str(empty_goal),
            "-Role",
            "researcher",
            "-Tests",
            "pytest -q",
        )
        assert rejected_empty.returncode != 0
        assert "Goal" in (rejected_empty.stdout + rejected_empty.stderr)

        placeholder = write_raw_task(
            root,
            "placeholder",
            compliant_task("TODO fill in later", "pytest -q"),
        )
        rejected_placeholder = run_python(
            VALIDATE_TASK,
            "-TaskFile",
            str(placeholder),
            "-Role",
            "researcher",
            "-Tests",
            "pytest -q",
        )
        assert rejected_placeholder.returncode != 0
        assert "placeholder" in (rejected_placeholder.stdout + rejected_placeholder.stderr).lower()

        valid = write_task(root, "valid", "validate strict task contract")
        accepted = run_python(VALIDATE_TASK, "-TaskFile", str(valid), "-Role", "researcher")
        assert accepted.returncode == 0, accepted.stdout + accepted.stderr


def test_delegate_rejects_old_inline_task_and_requires_metadata() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_cli_contract_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        task_file = write_task(root, "research")

        old_inline = run_python(
            DELEGATE,
            "-Task",
            "old inline task",
            "-WorkflowId",
            "wf-cli-contract",
            "-TaskId",
            "task-inline",
            "-Role",
            "researcher",
            "-SessionKey",
            "cli-contract",
            "-ArtifactRoot",
            str(artifact_root),
            "-DryRun",
        )
        assert old_inline.returncode != 0
        assert "TaskFile" in (old_inline.stdout + old_inline.stderr)

        missing_workflow = run_python(
            DELEGATE,
            "-TaskFile",
            str(task_file),
            "-TaskId",
            "task-missing-workflow",
            "-Role",
            "researcher",
            "-SessionKey",
            "cli-contract",
            "-ArtifactRoot",
            str(artifact_root),
            "-DryRun",
        )
        assert missing_workflow.returncode != 0
        assert "WorkflowId" in (missing_workflow.stdout + missing_workflow.stderr)

        missing_session = run_python(
            DELEGATE,
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-cli-contract",
            "-TaskId",
            "task-missing-session",
            "-Role",
            "researcher",
            "-ArtifactRoot",
            str(artifact_root),
            "-DryRun",
        )
        assert missing_session.returncode != 0
        assert "SessionKey" in (missing_session.stdout + missing_session.stderr)

        legacy_mode = run_python(
            DELEGATE,
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-cli-contract",
            "-TaskId",
            "task-legacy-mode",
            "-Role",
            "researcher",
            "-SessionKey",
            "cli-contract",
            "-Mode",
            "Review",
            "-ArtifactRoot",
            str(artifact_root),
            "-DryRun",
        )
        assert legacy_mode.returncode != 0
        assert "Mode" in (legacy_mode.stdout + legacy_mode.stderr)

        compliant = run_python(
            DELEGATE,
            "-TaskFile",
            str(task_file),
            "-WorkflowId",
            "wf-cli-contract",
            "-TaskId",
            "task-research",
            "-Role",
            "researcher",
            "-SessionKey",
            "cli-contract",
            "-ArtifactRoot",
            str(artifact_root),
            "-DryRun",
        )
        assert compliant.returncode == 0, compliant.stdout + compliant.stderr
        run_id = run_id_from_output(compliant.stdout)

        verified = run_python(VERIFY_ARTIFACTS, "-RunId", run_id, "-ArtifactRoot", str(artifact_root))

        assert verified.returncode == 0, verified.stdout + verified.stderr

        output = artifact_root / f"claude_{run_id}.md"
        output.write_text(
            output.read_text(encoding="utf-8").replace(
                f"Verification\n- dry-run artifact generation completed for RunId {run_id}",
                "Verification\nNone",
            ),
            encoding="utf-8",
        )
        missing_evidence = run_python(VERIFY_ARTIFACTS, "-RunId", run_id, "-ArtifactRoot", str(artifact_root))

        assert missing_evidence.returncode != 0
        assert "verification evidence" in (missing_evidence.stdout + missing_evidence.stderr).lower()


def test_workflow_verifier_requires_spec_and_quality_review_for_implementers() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_review_gate_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"

        implementer = run_delegate(root, artifact_root, "task-implement", "implementer")
        assert implementer.returncode == 0, implementer.stdout + implementer.stderr

        missing_reviews = run_python(
            VERIFY_WORKFLOW,
            "-WorkflowId",
            "wf-review-gate",
            "-ArtifactRoot",
            str(artifact_root),
        )

        assert missing_reviews.returncode != 0
        assert "spec" in (missing_reviews.stdout + missing_reviews.stderr).lower()
        assert "quality" in (missing_reviews.stdout + missing_reviews.stderr).lower()

        for review_kind in ("spec", "quality"):
            reviewer = run_delegate(
                root,
                artifact_root,
                f"task-{review_kind}-review",
                "reviewer",
                "-ReviewForTaskId",
                "task-implement",
                "-ReviewKind",
                review_kind,
            )
            assert reviewer.returncode == 0, reviewer.stdout + reviewer.stderr

        missing_final = run_python(
            VERIFY_WORKFLOW,
            "-WorkflowId",
            "wf-review-gate",
            "-ArtifactRoot",
            str(artifact_root),
        )
        assert missing_final.returncode != 0
        assert "final-verifier" in (missing_final.stdout + missing_final.stderr)

        final = run_delegate(root, artifact_root, "task-final-verifier", "final-verifier")
        assert final.returncode == 0, final.stdout + final.stderr

        reviewed = run_python(
            VERIFY_WORKFLOW,
            "-WorkflowId",
            "wf-review-gate",
            "-ArtifactRoot",
            str(artifact_root),
        )

        assert reviewed.returncode == 0, reviewed.stdout + reviewed.stderr


def test_workflow_verifier_requires_declared_tests_in_done_reports() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_declared_tests_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        fake_bin = make_fake_claude_bin(root, "implementer", "- fake verification passed")
        task_file = write_task(root, "task-implement", "Implement with declared verification.")
        implementer = subprocess.run(
            [
                sys.executable,
                str(DELEGATE),
                "-TaskFile",
                str(task_file),
                "-WorkflowId",
                "wf-review-gate",
                "-TaskId",
                "task-implement",
                "-Role",
                "implementer",
                "-SessionKey",
                "review-gate",
                "-Tests",
                "pytest -q",
                "-ArtifactRoot",
                str(artifact_root),
            ],
            cwd=REPO,
            text=True,
            capture_output=True,
            env={
                **os.environ,
                "CODEX_CLAUDE_CHILD_THREAD": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": f"{fake_bin}{os.pathsep}{os.environ.get('PATH', '')}",
            },
        )
        assert implementer.returncode == 0, implementer.stdout + implementer.stderr
        for review_kind in ("spec", "quality"):
            reviewer = run_delegate(
                root,
                artifact_root,
                f"task-{review_kind}-review",
                "reviewer",
                "-ReviewForTaskId",
                "task-implement",
                "-ReviewKind",
                review_kind,
            )
            assert reviewer.returncode == 0, reviewer.stdout + reviewer.stderr
        final = run_delegate(root, artifact_root, "task-final-verifier", "final-verifier")
        assert final.returncode == 0, final.stdout + final.stderr

        missing_test_evidence = run_python(
            VERIFY_WORKFLOW,
            "-WorkflowId",
            "wf-review-gate",
            "-ArtifactRoot",
            str(artifact_root),
        )
        assert missing_test_evidence.returncode != 0
        assert "pytest -q" in (missing_test_evidence.stdout + missing_test_evidence.stderr)


def test_workflow_verifier_rejects_overlapping_parallel_implementer_scope() -> None:
    with tempfile.TemporaryDirectory(prefix="codex_with_cc_parallel_scope_") as tmp:
        root = Path(tmp)
        artifact_root = root / "artifacts"
        for task_id, scope in (("task-a", "src/shared"), ("task-b", "src/shared/module.py")):
            implementer = run_delegate(
                root,
                artifact_root,
                task_id,
                "implementer",
                "-Scope",
                scope,
                "-AllowParallel",
            )
            assert implementer.returncode == 0, implementer.stdout + implementer.stderr
            for review_kind in ("spec", "quality"):
                reviewer = run_delegate(
                    root,
                    artifact_root,
                    f"{task_id}-{review_kind}-review",
                    "reviewer",
                    "-ReviewForTaskId",
                    task_id,
                    "-ReviewKind",
                    review_kind,
                )
                assert reviewer.returncode == 0, reviewer.stdout + reviewer.stderr
        same_scope_researcher = run_delegate(
            root,
            artifact_root,
            "task-researcher",
            "researcher",
            "-Scope",
            "src/shared/module.py",
            "-AllowParallel",
        )
        assert same_scope_researcher.returncode == 0, same_scope_researcher.stdout + same_scope_researcher.stderr
        final = run_delegate(root, artifact_root, "task-final-verifier", "final-verifier")
        assert final.returncode == 0, final.stdout + final.stderr

        overlap = run_python(
            VERIFY_WORKFLOW,
            "-WorkflowId",
            "wf-review-gate",
            "-ArtifactRoot",
            str(artifact_root),
        )
        assert overlap.returncode != 0
        assert "overlapping parallel implementer scope" in (overlap.stdout + overlap.stderr).lower()
