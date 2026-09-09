param([string]$Config)
$ErrorActionPreference = 'Stop'
# 固定解释器与模块入口，避免依赖调用方当前目录和全局 Python。
$workerRoot = Split-Path -Parent $PSScriptRoot
if (-not $Config) { $Config = Join-Path $workerRoot 'config/runtime.toml' }
& (Join-Path $workerRoot '.venv/Scripts/python.exe') -m agy_worker.server --config $Config
exit $LASTEXITCODE
