# AGY Worker v0.3.2 Codex 路由修补本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
ROUTING_TEST_HEAD: b0c9726830db88500823820994aba0ab0efa5526
ROUTING_INITIAL_CODE_HEAD: 13293e9fb2bbd309e0e9ee96929699514f5bdcf9
ROUTING_FIX_HEAD: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
package: 0.3.2
controller protocol: 2
MCP tools: 6
```

`ROUTING_FIX_HEAD` 是当前待验收生产代码。它之后只允许 `AGENTS.md` 和 `docs/planning/context-efficient-status-v032/**` 的说明/验收文件变化。如果出现其他源码、测试、脚本、配置或依赖变化，停止并报告。

### 已知前一轮失败（不要重复当作当前结果）

在旧 HEAD `c28713f09856331339968a7b5c4856b3e2b9ca6c` 上，本地权威检查真实得到：

```text
scripts/check.ps1 exit: 1
pytest: 95 passed / 1 failed / 0 skipped / 0 warnings
failed: tests/test_manage.py::test_register_adds_codex_routing_without_overwriting_existing_instructions
reason: 生产文案为“不得用 shell/terminal 直接调用”，测试要求连续子串“不可直接”或“不得直接”
```

ChatGPT 技术复核后确认路由语义本身已禁止 direct CLI，但测试合同要求更明确连续措辞。`ROUTING_FIX_HEAD` 只把生产指令改为“不得直接用 shell/terminal 调用”，相对旧 HEAD 仅 `src/agy_worker/manage.py` 一行替换。当前 HEAD 必须重新执行完整检查，不能沿用旧结果。

## 1. 安全前置

在 `D:\My\_Elio\agy-worker`：

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
```

若非空，不 stash/reset/clean 覆盖用户内容，停止并报告。

然后：

```powershell
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$RoutingFix = 'be29e8c78836deed4ccf88864cace5e1fc5dc7c2'
git merge-base --is-ancestor $RoutingFix HEAD
Write-Host "routing_fix_is_ancestor exit=$LASTEXITCODE"
git diff --name-only "$RoutingFix..HEAD"
git status --short
```

要求 ancestor exit `0`，且 target 之后只能有上述允许的文档路径。

## 2. 当前 HEAD 的权威测试

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"

git diff --check 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD'
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

原样记录：exit code、pytest passed/failed/skipped/warnings、compileall 结果和全部失败。前一轮旧 HEAD 是 `95 passed / 1 failed`；当前验收必须实际得到 exit `0` 和 `0 failed` 才能进入后续真实 Codex 路由验证。

## 3. 注册当前路由规则

这是 agy-worker 自身维护操作，因此允许 `scripts/register.ps1` 内部调用 AGY CLI：

```powershell
pwsh.exe -NoProfile -File scripts/register.ps1
$RegisterExit = $LASTEXITCODE
Write-Host "register exit=$RegisterExit"
```

不要输出整个 `~/.codex/config.toml`，避免泄露其他配置。用只读脚本只报告布尔值/计数：

```powershell
@'
from pathlib import Path
import tomllib
p = Path.home()/'.codex'/'config.toml'
d = tomllib.loads(p.read_text('utf-8'))
s = d.get('developer_instructions','')
print('routing_begin_count=', s.count('<AGY_WORKER_ROUTING>'))
print('routing_end_count=', s.count('</AGY_WORKER_ROUTING>'))
print('worker_rule_present=', 'agy_worker' in s and 'agy.exe' in s)
print('direct_cli_prohibition_present=', '不得直接' in s or '不可直接' in s)
print('mcp_registered=', 'agy_worker' in d.get('mcp_servers',{}))
'@ | .venv\Scripts\python.exe -
```

要求 begin/end 均为 `1`，`worker_rule_present=True`，`direct_cli_prohibition_present=True`，`mcp_registered=True`。再次执行 `scripts/register.ps1` 后重复检查，计数仍必须为 `1`，证明真实配置幂等。

## 4. 真实 Codex 行为复验

注册完成后**新开一个 Codex 会话**，避免旧 session 已经加载旧 config。进入此前实际使用 AGY 编译的业务项目，用与失败时相同或等价的自然语言：

```text
你让agy跑一下编译
```

保存 Codex 可见 transcript。不要指导 Codex“一定要用 MCP”；这一步要验证自然语言路由本身。

### PASS 条件

必须同时满足：

1. Codex 使用 `agy_worker` MCP 链路；允许先调用 `agy_capabilities`，随后应看到 `agy_worker`、`agy_status`，需要诊断时才按需 `agy_artifact_read`。
2. transcript **不得**出现正常业务路径下的 `agy --help`、`agy -p ...`、直接 `agy.exe ...` 或其他 shell/terminal AGY CLI fallback。
3. 如果 MCP 不可用，Codex 应明确报告不可用并停止，不得自动转为 direct CLI。
4. 编译成功/失败结论必须来自 Worker terminal 的真实 operation 状态/exit code；AGY 自述成功不能替代进程证据。
5. 成功时不应无条件读取 diagnostics/result/operation-log 全量冷证据；只有实际需要细节时才 drill-down。

若 UI 显示 context/token 使用量，记录本次请求前和完成后的数值作为补充比较。UI 折叠不视为“未进入上下文”的证据；主要判据仍是 tool transcript 与 Worker compact 返回。

## 5. 返回 ChatGPT 的报告模板

```text
branch_head:
routing_fix_is_ancestor:
post_routing_fix_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:

register_exit:
routing_begin_count_first:
routing_end_count_first:
routing_begin_count_second:
routing_end_count_second:
worker_rule_present:
direct_cli_prohibition_present:
mcp_registered:

new_codex_session: yes/no
natural_language_request:
observed_tools_in_order:
direct_agy_help_seen: yes/no
direct_agy_p_seen: yes/no
direct_agy_exe_seen: yes/no
worker_terminal_status:
operation_exit_code:
artifact_reads:
context_before_if_visible:
context_after_if_visible:

working_tree_after:
open_findings:
overall_recheck: PASS/FAIL
```

不要自行修改失败项。把 transcript 中与路由、错误、exit code 有关的原文一并返回 ChatGPT，由远端主开发 AI 复核。
