# Controller v0.3.1 本地 AI 严格验收协议

> 适用分支：`fix/controller-hardening-v031`  
> 规格：`SPEC.md`  
> 实施计划：`PLAN.md`  
> 状态追踪：`TASKS.md`

## 1. 本地 AI 的角色

本地 AI 是独立验收层，不是本分支的主开发者。

职责：

- 拉取远端分支；
- 在 Windows 10 / 当前项目真实 Python 环境执行测试；
- 验证 WMI、Job Object、stdio Bridge、Controller 生命周期；
- 检查本机进程 / state / 日志证据；
- 报告失败的具体命令、stdout/stderr、文件和行号；
- 保持源码只读，除非用户明确要求本地 AI 临时做独立实验；
- 不直接替 ChatGPT 修生产代码；发现问题后交回 ChatGPT 按 receiving-code-review 复核。

不得把“代码看起来正确”写成“测试通过”。

## 2. 安全约束

### 2.1 默认不动正式 Controller

验收优先使用：

```text
pytest 的 tmp_path / temp data_dir
work/controller-v031-acceptance/
```

不要为了验收自动执行正式：

```powershell
scripts/stop.ps1
scripts/register.ps1
scripts/install.ps1
```

因为 stop 可能取消用户当前任务，register/install 会改变本机接入状态。

只有用户明确确认当前没有重要任务、且确实要验收正式配置时，才操作正式 `config/runtime.toml` Controller。

### 2.2 不删除历史证据

不要删除：

```text
data/tasks/
data/sessions/
work/backups/
```

本验收只允许清理自己创建的：

```text
work/controller-v031-acceptance/
```

并且清理前先确认该目录的 Controller 已停止。

### 2.3 验收前保留用户工作

第一步必须执行：

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
```

若存在用户未提交修改：

- 不 reset；
- 不 clean；
- 不 checkout 覆盖；
- 记录后停止可能覆盖这些文件的操作；
- 向用户报告。

## 3. 每个 TDD Task 的 RED 验收格式

ChatGPT 提交“仅测试 / 测试先行”阶段后，本地 AI 执行 PLAN 指定的定向命令。

报告必须使用：

```markdown
## RED Verification — T<编号>

Branch: fix/controller-hardening-v031
Commit: <实际 HEAD SHA>
Command:
```powershell
<完整命令>
```

Exit code: <数字>
Result: EXPECTED_FAIL | WRONG_FAILURE | UNEXPECTED_PASS | INFRA_FAILURE

Expected break:
- <这个测试本来要捕获的生产缺陷>

Observed failure:
- Test: <测试名>
- Exception/assertion: <原文>
- File/line: <如有>

Unrelated failures:
- none
# 或逐条列出

Git status after run:
```text
<git status --short 原文>
```
```

判断：

- `EXPECTED_FAIL`：失败原因就是计划中的缺失行为，ChatGPT 才能进入生产实现；
- `WRONG_FAILURE`：测试自己写错 / fixture 错 / 环境错误，不能进入 GREEN；
- `UNEXPECTED_PASS`：测试没有证明缺陷，不能进入 GREEN；
- `INFRA_FAILURE`：Python/依赖/路径等基础环境失败，先修验收环境或报告阻断。

## 4. 每个 TDD Task 的 GREEN 验收格式

ChatGPT 完成最小实现后，本地 AI 执行定向测试，并在必要时执行邻近回归。

```markdown
## GREEN Verification — T<编号>

Branch: fix/controller-hardening-v031
Commit: <实际 HEAD SHA>
Commands:
```powershell
<命令1>
<命令2>
```

Exit codes:
- command 1: 0
- command 2: 0

Results:
- <测试文件>: <passed 数 / failed 数，以真实输出为准>

Warnings / stderr:
- none
# 或贴原文

Git status after run:
```text
<原文>
```

Verdict: PASS | FAIL
```

不能只发“通过了”。必须提供实际 commit + command + exit code + 测试摘要。

## 5. 最终集成验收准备

在 T1–T8 完成并由 ChatGPT 标记 `awaiting_acceptance` 后执行。

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git fetch origin
git switch fix/controller-hardening-v031
git pull --ff-only origin fix/controller-hardening-v031
git status --short
git rev-parse HEAD
```

如果本机仓库路径不同，使用实际路径；不要为了匹配文档移动仓库。

