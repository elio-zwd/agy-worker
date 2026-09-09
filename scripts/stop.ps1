$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $workerRoot '.venv/Scripts/python.exe') -m agy_worker.manage stop
exit $LASTEXITCODE
