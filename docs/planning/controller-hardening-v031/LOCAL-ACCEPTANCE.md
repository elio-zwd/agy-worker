# Controller v0.3.1 最终本地 AI 严格验收协议

> 适用分支：`fix/controller-hardening-v031`
> 规格：`SPEC.md`
> 实施计划：`PLAN.md`
> 状态追踪：`TASKS.md`

## 1. 验收方式

本分支按用户要求采用**远端连续开发 + 最终一次性本地验收**：T2–T9 不再逐 Task 打断用户执行 RED/GREEN；ChatGPT 完成代码、测试、静态规格复核和代码质量复核后，再由本地 AI 在最终 HEAD 上一次性运行全部 Windows 验证。

本地 AI 是独立验收层，不是主开发者。只允许：

- 拉取远端分支；
- 读取代码、diff、日志和 state；
- 在 Windows 10 / 项目真实 Python 环境运行测试与验收脚本；
- 验证 WMI、stdio Bridge、Controller 生命周期、ACL advisory；
- 返回命令、退出码、pytest 摘要、PID/instance、原始错误。

**不得修复生产代码、不得改测试制造通过、不得 reset/clean 用户工作。** 发现问题后把证据交回 ChatGPT，按 `receiving-code-review` 技术复核。

## 2. 安全边界

验收优先使用独立目录：

```text
work/controller-v031-acceptance/
```

不要自动停止正式 `config/runtime.toml` Controller，不要执行 `register.ps1` / `install.ps1`，不要删除历史：

```text
data/tasks/
data/sessions/
work/backups/
```

只可清理本次自己创建的 acceptance 目录，并且先确认其中 Controller 已停止。

## 3. 拉取最终 HEAD

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git fetch origin
git switch fix/controller-hardening-v031
git pull --ff-only origin fix/controller-hardening-v031

git branch --show-current
git rev-parse HEAD
git status --short
```

如果本机路径不同，使用实际路径。若 `git status --short` 有任何用户未提交修改：不要覆盖；记录并停止可能改 tracked 文件的动作。

随后刷新 editable package metadata，避免源码版本已更新但本机 `.dist-info` 仍旧：

```powershell
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
& ./.venv/Scripts/python.exe -c "import importlib.metadata as m; print(m.version('elio-agy-worker'))"
```

期望 metadata：`0.3.1`。若 editable install 失败，停止后续并原样报告。

## 4. T2–T8 定向验收

逐条运行，保留每条 exit code 与 pytest summary；任何一条失败都继续记录后续**只读/测试性**证据，但不得修代码。

### T2：跨协议 stop / replacement 防误停

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "stop or protocol"
```

重点：旧协议 management stop；v2 stop auth-only；business call 仍 protocol strict；replacement 不被继续请求；`manage stop --config`。

### T3：launch lock takeover / retry / WMI PID

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "simultaneous or takeover or launch_retry or wmi_launch or pending_pid"
```

重点：等待者能接管；重试间隔不形成 process storm；共享 pending PID 不允许重复 launch；两个 client 仍只落到一个 healthy Controller；WMI 返回的 venv launcher PID 仅用于启动归属/诊断，health 中 Controller PID 与 health 本身仍是 ready 真值。

### T4：custom run-task ownership

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_run_task.py
```

重点：本次自启实例默认清理；pre-existing 保留；`--keep-controller` 保留；replacement 防误停。

### T5：status reconnect budget

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_reconnect.py
```

重点：第一次 long-poll 断线后，第二次 `wait_ms=0`；task/revision 保留；submit/continue request_id 不变。

### T6：inflight backpressure / queued cancel

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_runtime.py
```

重点：1 concurrent / 16 inflight；第 17 个新请求 `worker_busy`；幂等 retry 不受容量 gate；reject 不创建第 17 个 task/session；真正 queued Future 立即 `cancelled`。

### T7：state security / ACL advisory

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py
```

重点：非法 endpoint 在任何网络访问前拒绝；authenticated health 非 object 也受控拒绝；ACL classifier；ACL API 失败是 unknown，不宣称安全。

### T8：MCP version / package contract

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_server.py
```

重点：MCP server version 使用 package metadata，必须为 `0.3.1`。

### 最终审查新增回归

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_hardening_quality.py
```

重点：`--fresh` 不把仍存在但不可达的旧 state 当成 `not_running`；WMI 多次 launch 使用独立环境文件；超过清理窗口的遗留 proxy 环境文件会被清理而新鲜文件不受影响；stop 必须等待 state 真正消失；Windows venv launcher 与真实 Controller PID 不同时仍能安全建立 ownership。

## 5. 权威全量检查

仓库 `AGENTS.md` 的权威入口：

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
```

