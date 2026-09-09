param([string]$Python = 'py.exe')
$ErrorActionPreference = 'Stop'
$workerRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $workerRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        # 安装者可传入已安装的 Python 3.13 或 3.14，不升级全局解释器。
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
    }
    & '.venv/Scripts/python.exe' -m pip install -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw '安装依赖失败' }
    & '.venv/Scripts/python.exe' -m pip install --no-deps --no-build-isolation -e .
    if ($LASTEXITCODE -ne 0) { throw '安装 Worker 失败' }
    & npm.cmd ci --prefix vendor/browser --ignore-scripts --no-audit --no-fund
    if ($LASTEXITCODE -ne 0) { throw '安装浏览器执行器失败' }
    & '.venv/Scripts/python.exe' -m agy_worker.manage doctor
    if ($LASTEXITCODE -ne 0) { throw '环境检查失败' }
} finally { Pop-Location }
