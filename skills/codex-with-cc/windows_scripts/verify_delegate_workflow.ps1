. (Join-Path $PSScriptRoot '_runtime.ps1')
Invoke-CodexWithCcRuntime -PythonScript 'verify_delegate_workflow.py' -RemainingArgs $args
