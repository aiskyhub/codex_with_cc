#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


repo = Path(__file__).resolve().parents[1]
delegate = repo / "skills" / "codex-with-cc" / "scripts" / "delegate_to_claude.py"
real_chain = repo / "skills" / "codex-with-cc" / "scripts" / "run_real_delegate_chain_validation.py"


with tempfile.TemporaryDirectory(prefix="codex_with_cc_prompt_contract_") as tmp:
    root = Path(tmp)
    artifact_root = root / "artifacts"
    prompt_run = subprocess.run(
        [
            sys.executable,
            str(delegate),
            "-Task",
            "audit the prompt contract",
            "-Scope",
            "alpha/file.txt",
            "-Tests",
            'pwsh -NoProfile -File .\\verify_delegate_artifacts.ps1 -RunId <sample-run-id> -ArtifactRoot "X"',
            "-ArtifactRoot",
            str(artifact_root),
            "-SessionKey",
            "prompt-contract",
            "-DryRun",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        env={**os.environ, "CODEX_CLAUDE_CHILD_THREAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if prompt_run.returncode != 0:
        raise AssertionError(prompt_run.stdout + prompt_run.stderr)
    config = json.loads(next(artifact_root.glob("config_*.json")).read_text(encoding="utf-8"))
    prompt = Path(config["promptPath"]).read_text(encoding="utf-8")
    assert f"Current delegate run id:\n{config['runId']}" in prompt
    assert f"replace it with the current delegate run id `{config['runId']}` before you execute the command." in prompt
    assert f"Never inspect, poll, or wait on the current run's own live artifacts (`status_{config['runId']}.json`" in prompt
    assert "Never add sleeps or \"wait for completion\" loops for the current run." in prompt
    assert "- alpha/file.txt" in prompt
    assert '- pwsh -NoProfile -File .\\verify_delegate_artifacts.ps1 -RunId <sample-run-id> -ArtifactRoot "X"' in prompt

    validation_root = root / "validation"
    chain_run = subprocess.run(
        [
            sys.executable,
            str(real_chain),
            "-ValidationRoot",
            str(validation_root),
            "-Name",
            "contract-check",
            "-SessionKey",
            "contract-session",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if chain_run.returncode != 0:
        raise AssertionError(chain_run.stdout + chain_run.stderr)
    task_file = next((validation_root / "contract-check" / "tasks").rglob("*anchor-read-protocol.md"))
    task_text = task_file.read_text(encoding="utf-8")
    assert '-Scope "' in task_text
    assert 'windows_scripts/delegate_to_claude.ps1"' in task_text
    assert 'CODEX_WITH_CC.md"' in task_text
    assert "-Tests 'pwsh -NoProfile -File .\\" in task_text
    assert "verify_delegate_artifacts.ps1 -RunId <anchor-read-protocol-run-id>" in task_text


print("delegate prompt and real chain contract tests passed")