记录：

```text
HEAD=<sha>
status=<git status --short>
```

## 6. 权威全量检查

执行仓库 `AGENTS.md` 指定的权威入口：

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
```

记录完整：

- exit code；
- pytest collected/passed/failed 数；
- warning/error；
- 是否有 hang / timeout。

**通过条件：** exit code 0，pytest 0 failed。

不要在报告中预设测试数量；以当前分支实际输出为准。

## 7. 建立隔离 lifecycle acceptance config

下面步骤只写 `work/`，不修改 tracked config。

```powershell
$Root = (Get-Location).Path
$AcceptanceRoot = Join-Path $Root 'work/controller-v031-acceptance'
$DataDir = Join-Path $AcceptanceRoot 'data'
$Config = Join-Path $AcceptanceRoot 'runtime.toml'
$Demo = Join-Path $Root 'examples/demo'

New-Item -ItemType Directory -Force -Path $AcceptanceRoot | Out-Null

function Escape-TomlPath([string]$Path) {
    return $Path.Replace('\', '\\')
}

$ConfigText = @"
schema_version = 1
data_dir = '$(Escape-TomlPath $DataDir)'
enabled_kinds = ['build']

[workspaces.demo]
source = '$(Escape-TomlPath $Demo)'
allowed_commands = ['demo_compile']

[commands.demo_compile]
argv = ['{python}', '-m', 'py_compile', 'sample.py']
"@

Set-Content -LiteralPath $Config -Value $ConfigText -Encoding utf8
Get-Content -LiteralPath $Config
```

验收配置故意不登记 AGY/browser，因为此 lifecycle 测试只验证 Bridge/Controller/Runtime 启动与工具发现，不执行 AGY 任务。

## 8. Fresh 双 Bridge / WMI 生命周期验收

先确认脚本支持计划中的参数：

```powershell
& ./.venv/Scripts/python.exe scripts/verify-controller.py --help
```

然后：

```powershell
& ./.venv/Scripts/python.exe scripts/verify-controller.py `
  --config $Config `
  --fresh `
  --stop-after
```

记录完整 JSON。

**必须检查：**

- `first_server_version == "0.3.1"`；
- `second_server_version == "0.3.1"`；
- `tool_count == 6`；
- `controller_protocol == 2`；
- `controller_instance_id` 非空；
- `controller_pid > 0`；
- `controller_alive_after_bridges == true`；
- `max_concurrent_tasks == 1`；
- `max_inflight_tasks == 16`；
- `stopped_after_verification == true`。

随后检查：

```powershell
$State = Join-Path $DataDir 'controller.json'
Test-Path -LiteralPath $State
```

Expected:

```text
False
```

这证明 acceptance Controller 已停止，不代表正式 Controller 状态。

## 9. Custom `run-task --config` no-leak 验收

### 9.1 测试前确认没有 acceptance Controller

```powershell
Test-Path -LiteralPath (Join-Path $DataDir 'controller.json')
```

Expected: `False`。

### 9.2 构造只执行本地 Python compile 的请求

```powershell
$Request = Join-Path $AcceptanceRoot 'request.json'
@"
{
  "request_id": "req-$(New-Guid | ForEach-Object { $_.Guid.Replace('-', '') })",
  "workspace_id": "demo",
  "kind": "build",
  "objective": "执行已登记的 demo_compile，只返回执行结果，不修改源码。",
  "permissions": {"build": true, "log": true},
  "inputs": {"command_id": "demo_compile"}
}
"@ | Set-Content -LiteralPath $Request -Encoding utf8
```

注意：该任务正常 Runtime 仍会启动 AGY CLI 来驱动 execute。如果本机 AGY 账号不可用，这一步可能因 AGY 认证失败；**no-leak 的判断仍必须看 finally 是否清理 Controller**，不能把 AGY auth failure 与 Controller cleanup 混为一个结论。

执行：

```powershell
& ./.venv/Scripts/python.exe scripts/run-task.py $Request --config $Config
$RunTaskExit = $LASTEXITCODE
$StateExists = Test-Path -LiteralPath (Join-Path $DataDir 'controller.json')
"run-task exit=$RunTaskExit"
"controller state exists=$StateExists"
```

**Controller lifecycle 通过条件：** 无论任务业务成功或失败，若该 Controller 是本次 run-task 启动且未给 `--keep-controller`，最终 `controller state exists=False`。

业务任务是否成功必须单独报告。

### 9.3 `--keep-controller`

使用新的 request_id：

```powershell
& ./.venv/Scripts/python.exe scripts/run-task.py $Request --config $Config --keep-controller
```

如果该次脚本拥有新启动 Controller，则结束后 state 应存在。随后显式清理：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1 -Config $Config
Test-Path -LiteralPath (Join-Path $DataDir 'controller.json')
```

Expected 最终 `False`。

如果业务请求的固定 request_id 已被第一次保存，先生成新的 request 文件；不要复用不同 payload 的同一 request_id。

## 10. Endpoint tamper / fail-closed 本地验证

自动测试通过后，可做一个隔离 state 篡改探针，但不要连接外部地址。

推荐只运行 pytest 中的 endpoint 测试：

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py -k endpoint
```

通过条件：非法 endpoint 在网络请求前被本地验证拒绝。

不要通过真的启动外部 HTTP server 来“证明不会外联”。

## 11. ACL advisory 验收

执行：

```powershell
pwsh.exe -NoProfile -File scripts/doctor.ps1
Get-Content -LiteralPath work/doctor.json
```

报告 `controller_data_acl` 原文。

判断规则：

- `checked=true`：记录 `broad_read_principals` 和 advisory；
- `checked=false`：记录 error，结论只能是“ACL 安全状态未确认”；
- 即使 advisory 良好，也不能报告 `os_isolation=true` 或“安全沙箱已启用”。

## 12. Protocol stop 验收

自动测试负责模拟 v1/v2 compatibility。最终本机不要求安装真的旧 v0.3 Controller。

运行：

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "protocol and stop"
```

通过条件：普通 business client 对协议不匹配 fail-closed；management stop 仍可停止旧协议 fixture/server。

## 13. Backpressure / queued cancel 验收

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_runtime.py -k "worker_busy or inflight or queued_cancel"
```

重点看：

- 第 17 个新请求被拒；
- 幂等 retry 不被拒；
- queued cancel 不需要释放前一个 running slot。

## 14. 最终 Git 完整性检查

```powershell
git status --short
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

报告：

- tracked 工作区是否干净；
- diff-check 是否有 whitespace error；
- changed files 是否全部属于计划范围；
- commit 顺序。

不要因为 `work/controller-v031-acceptance/` 存在就误报 tracked dirty；但如果任何受版本控制文件被验收修改，必须列出并停止。

## 15. 最终本地 AI 报告模板

请把以下完整报告发回 ChatGPT：

```markdown
# AGY Worker v0.3.1 Local Acceptance Report

## Environment
- OS:
- PowerShell:
- Python:
- Branch: fix/controller-hardening-v031
- HEAD:
- Starting git status:

## 1. Full repository check
Command:
```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
```
Exit code:
Pytest summary:
Warnings/errors:

## 2. Fresh two-Bridge lifecycle
Config:
Command:
```powershell
...
```
Raw JSON:
```json
...
```
State exists after --stop-after:

## 3. Custom run-task ownership
Normal custom run exit code:
Business task status:
Controller state after normal run:
Keep-controller state after run:
Explicit custom stop result:
Final state exists:

## 4. Protocol stop tests
Command:
Exit code:
Summary:

## 5. Backpressure / queued cancel
Command:
Exit code:
Summary:

## 6. ACL advisory
Doctor exit code:
controller_data_acl:
```json
...
```

## 7. Git integrity
`git status --short`:
```text
...
```
`git diff --check origin/main...HEAD` exit/output:
```text
...
```

## Findings
### Blocking
- none
# 或逐条：测试名 / 命令 / 原始错误 / 复现条件

### Non-blocking
- none

## Verdict
PASS | FAIL | PARTIAL

## Unverified
- <明确列出没有实际执行的项目>
```

## 16. 反馈给 ChatGPT 后的处理

ChatGPT 收到本报告后必须：

1. 对每个 finding 回到当前 GitHub 代码核实；
2. 区分真实缺陷、环境问题、测试问题、建议性改进；
3. 真实缺陷先补能复现的失败测试；
4. 不未经判断照搬本地 AI 建议；
5. 修复后要求最小必要的定向复验；
6. 最终只基于新鲜证据更新 `TASKS.md` / `docs/部署验收.md`。
