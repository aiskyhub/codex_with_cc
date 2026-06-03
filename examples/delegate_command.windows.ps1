$env:CODEX_CLAUDE_CHILD_THREAD = '1'

$workflowRoot = '<installed-workflow-root>'
$taskFile = '<task-file>'
$artifactRoot = '<artifact-root>'

powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $workflowRoot 'windows_scripts\delegate_to_claude.ps1') `
  -TaskFile $taskFile `
  -WorkflowId '<workflow-id>' `
  -TaskId '<task-id>' `
  -Role implementer `
  -SessionKey '<stable-session-key>' `
  -SessionMode PrimaryReuse `
  -Scope '<scope>' `
  -Tests '<declared verification evidence>' `
  -ArtifactRoot $artifactRoot `
  -Model haiku `
  -MaxRetryCount 1 `
  -BypassPermissions
