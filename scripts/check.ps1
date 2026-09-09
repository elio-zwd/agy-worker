$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workerRoot
try {
    & '.venv/Scripts/python.exe' -m compileall -q src
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    & '.venv/Scripts/python.exe' -m pytest -q
    exit $LASTEXITCODE
} finally { Pop-Location }
