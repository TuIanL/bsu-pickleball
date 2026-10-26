$ErrorActionPreference = 'Stop'
$repoPath = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $repoPath '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create the repository .venv with Python 3.11 first.' }
& $pythonPath (Join-Path $PSScriptRoot 'windows_runtime.py') start
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