记录：

- exit code；
- compileall 是否成功；
- pytest collected / passed / failed / skipped；
- warning / error；
- 是否 hang / timeout。

只有 exit code 0 且 pytest 0 failed 才可记为全量 PASS。不要预填测试数量。

## 6. 建立隔离 lifecycle config

只写 `work/`：

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

该配置不登记 AGY/browser；lifecycle 验收只初始化 Bridge/Controller/Runtime 与 capabilities，不执行 AGY。

## 7. T9 fresh 双 Bridge / WMI 生命周期

先查看 CLI：

```powershell
& ./.venv/Scripts/python.exe scripts/verify-controller.py --help
```

再执行：

```powershell
& ./.venv/Scripts/python.exe scripts/verify-controller.py `
  --config $Config `
  --fresh `
  --stop-after
$VerifyExit = $LASTEXITCODE
"verify-controller exit=$VerifyExit"
```

完整保存 JSON。通过条件全部为真：

```text
first_server_version == "0.3.1"
second_server_version == "0.3.1"
tool_count == 6
second_tool_count == 6
controller_protocol == 2
controller_instance_id 非空
controller_pid > 0
controller_alive_after_bridges == true
max_concurrent_tasks == 1
max_inflight_tasks == 16
stopped_after_verification == true
verification_passed == true
exit code == 0
```

`--fresh` 如果在停止目标时发现 replacement，或发现 state 仍存在但目标 stop 暂时不可达，脚本应 fail-closed，不应继续启动/追停 replacement。

结束后：

```powershell
$State = Join-Path $DataDir 'controller.json'
Test-Path -LiteralPath $State
```

期望 `False`。

## 8. 真实 custom-config lifecycle（不调用 AGY）

这部分使用一个**必然在 Runtime 前置校验阶段失败**的请求，因此可以验证 Controller ownership/cleanup，而不依赖 AGY 登录状态。

```powershell
$InvalidRequest = Join-Path $AcceptanceRoot 'invalid-workspace-request.json'
@"
{
  "request_id": "req-$((New-Guid).Guid.Replace('-', ''))",
  "workspace_id": "missing-workspace",
  "kind": "build",
  "objective": "只验证 custom Controller 生命周期；此请求应在工作区校验处被拒绝。",
  "permissions": {"build": true},
  "inputs": {"command_id": "demo_compile"}
}
"@ | Set-Content -LiteralPath $InvalidRequest -Encoding utf8
```

### 8.1 本次自启 → 默认 no-leak

先确认：

```powershell
Test-Path -LiteralPath $State
```

期望 `False`。

执行（业务 exit 非 0 是预期，因为 workspace 故意不存在）：

```powershell
& ./.venv/Scripts/python.exe scripts/run-task.py $InvalidRequest --config $Config
$NormalExit = $LASTEXITCODE
$NormalStateExists = Test-Path -LiteralPath $State
"normal exit=$NormalExit"
"normal state exists=$NormalStateExists"
```

lifecycle 通过条件：`normal state exists=False`。

### 8.2 pre-existing Controller 必须保留

先显式启动 acceptance Controller并记录身份：

```powershell
& ./.venv/Scripts/python.exe -c "from agy_worker.controller_client import ControllerClient; import sys; c=ControllerClient(sys.argv[1]); print(c.state['instance_id']); print(c.state['pid'])" $Config
$Before = Get-Content -LiteralPath $State -Raw | ConvertFrom-Json
"before instance=$($Before.instance_id) pid=$($Before.pid)"
```

为这次逻辑请求生成新的 request_id：

```powershell
(Get-Content -LiteralPath $InvalidRequest -Raw) `
  -replace 'req-[0-9a-f]+', ('req-' + (New-Guid).Guid.Replace('-', '')) `
  | Set-Content -LiteralPath $InvalidRequest -Encoding utf8

& ./.venv/Scripts/python.exe scripts/run-task.py $InvalidRequest --config $Config
$PreExistingExit = $LASTEXITCODE
$After = Get-Content -LiteralPath $State -Raw | ConvertFrom-Json
"after instance=$($After.instance_id) pid=$($After.pid)"
```

通过条件：state 仍存在，且 `$After.instance_id == $Before.instance_id`。

然后清理：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1 -Config $Config
Test-Path -LiteralPath $State
```

期望 `False`。

### 8.3 `--keep-controller`

再生成新的 request_id，并在无 pre-existing Controller 时：

