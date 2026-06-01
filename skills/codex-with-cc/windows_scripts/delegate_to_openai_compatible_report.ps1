. (Join-Path $PSScriptRoot '_runtime.ps1')
Invoke-CodexWithCcRuntime -PythonScript 'delegate_to_openai_compatible_report.py' -RemainingArgs $args
