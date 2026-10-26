$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
& (Join-Path $repoPath '.venv/Scripts/python.exe') (Join-Path $PSScriptRoot 'windows_runtime.py') stop
exit $LASTEXITCODE
