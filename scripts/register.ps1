$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
$workerPython = Join-Path $workerRoot '.venv/Scripts/python.exe'
# 只新增专用 Broker，保留现有 AGY 浏览器 MCP 与账号设置。
& agy.exe mcp add agy-worker-broker $workerPython -m agy_worker.broker
if ($LASTEXITCODE -ne 0) { throw '注册 AGY Broker 失败' }
& $workerPython -m agy_worker.manage register
exit $LASTEXITCODE
