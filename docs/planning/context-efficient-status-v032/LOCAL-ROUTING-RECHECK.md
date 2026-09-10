# AGY Worker v0.3.2 Codex 路由修补本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
PREVIOUS_WINDOWS_PASS_HEAD: 87fb3ddd34c595c0b1be78db1a446711b994895f
CHAT_THREAD_RED_HEAD: d73d6a4646f7d1cb4818f93a18ea74f31a2fd698
CHAT_THREAD_FIX_HEAD: 73a2015c04dc84ad0d755cfe4831fb84fe4b6e17
ROUTING_UPGRADE_RED_HEAD: 365da956791f562d2989286e363e855eeb94a2e6
ROUTING_TARGET_HEAD: 31119240a5d5388b17f3f0d724644a479ec77b21
package: 0.3.2
controller protocol: 2
MCP tools: 6
```

`ROUTING_TARGET_HEAD` 是当前待验收代码。它之后只允许 `docs/planning/context-efficient-status-v032/**` 的验收/状态文档变化；若出现新的 `src/`、`tests/`、scripts、config、依赖或其他生产变化，停止并报告。

## 1. 已知历史证据

旧 HEAD `87fb3ddd34c595c0b1be78db1a446711b994895f` 已真实通过：

```text
scripts/check.ps1: exit 0
pytest: 96 passed / 0 failed / 0 skipped / 0 warnings
working_tree before/after: clean
```

但同一版本的真实 Codex 请求“让 AGY 跑一下编译”仍错误走了聊天/代理线程，出现“已列出聊天 / 已向聊天发送消息 / wait threads / 已读取聊天”。所以该版本**不是端到端 PASS**。

当前修补把 `AGY/agy` 在 Worker 支持任务中的含义唯一绑定为本机 `agy_worker` MCP，并显式排除 chat/thread/agent/subagent。随后又修复了一个升级问题：机器上若已经注册旧 `<AGY_WORKER_ROUTING>` block，新 `register.ps1` 应原位升级该 managed block，而不是因正文不同报冲突；用户自己的前置 `developer_instructions` 必须保留。

## 2. 安全前置与当前 HEAD

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
```

若非空，不 stash/reset/clean，停止并报告。

```powershell
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '31119240a5d5388b17f3f0d724644a479ec77b21'
git merge-base --is-ancestor $Target HEAD
Write-Host "routing_target_is_ancestor exit=$LASTEXITCODE"
git diff --name-only "$Target..HEAD"
git status --short
```

要求 ancestor exit `0`，且 target 之后只有本 planning 目录文档变化。

## 3. 当前 HEAD 权威回归

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"

git diff --check 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD'
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

记录真实 exit code、passed/failed/skipped/warnings、compileall。必须 `scripts/check.ps1 exit 0`、`0 failed`、`git diff --check exit 0`。不要用历史 96 passed 推断当前结果。

## 4. 验证旧 managed block 可安全升级

不要输出整个 `~/.codex/config.toml`。注册前先只读报告：

```powershell
@'
from pathlib import Path
import tomllib
p=Path.home()/'.codex'/'config.toml'
d=tomllib.loads(p.read_text('utf-8'))
s=d.get('developer_instructions','')
print('before_begin_count=',s.count('<AGY_WORKER_ROUTING>'))
print('before_end_count=',s.count('</AGY_WORKER_ROUTING>'))
print('before_chat_thread_binding=',all(x in s for x in ['只指本机','聊天','线程','subagent']))
'@ | .venv\Scripts\python.exe -
```

然后执行当前注册：

```powershell
pwsh.exe -NoProfile -File scripts/register.ps1
$RegisterExit = $LASTEXITCODE
Write-Host "register exit=$RegisterExit"
```

再只读检查：

```powershell
@'
from pathlib import Path
import tomllib
p=Path.home()/'.codex'/'config.toml'
d=tomllib.loads(p.read_text('utf-8'))
s=d.get('developer_instructions','')
print('after_begin_count=',s.count('<AGY_WORKER_ROUTING>'))
print('after_end_count=',s.count('</AGY_WORKER_ROUTING>'))
print('worker_rule_present=','agy_worker' in s and 'agy.exe' in s)
print('chat_thread_binding=',all(x in s for x in ['只指本机','聊天','线程','agent','subagent','让 AGY 跑一下编译']))
print('direct_cli_prohibition=',('不得直接' in s) and ('agy -p' in s))
print('mcp_registered=','agy_worker' in d.get('mcp_servers',{}))
'@ | .venv\Scripts\python.exe -
```

要求 `register exit=0`、begin/end 各 `1`、其余布尔值均 True。再次执行 `scripts/register.ps1` 并重复 after 检查，begin/end 仍必须各 `1`，证明升级后重复注册幂等。

> 若注册阶段出现“路由指令标记冲突或损坏”，不要手工改 `config.toml`，直接返回原始错误给 ChatGPT。

## 5. 新 Codex 会话真实行为

注册成功后**关闭旧测试会话并新开 Codex 会话**，进入此前实际业务项目。只发送：

```text
让 AGY 跑一下编译
```

不要额外提示“用 MCP”，因为这里验证的是自然语言路由。

### PASS 条件

必须同时满足：

1. `AGY` 被解释为 `agy_worker` MCP，而不是聊天/线程/agent/subagent。
2. 允许 `agy_capabilities`（必要时），随后应是 `agy_worker` → `agy_status(after_revision=...)`；需要失败细节时才按需 `agy_artifact_read`。
3. transcript 中不得出现为寻找 AGY 而进行的“列出聊天 / 读取聊天 / 向聊天发送消息 / wait threads / spawn 或等待 subagent”等路线。
4. transcript 中不得出现 `agy --help`、`agy -p`、direct `agy.exe` 等 shell/terminal fallback。
5. 编译成功/失败以 Worker terminal operation/exit code 为依据；成功路径不应无条件读取完整 diagnostics/result/operation-log。

若 UI 显示 context/token 数值，可记录请求前后变化，但只作为补充指标；主要证据是工具 transcript 和 Worker compact terminal result。

## 6. 返回 ChatGPT 的报告模板

```text
branch_head:
routing_target_is_ancestor:
post_target_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:

before_begin_count:
before_end_count:
before_chat_thread_binding:
register_exit_first:
after_begin_count_first:
after_end_count_first:
worker_rule_present:
chat_thread_binding:
direct_cli_prohibition:
mcp_registered:
register_exit_second:
after_begin_count_second:
after_end_count_second:

new_codex_session: yes/no
natural_language_request:
observed_tools_in_order:
chat_list_read_seen: yes/no
chat_send_seen: yes/no
thread_wait_seen: yes/no
subagent_route_seen: yes/no
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

本地 AI 只验收，不修代码。失败时保留 transcript、命令输出和 exit code，交回 ChatGPT 技术复核。
