# Verification

Use these commands to validate the delegate runtime and workflow artifacts after changing codex-with-cc.

```powershell
python -m pytest -q
pwsh -NoProfile -File .\skills\codex-with-cc\windows_scripts\test_delegate_runtime.ps1
pwsh -NoProfile -File .\skills\codex-with-cc\windows_scripts\test_delegate_session_pool.ps1
pwsh -NoProfile -File .\skills\codex-with-cc\windows_scripts\run_real_delegate_chain_validation.ps1 -ValidationRoot .\build\codex-with-cc-real-flow
```

For completed worker runs, verify each `RunId` and the workflow aggregate:

```powershell
pwsh -NoProfile -File .\skills\codex-with-cc\windows_scripts\verify_delegate_artifacts.ps1 -RunId <RunId> -ArtifactRoot <ArtifactRoot>
pwsh -NoProfile -File .\skills\codex-with-cc\windows_scripts\verify_delegate_workflow.ps1 -WorkflowId <WorkflowId> -ArtifactRoot <ArtifactRoot>
```

On macOS, use the matching scripts under `skills/codex-with-cc/macos_scripts/`.
