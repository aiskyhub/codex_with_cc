param(
  [string]$TargetRoot = (Get-Location).Path,
  [ValidateSet('Auto', 'Windows', 'macOS')]
  [string]$Platform = 'Auto',
  [switch]$Force,
  [switch]$SkipAgentEntrypoints
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Get-FullPath {
  param([Parameter(Mandatory = $true)][string]$Path)
  return [System.IO.Path]::GetFullPath($Path)
}

function Test-PathInside {
  param(
    [Parameter(Mandatory = $true)][string]$Child,
    [Parameter(Mandatory = $true)][string]$Parent
  )

  $fullChild = Get-FullPath -Path $Child
  $fullParent = (Get-FullPath -Path $Parent).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
  return $fullChild.StartsWith($fullParent + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
}

function Resolve-InstallPlatform {
  param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Auto', 'Windows', 'macOS')]
    [string]$Platform
  )

  if ($Platform -ne 'Auto') {
    return $Platform
  }

  if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::Windows)) {
    return 'Windows'
  }

  if ([System.Runtime.InteropServices.RuntimeInformation]::IsOSPlatform([System.Runtime.InteropServices.OSPlatform]::OSX)) {
    return 'macOS'
  }

  throw 'Unsupported install platform. Pass -Platform Windows or -Platform macOS explicitly.'
}

function Test-InstallDocumentDirectory {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )

  if (-not (Test-Path -LiteralPath $Path)) {
    return $false
  }

  $item = Get-Item -LiteralPath $Path -Force
  if (-not $item.PSIsContainer) {
    throw "Install document path is not a directory: $Path"
  }

  return $true
}

function Get-WorkflowRelativePath {
  param(
    [Parameter(Mandatory = $true)][string]$DocumentRoot
  )

  return ('{0}/codex_with_cc' -f (Split-Path -Leaf $DocumentRoot))
}

function Update-AgentEntrypoint {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$WorkflowRelativePath
  )

  $begin = '<!-- BEGIN CODEX_WITH_CC -->'
  $end = '<!-- END CODEX_WITH_CC -->'
  $block = @(
    $begin
    "Codex with Claude Code workflow: before using this workflow, read ``$WorkflowRelativePath/CODEX_WITH_CC.md``."
    'If the task involves child agents, subagents, delegation, or any worker-execution step, you must read that file first and follow the custom `Codex main thread -> Codex child agent -> delegate_to_claude.* -> Claude Code CLI` workflow defined there.'
    $end
  ) -join [Environment]::NewLine

  if (Test-Path -LiteralPath $Path) {
    $text = Get-Content -LiteralPath $Path -Raw
    $pattern = '(?s)<!-- BEGIN CODEX_WITH_CC -->.*?<!-- END CODEX_WITH_CC -->'
    if ($text -match $pattern) {
      $updated = [regex]::Replace($text, $pattern, [System.Text.RegularExpressions.MatchEvaluator]{ param($m) $block })
    } else {
      $updated = $text.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block + [Environment]::NewLine
    }
  } else {
    $updated = $block + [Environment]::NewLine
  }

  [System.IO.File]::WriteAllText($Path, $updated, (New-Object System.Text.UTF8Encoding($false)))
}

