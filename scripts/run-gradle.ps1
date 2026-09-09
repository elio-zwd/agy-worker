param([Parameter(Mandatory)][ValidatePattern('^[A-Za-z0-9_:]+$')][string]$Task)
$ErrorActionPreference = 'Stop'
# 工作目录由 Runtime 绑定到执行副本；命令不接受任意 shell 文本。
if (-not (Test-Path -LiteralPath './gradlew.bat')) { throw '执行副本中没有 gradlew.bat' }
& './gradlew.bat' $Task --console=plain --no-daemon
exit $LASTEXITCODE
