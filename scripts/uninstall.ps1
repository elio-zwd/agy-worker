$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
& (Join-Path $workerRoot '.venv/Scripts/python.exe') -m agy_worker.manage stop
if ($LASTEXITCODE -ne 0) { throw '停止 AGY Worker Controller 失败' }
& (Join-Path $workerRoot '.venv/Scripts/python.exe') -m agy_worker.manage unregister
if ($LASTEXITCODE -ne 0) { throw '移除 Codex 注册失败' }
& agy.exe mcp remove agy-worker-broker
# 默认保留源码、任务证据及虚拟环境，避免误删仍需审查的部署资料。
Write-Host '已移除连接配置。安装目录和任务证据均保留。'
