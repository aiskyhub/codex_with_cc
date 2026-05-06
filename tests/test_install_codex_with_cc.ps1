$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $repoRoot 'codex_with_cc\windows_scripts\test_helpers.ps1')

$installerPath = Join-Path $repoRoot 'install_codex_with_cc.ps1'
$sourceWorkflowRoot = Join-Path $repoRoot 'codex_with_cc'
$legacyTemplatesRoot = Join-Path $repoRoot 'templates'
$tempRoot = Join-Path ([System.IO.Path]::GetTempPath()) "codex_with_cc_install_$([guid]::NewGuid().ToString('N'))"
$targetRoot = Join-Path $tempRoot 'host-project'

try {
  New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $targetRoot 'README.md') -Value '# Host Project' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $targetRoot '.gitignore') -Value @"
build
.claude
"@ -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $targetRoot 'AGENTS.md') -Value @"
# Existing Host Instructions

Keep this project-specific rule.
"@ -Encoding UTF8

  Assert-True -Condition (Test-Path -LiteralPath $installerPath) -Name 'installer-exists'
  Assert-True -Condition (Test-Path -LiteralPath $sourceWorkflowRoot) -Name 'source-workflow-root-exists-at-repo-root'
  Assert-True -Condition (-not (Test-Path -LiteralPath $legacyTemplatesRoot)) -Name 'legacy-templates-root-removed'

  $installOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $targetRoot -Platform Windows 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "installer failed unexpectedly.`n$($installOutput -join [Environment]::NewLine)"
  }

  $workflowRoot = Join-Path $targetRoot 'docs\codex_with_cc'
  $taskRoot = Join-Path $targetRoot '.codex\codex_with_cc\tasks'
  Assert-True -Condition (Test-Path -LiteralPath $workflowRoot) -Name 'workflow-root-created'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $workflowRoot 'CODEX_WITH_CC.md')) -Name 'codex-with-cc-entry-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'CLAUDE_CODE_DELEGATION.md'))) -Name 'delegation-doc-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'HOST_PROJECT_RULES.md'))) -Name 'host-rules-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'PROJECT_MEMORY.md'))) -Name 'project-memory-not-created'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $workflowRoot 'windows_scripts\delegate_to_claude.ps1')) -Name 'delegate-script-created'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $workflowRoot 'windows_scripts\verify_delegate_chain.ps1')) -Name 'chain-verifier-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'scripts'))) -Name 'legacy-scripts-dir-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'macos_scripts'))) -Name 'windows-install-does-not-copy-macos-scripts'
  Assert-True -Condition (Test-Path -LiteralPath $taskRoot) -Name 'tasks-dir-created-under-codex-root'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.gitkeep'))) -Name 'tasks-gitkeep-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'docs\ai'))) -Name 'legacy-docs-ai-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'docs\scripts\ai'))) -Name 'legacy-docs-scripts-ai-not-created'
  $gitIgnoreText = Get-Content -LiteralPath (Join-Path $targetRoot '.gitignore') -Raw
  $gitIgnoreLines = @($gitIgnoreText -split "\r?\n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) } | ForEach-Object { $_.Trim() })
  Assert-True -Condition ($gitIgnoreLines -contains '.codex/codex_with_cc') -Name 'gitignore-contains-targeted-codex-with-cc-entry'
  Assert-True -Condition (-not ($gitIgnoreLines -contains '.codex')) -Name 'gitignore-does-not-ignore-shared-codex-root'
  Assert-True -Condition (-not ($gitIgnoreLines -contains '.codex/')) -Name 'gitignore-does-not-ignore-shared-codex-root-slash'

  $agentsText = Get-Content -LiteralPath (Join-Path $targetRoot 'AGENTS.md') -Raw
  Assert-Contains -Text $agentsText -Needle 'Keep this project-specific rule.' -Name 'existing-agents-content-preserved'
  Assert-Contains -Text $agentsText -Needle '<!-- BEGIN CODEX_WITH_CC -->' -Name 'agents-managed-block-added'
  Assert-Contains -Text $agentsText -Needle 'docs/codex_with_cc/CODEX_WITH_CC.md' -Name 'agents-managed-block-points-to-central-entry'
  Assert-Contains -Text $agentsText -Needle '`docs/codex_with_cc/CODEX_WITH_CC.md`' -Name 'agents-managed-block-keeps-markdown-code-format'
  Assert-Contains -Text $agentsText -Needle 'If the task involves child agents, subagents, delegation, or any worker-execution step, you must read that file first' -Name 'agents-managed-block-requires-reading-workflow-before-subagent-logic'
  Assert-Contains -Text $agentsText -Needle 'Codex main thread -> Codex child agent -> delegate_to_claude.* -> Claude Code CLI' -Name 'agents-managed-block-points-to-custom-subagent-chain'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'CLAUDE.md'))) -Name 'claude-entrypoint-not-created'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $targetRoot 'GEMINI.md'))) -Name 'gemini-entrypoint-not-created'
  Assert-Contains -Text ($installOutput -join [Environment]::NewLine) -Needle 'Agent entrypoints updated: AGENTS.md' -Name 'install-output-lists-only-agents'

  $delegateText = Get-Content -LiteralPath (Join-Path $workflowRoot 'windows_scripts\delegate_to_claude.ps1') -Raw
  Assert-Contains -Text $delegateText -Needle 'docs/codex_with_cc/CODEX_WITH_CC.md' -Name 'delegate-uses-central-workflow-entry'
  Assert-Contains -Text $delegateText -Needle 'docs/codex_with_cc/windows_scripts/delegate_to_claude.ps1' -Name 'delegate-prompt-uses-central-script-path'
  Assert-NotContains -Text $delegateText -Needle 'docs/codex_with_cc/CLAUDE_CODE_DELEGATION.md' -Name 'delegate-does-not-use-delegation-sidecar-doc'
  Assert-NotContains -Text $delegateText -Needle 'docs/codex_with_cc/PROJECT_MEMORY.md' -Name 'delegate-does-not-use-central-project-memory'
  Assert-NotContains -Text $delegateText -Needle 'docs/codex_with_cc/HOST_PROJECT_RULES.md' -Name 'delegate-does-not-use-host-project-rules'
  Assert-NotContains -Text $delegateText -Needle 'SmartDialog' -Name 'delegate-does-not-include-easy-kit-ui-rule'
  Assert-NotContains -Text $delegateText -Needle 'pubspec.yaml' -Name 'delegate-does-not-include-easy-kit-pubspec-rule'
  Assert-NotContains -Text $delegateText -Needle 'docs/ai/PROJECT_MEMORY.md' -Name 'delegate-does-not-use-legacy-project-memory-path'
  Assert-NotContains -Text $delegateText -Needle 'D:\Develop\GitHub\easy_kit' -Name 'delegate-does-not-hardcode-easy-kit-path'

  Set-Content -LiteralPath (Join-Path $workflowRoot 'obsolete.txt') -Value 'stale' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $workflowRoot 'HOST_PROJECT_RULES.md') -Value 'stale host rules' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $workflowRoot 'PROJECT_MEMORY.md') -Value 'stale project memory' -Encoding UTF8
  $staleDocWorkflowRoot = Join-Path $targetRoot 'doc\codex_with_cc'
  New-Item -ItemType Directory -Path $staleDocWorkflowRoot -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $staleDocWorkflowRoot 'obsolete.txt') -Value 'stale doc workflow' -Encoding UTF8
  Set-Content -LiteralPath (Join-Path $targetRoot 'doc\keep.md') -Value 'keep doc content' -Encoding UTF8
  New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $taskRoot '.gitkeep') -Value '' -Encoding UTF8

  $reinstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $targetRoot -Platform Windows 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "reinstall failed unexpectedly.`n$($reinstallOutput -join [Environment]::NewLine)"
  }

  $agentsTextAfterReinstall = Get-Content -LiteralPath (Join-Path $targetRoot 'AGENTS.md') -Raw
  $managedBlockCount = ([regex]::Matches($agentsTextAfterReinstall, '<!-- BEGIN CODEX_WITH_CC -->')).Count
  Assert-True -Condition ($managedBlockCount -eq 1) -Name 'reinstall-keeps-one-managed-block'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'obsolete.txt'))) -Name 'reinstall-removes-obsolete-file'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'HOST_PROJECT_RULES.md'))) -Name 'reinstall-removes-stale-host-rules'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $workflowRoot 'PROJECT_MEMORY.md'))) -Name 'reinstall-removes-stale-project-memory'
  Assert-True -Condition (-not (Test-Path -LiteralPath $staleDocWorkflowRoot)) -Name 'reinstall-removes-stale-doc-workflow'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $targetRoot 'doc\keep.md')) -Name 'reinstall-preserves-doc-sibling-content'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.gitkeep'))) -Name 'reinstall-removes-stale-gitkeep'
  Assert-True -Condition (Test-Path -LiteralPath $taskRoot) -Name 'reinstall-recreates-tasks-dir'

  $docOnlyTargetRoot = Join-Path $tempRoot 'doc-only-host-project'
  New-Item -ItemType Directory -Path (Join-Path $docOnlyTargetRoot 'doc') -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $docOnlyTargetRoot 'AGENTS.md') -Value '# Doc Only Host' -Encoding UTF8
  $docOnlyInstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $docOnlyTargetRoot -Platform Windows 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "doc-only installer failed unexpectedly.`n$($docOnlyInstallOutput -join [Environment]::NewLine)"
  }
  $docOnlyWorkflowRoot = Join-Path $docOnlyTargetRoot 'doc\codex_with_cc'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $docOnlyWorkflowRoot 'CODEX_WITH_CC.md')) -Name 'doc-only-install-uses-doc-workflow-root'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $docOnlyTargetRoot 'docs'))) -Name 'doc-only-install-does-not-create-docs-root'
  Assert-Contains -Text ($docOnlyInstallOutput -join [Environment]::NewLine) -Needle "codex_with_cc installed into: $docOnlyWorkflowRoot" -Name 'doc-only-output-uses-doc-workflow-root'
  Assert-Contains -Text ($docOnlyInstallOutput -join [Environment]::NewLine) -Needle 'Next: read doc/codex_with_cc/CODEX_WITH_CC.md' -Name 'doc-only-next-step-uses-doc-relative-path'
  $docOnlyAgentsText = Get-Content -LiteralPath (Join-Path $docOnlyTargetRoot 'AGENTS.md') -Raw
  Assert-Contains -Text $docOnlyAgentsText -Needle 'doc/codex_with_cc/CODEX_WITH_CC.md' -Name 'doc-only-agents-block-points-to-doc-entry'
  $docOnlyDelegateText = Get-Content -LiteralPath (Join-Path $docOnlyWorkflowRoot 'windows_scripts\delegate_to_claude.ps1') -Raw
  Assert-Contains -Text $docOnlyDelegateText -Needle 'doc/codex_with_cc/CODEX_WITH_CC.md' -Name 'doc-only-delegate-prompt-uses-doc-entry'

  $bothDocsTargetRoot = Join-Path $tempRoot 'both-docs-host-project'
  New-Item -ItemType Directory -Path (Join-Path $bothDocsTargetRoot 'docs') -Force | Out-Null
  New-Item -ItemType Directory -Path (Join-Path $bothDocsTargetRoot 'doc') -Force | Out-Null
  $bothDocsInstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $bothDocsTargetRoot -Platform Windows -SkipAgentEntrypoints 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "both-docs installer failed unexpectedly.`n$($bothDocsInstallOutput -join [Environment]::NewLine)"
  }
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $bothDocsTargetRoot 'docs\codex_with_cc\CODEX_WITH_CC.md')) -Name 'both-docs-install-prefers-docs-root'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $bothDocsTargetRoot 'doc\codex_with_cc'))) -Name 'both-docs-install-does-not-install-into-doc-root'

  $docsFileTargetRoot = Join-Path $tempRoot 'docs-file-host-project'
  New-Item -ItemType Directory -Path $docsFileTargetRoot -Force | Out-Null
  Set-Content -LiteralPath (Join-Path $docsFileTargetRoot 'docs') -Value 'not a directory' -Encoding UTF8
  $docsFileInstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $docsFileTargetRoot -Platform Windows -SkipAgentEntrypoints 2>&1
  Assert-True -Condition ($LASTEXITCODE -ne 0) -Name 'docs-file-target-fails'
  Assert-Contains -Text ($docsFileInstallOutput -join [Environment]::NewLine) -Needle 'Install document path is not a directory' -Name 'docs-file-target-error-is-clear'

  $selfInstallRoot = Join-Path $tempRoot 'self-install-source'
  New-Item -ItemType Directory -Path $selfInstallRoot -Force | Out-Null
  Copy-Item -LiteralPath $installerPath -Destination (Join-Path $selfInstallRoot 'install_codex_with_cc.ps1') -Force
  Copy-Item -LiteralPath $sourceWorkflowRoot -Destination (Join-Path $selfInstallRoot 'codex_with_cc') -Recurse -Force
  $selfInstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File (Join-Path $selfInstallRoot 'install_codex_with_cc.ps1') -TargetRoot $selfInstallRoot 2>&1
  Assert-True -Condition ($LASTEXITCODE -ne 0) -Name 'self-install-refuses-source-target-overlap'
  Assert-Contains -Text ($selfInstallOutput -join [Environment]::NewLine) -Needle 'Refusing to install codex_with_cc into its own source repository' -Name 'self-install-error-is-clear'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $selfInstallRoot 'codex_with_cc\CODEX_WITH_CC.md')) -Name 'self-install-keeps-source-workflow'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $selfInstallRoot 'codex_with_cc\windows_scripts\delegate_to_claude.ps1')) -Name 'self-install-keeps-source-scripts'

  $macTargetRoot = Join-Path $tempRoot 'mac-host-project'
  New-Item -ItemType Directory -Path (Join-Path $macTargetRoot 'doc') -Force | Out-Null
  $macInstallOutput = & pwsh -NoProfile -ExecutionPolicy Bypass -File $installerPath -TargetRoot $macTargetRoot -Platform macOS -SkipAgentEntrypoints 2>&1
  if ($LASTEXITCODE -ne 0) {
    throw "mac installer failed unexpectedly.`n$($macInstallOutput -join [Environment]::NewLine)"
  }
  $macWorkflowRoot = Join-Path $macTargetRoot 'doc\codex_with_cc'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $macWorkflowRoot 'CODEX_WITH_CC.md')) -Name 'mac-install-copies-workflow-doc'
  Assert-True -Condition (Test-Path -LiteralPath (Join-Path $macWorkflowRoot 'macos_scripts\README.md')) -Name 'mac-install-copies-macos-scripts'
  Assert-True -Condition (-not (Test-Path -LiteralPath (Join-Path $macWorkflowRoot 'windows_scripts'))) -Name 'mac-install-does-not-copy-windows-scripts'
  $macReadmeText = Get-Content -LiteralPath (Join-Path $macWorkflowRoot 'macos_scripts\README.md') -Raw
  Assert-Contains -Text $macReadmeText -Needle 'source repository''s `codex_with_cc/windows_scripts`' -Name 'mac-placeholder-points-to-source-windows-reference'

  Write-Host 'install tests passed' -ForegroundColor Green
} finally {
  if (Test-Path -LiteralPath $tempRoot) {
    Remove-Item -LiteralPath $tempRoot -Recurse -Force
  }
}
