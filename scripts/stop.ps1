param([string]$Config)

$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
$arguments = @('-m', 'agy_worker.manage', 'stop')
if ($Config) {
    $arguments += @('--config', $Config)
}
& (Join-Path $workerRoot '.venv/Scripts/python.exe') @arguments
exit $LASTEXITCODE