```powershell
(Get-Content -LiteralPath $InvalidRequest -Raw) `
  -replace 'req-[0-9a-f]+', ('req-' + (New-Guid).Guid.Replace('-', '')) `
  | Set-Content -LiteralPath $InvalidRequest -Encoding utf8

& ./.venv/Scripts/python.exe scripts/run-task.py $InvalidRequest --config $Config --keep-controller
$KeepExit = $LASTEXITCODE
$KeepStateExists = Test-Path -LiteralPath $State
"keep exit=$KeepExit"
"keep state exists=$KeepStateExists"
```

lifecycle 通过条件：`keep state exists=True`。业务请求失败仍是预期，不要把它误判为 lifecycle 失败。

最终显式清理：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1 -Config $Config
Test-Path -LiteralPath $State
```

期望 `False`。

## 9. ACL advisory 真实诊断

运行正式 doctor 只做诊断，不自动更改 ACL：

```powershell
pwsh.exe -NoProfile -File scripts/doctor.ps1
$DoctorExit = $LASTEXITCODE
Get-Content -LiteralPath work/doctor.json
```

报告字段名是 **`controller_data_acl`**，与 `SPEC.md` 合同一致：

- `checked=true`：记录 `broad_read_principals` 与 `token_confidentiality_advisory`；
- `checked=false`：记录 error，结论只能是“ACL 安全状态未确认”；
- 无论结果如何，`os_isolation` 仍应为 `false`；
- advisory 良好也不能写“安全沙箱已启用”。

`doctor` 的整体 exit code仍由既有 AGY/browser 必需条件决定；如果 doctor 因其他必需依赖失败，要区分 ACL 结果与整体 doctor 结果。

## 10. Git 完整性

```powershell
git status --short
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git log --oneline --decorate origin/main..HEAD
```

要求：

- tracked 工作区干净；
- `git diff --check` exit 0；
- 不因 `work/controller-v031-acceptance/` 未跟踪/忽略文件误报 tracked 修改；
- 若任何 tracked 文件被验收过程修改，停止并报告。

## 11. 最终报告模板

把下面一次性完整报告交回 ChatGPT。不要只写“全通过”。

```markdown
# AGY Worker v0.3.1 Final Local Acceptance

## Environment
- OS:
- PowerShell:
- Python:
- Branch: fix/controller-hardening-v031
- HEAD:
- Starting git status:
- Package metadata version:

## T2 stop/protocol
- Command:
- Exit code:
- Summary:

## T3 launch takeover/WMI
- Command:
- Exit code:
- Summary:

## T4 run-task unit tests
- Command:
- Exit code:
- Summary:

## T5 reconnect
- Command:
- Exit code:
- Summary:

## T6 runtime/backpressure
- Command:
- Exit code:
- Summary:

## T7 security/ACL tests
- Command:
- Exit code:
- Summary:

## T8 server/version
- Command:
- Exit code:
- Summary:

## Final-review regressions
- Command:
- Exit code:
- Summary:

## Full repository check
- Command: pwsh.exe -NoProfile -File scripts/check.ps1
- Exit code:
- Compileall:
- Pytest collected/passed/failed/skipped:
- Warnings/errors:

## T9 fresh two-Bridge lifecycle
- Command:
- Exit code:
- Raw JSON:
```json
...
```
- State exists after --stop-after:

## Custom-config lifecycle
- Normal invalid-request exit:
- State after normal run:
- Pre-existing instance before:
- Pre-existing instance after:
- Keep-controller state after run:
- Final explicit stop result:
- Final state exists:

## ACL advisory
- doctor exit code:
- controller_data_acl:
```json
...
```
- os_isolation:

## Git integrity
- git status --short:
```text
...
```
- git diff --check exit/output:
```text
...
```
- diff stat:
```text
...
```

## Findings
### Blocking
- none
# 或逐条列出：命令、测试名、原始错误、文件/行号

### Non-blocking
- none

## Final local verdict
PASS | FAIL | INFRA_BLOCKED
```

## 12. 判定规则

- 任一代码/测试行为失败：`FAIL`；不修，交回 ChatGPT。
- editable install、Python、PowerShell 等基础设施阻断且无法执行测试：`INFRA_BLOCKED`。
- 只有所有 required checks 有真实证据、全量测试 0 failed、fresh lifecycle exit 0、custom lifecycle 符合 ownership 合同、git diff-check 0，才能写 `PASS`。
- 本地 AI 的 PASS 仍是验收证据；ChatGPT 收到后会按 `receiving-code-review` 逐条技术核对，再决定是否创建 Draft PR。