function Update-InstalledWorkflowReferences {
  param(
    [Parameter(Mandatory = $true)][string]$WorkflowRoot,
    [Parameter(Mandatory = $true)][string]$WorkflowRelativePath
  )

  $canonicalRelativePath = 'docs/codex_with_cc'
  if ($WorkflowRelativePath -eq $canonicalRelativePath) {
    return
  }

  $canonicalWindowsPath = $canonicalRelativePath.Replace('/', '\')
  $workflowWindowsPath = $WorkflowRelativePath.Replace('/', '\')
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  foreach ($file in Get-ChildItem -LiteralPath $WorkflowRoot -Recurse -File -Force) {
    if ($file.Extension -notin @('.md', '.ps1')) {
      continue
    }

    $text = Get-Content -LiteralPath $file.FullName -Raw
    $updated = $text.Replace($canonicalRelativePath, $WorkflowRelativePath).Replace($canonicalWindowsPath, $workflowWindowsPath)
    if ($updated -ne $text) {
      [System.IO.File]::WriteAllText($file.FullName, $updated, $utf8NoBom)
    }
  }
}

function Update-GitIgnore {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )

  $entry = '.codex/codex_with_cc'
  if (Test-Path -LiteralPath $Path) {
    $text = Get-Content -LiteralPath $Path -Raw
    $lines = @($text -split "\r?\n")
    $hasCodexIgnore = $false
    foreach ($line in $lines) {
      $normalizedLine = $line.Trim()
      if ($normalizedLine -eq $entry -or $normalizedLine -eq '.codex/codex_with_cc/') {
        $hasCodexIgnore = $true
        break
      }
    }

    if ($hasCodexIgnore) {
      return
    }

    $updated = $text.TrimEnd()
    if ($updated.Length -gt 0) {
      $updated += [Environment]::NewLine
    }
    $updated += $entry + [Environment]::NewLine
  } else {
    $updated = $entry + [Environment]::NewLine
  }

  [System.IO.File]::WriteAllText($Path, $updated, (New-Object System.Text.UTF8Encoding($false)))
}

$installerRoot = $PSScriptRoot
$installPlatform = Resolve-InstallPlatform -Platform $Platform
$resolvedInstallerRoot = Get-FullPath -Path $installerRoot
$sourceWorkflowRoot = Join-Path $installerRoot 'codex_with_cc'
if (-not (Test-Path -LiteralPath $sourceWorkflowRoot)) {
  throw "Workflow source was not found: $sourceWorkflowRoot"
}
$resolvedSourceWorkflowRoot = (Resolve-Path -LiteralPath $sourceWorkflowRoot).Path

$resolvedTargetRoot = Get-FullPath -Path $TargetRoot
if (-not (Test-Path -LiteralPath $resolvedTargetRoot)) {
  New-Item -ItemType Directory -Path $resolvedTargetRoot -Force | Out-Null
}
$resolvedTargetRoot = (Resolve-Path -LiteralPath $resolvedTargetRoot).Path

if ([string]::Equals($resolvedInstallerRoot, $resolvedTargetRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to install codex_with_cc into its own source repository. Choose a different -TargetRoot so the installer does not modify its source repository: $resolvedInstallerRoot"
}

$docsCandidateRoot = Join-Path $resolvedTargetRoot 'docs'
$docCandidateRoot = Join-Path $resolvedTargetRoot 'doc'
$hasDocsRoot = Test-InstallDocumentDirectory -Path $docsCandidateRoot
$hasDocRoot = Test-InstallDocumentDirectory -Path $docCandidateRoot
$docsRoot = if ($hasDocsRoot -or -not $hasDocRoot) { $docsCandidateRoot } else { $docCandidateRoot }
$workflowRelativePath = Get-WorkflowRelativePath -DocumentRoot $docsRoot
$workflowRoot = Join-Path $docsRoot 'codex_with_cc'
$codexRoot = Join-Path $resolvedTargetRoot '.codex'
$taskRoot = Join-Path $codexRoot 'codex_with_cc\tasks'
$resolvedWorkflowRoot = [System.IO.Path]::GetFullPath($workflowRoot)

if ([string]::Equals($resolvedSourceWorkflowRoot, $resolvedWorkflowRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "Refusing to install codex_with_cc into its own source repository. Choose a different -TargetRoot so the installer does not remove its source workflow directory: $resolvedSourceWorkflowRoot"
}

foreach ($candidateWorkflowRoot in @((Join-Path $docsCandidateRoot 'codex_with_cc'), (Join-Path $docCandidateRoot 'codex_with_cc'))) {
  if (Test-Path -LiteralPath $candidateWorkflowRoot) {
    if (-not (Test-PathInside -Child $candidateWorkflowRoot -Parent $resolvedTargetRoot)) {
      throw "Refusing to remove workflow directory outside target root: $candidateWorkflowRoot"
    }

    $resolvedCandidateWorkflowRoot = [System.IO.Path]::GetFullPath($candidateWorkflowRoot)
    if ([string]::Equals($resolvedSourceWorkflowRoot, $resolvedCandidateWorkflowRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
      throw "Refusing to install codex_with_cc into its own source repository. Choose a different -TargetRoot so the installer does not remove its source workflow directory: $resolvedSourceWorkflowRoot"
    }

    Remove-Item -LiteralPath $candidateWorkflowRoot -Recurse -Force
  }
}

New-Item -ItemType Directory -Path $docsRoot -Force | Out-Null
New-Item -ItemType Directory -Path $workflowRoot -Force | Out-Null
$excludedScriptRoot = if ($installPlatform -eq 'Windows') { 'macos_scripts' } else { 'windows_scripts' }
foreach ($sourceItem in Get-ChildItem -LiteralPath $sourceWorkflowRoot -Force) {
  if ($sourceItem.Name -eq $excludedScriptRoot) {
    continue
  }
  Copy-Item -LiteralPath $sourceItem.FullName -Destination $workflowRoot -Recurse -Force
}
Update-InstalledWorkflowReferences -WorkflowRoot $workflowRoot -WorkflowRelativePath $workflowRelativePath
New-Item -ItemType Directory -Path $taskRoot -Force | Out-Null
$taskGitkeepPath = Join-Path $taskRoot '.gitkeep'
if (Test-Path -LiteralPath $taskGitkeepPath) {
  Remove-Item -LiteralPath $taskGitkeepPath -Force
}
Update-GitIgnore -Path (Join-Path $resolvedTargetRoot '.gitignore')

if (-not $SkipAgentEntrypoints) {
  foreach ($entryName in @('AGENTS.md')) {
    Update-AgentEntrypoint -Path (Join-Path $resolvedTargetRoot $entryName) -WorkflowRelativePath $workflowRelativePath
  }
}

Write-Host "codex_with_cc installed into: $workflowRoot"
if (-not $SkipAgentEntrypoints) {
  Write-Host 'Agent entrypoints updated: AGENTS.md'
}
Write-Host "Next: read $workflowRelativePath/CODEX_WITH_CC.md and use it as the single workflow contract."
