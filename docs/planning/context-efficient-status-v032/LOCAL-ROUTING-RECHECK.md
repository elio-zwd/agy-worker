# AGY Worker v0.3.2 自适应 status 二次本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不修改任何 `AGENTS.md`、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
PREVIOUS_RECHECK_FAIL_HEAD: 3086915c2c8865271bcea18275b3fa69964df935
ADAPTIVE_RUNTIME_CODE_HEAD: 02201bd5b779117fb9e04c808b36e95ea80996be
RECHECK_TARGET_HEAD: 802f40405ea74ede2b437887ff6ba9dd2daa2edb
package: 0.3.2
controller protocol: 2
MCP tools: 6
public agy_status default wait: 50000 ms
public agy_status explicit wait range: 50000..600000 ms
internal controller status slice: <=25000 ms
Codex MCP tool_timeout_sec: 660
```

`02201bd...` 是自适应 status 的 Runtime/MCP 生产行为代码点；`802f404...` 在它之后只修复本地验收暴露的测试隔离、旧测试合同与 generated schema 同步问题，没有修改 Runtime、Controller、权限、协议或任何 `AGENTS.md`。本轮验收以 `802f404...` 为固定 target；target 后只允许本复验文档和 Task Tracker 等文档变化。

## 1. 上一轮 FAIL 与已核对根因

上一轮在 `3086915...` 得到：

```text
scripts/check.ps1: exit 1
pytest: 109 passed / 5 failed / 0 skipped / 2 warnings
compileall: PASS
git diff --check: exit 0
schema regeneration: 3 个 schema 产生 description 差异
register: exit 0
tool_timeout_sec: 660
hot capabilities: 700 bytes
真实新 Codex 会话: 未执行
```

ChatGPT 按 `receiving-code-review + systematic-debugging` 核对仓库后确认三个独立问题：

1. **4 个 StopIteration 属于测试时钟隔离错误。** deadline 测试通过 `monkeypatch.setattr(server_module.time, 'monotonic', ...)` 修改了 Python 共享的标准库 `time` 模块；`asyncio` 也依赖同一个 `time.monotonic`，有限 iterator 因此会被 event loop 额外消耗。`590629e...` 新增 `tests/conftest.py`，在每个测试中把 `server_module.time` 替换成只暴露真实 `monotonic` 的模块局部代理，之后各测试自己的 monkeypatch 不再污染 asyncio。生产 server deadline 逻辑未改。
2. **第 5 个失败是旧测试合同。** `tests/test_controller_reconnect.py` 仍断言旧 `tool_timeout_sec == 60`；当前用户批准合同和真实注册结果均为 660。`3a6d703...` 把该测试同步为 660；`manage.register()` 生产代码未回退。
3. **schema regeneration 差异是 tracked generated files 未完整同步。** Pydantic 会把 `McpWorkerRequest`、`McpPermissions`、`McpLimits`、`McpStatusRequest` 的 docstring 生成为 JSON Schema `description`，但 tracked worker/continue/status schema 此前手工同步时漏了这些字段。`aa8fc85...`、`0dda8b1...`、`802f404...` 只把生成器实际输出的 description 补进三个 tracked schema。

这些结论仍需本轮 Windows pytest/schema regeneration 的新鲜执行结果确认，不能仅凭远端代码审查宣称通过。

## 2. HEAD 与范围检查

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '802f40405ea74ede2b437887ff6ba9dd2daa2edb'
git merge-base --is-ancestor $Target HEAD
Write-Host "recheck_target_is_ancestor exit=$LASTEXITCODE"
git diff --name-only "$Target..HEAD"
git status --short
```

要求：开始工作区 clean；ancestor exit 0；target 后只能有 docs/planning 等验收文档；不得出现新的 `src/`、`tests/`、`scripts/`、`schemas/`、config、依赖或任何 `AGENTS.md` 变化。

## 3. 第一阶段：先关闭自动化失败

### 3.1 权威检查

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"

git diff --check 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD'
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

必须记录真实 pytest passed/failed/skipped/warnings 与 compileall。硬门槛：`scripts/check.ps1 exit 0`、pytest `0 failed`、compileall PASS、diff-check exit 0。若仍出现 StopIteration，保留完整 traceback 并停止后续真实 Codex 验收。

### 3.2 schema regeneration

```powershell
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
$SchemaExit = $LASTEXITCODE
git diff -- schemas
Write-Host "schema generation exit=$SchemaExit"
```

硬门槛：生成 exit 0 且 `git diff -- schemas` 为空。若仍有差异，返回**具体文件与完整 diff**，不要只写“有描述差异”，并撤销本次生成副作用以恢复 clean tree。

同时只读确认：

```text
agy_status.wait_ms default/min/max = 50000/50000/600000
worker/continue 不含 shell/code_write/write_paths/write_reason
worker/continue limits 仅 total_timeout_sec
```

### 3.3 注册配置

上一轮已真实得到 `register_exit=0`、`tool_timeout_sec=660`、用户 developer instructions/其他 MCP 保留；本轮代码没有修改 `manage.register()`。为确保当前环境仍加载最终分支，可再次幂等执行：

```powershell
pwsh.exe -NoProfile -File scripts/register.ps1
```

记录 exit code，并只读确认 `mcp_servers.agy_worker.tool_timeout_sec = 660`、managed routing block 仍只有 1 份、其他 MCP 和用户前缀仍保留。

**只有第一阶段全部 PASS 才进入第二阶段。**

## 4. 第二阶段：补齐上一轮未执行的真实 Codex 闭环

在已经带有“AGY是MCP”规则的真实业务项目中，新开一个 Codex 会话。不要编辑业务项目 Agents，只发送：

```text
使用AGY跑编译测试
```

必须保存完整 transcript 或足够还原调用顺序的证据。

### 4.1 路由与第一次提交

硬门槛：

- 进入 `agy_worker` MCP；未知映射时最多一次紧凑 `agy_capabilities`；
- 不出现为了定位 AGY 的 git/rg/`agy --help` 探测；
- 不 direct 调用 `agy/agy.exe/agy -p`；
- 不走 chat/thread/agent/subagent；
- 第一笔 `agy_worker` 即通过参数校验并提交，不带 shell/code_write 或 artifact/summary byte budgets；
- 成功路径不无条件读取完整 artifact。

### 4.2 status 自适应等待

第一次没有 revision 基线时允许：

```text
agy_status(task_id=<id>)
```

内部必须是即时 `wait_ms=0` 快照。之后使用 `after_revision=<last visible revision>`；公开 `wait_ms` 可以省略（默认 50000），也可以由 Codex 在 50000..600000 内自主选择。

观察并记录：

- Codex 可见 status 调用次数与参数；
- progress revision 是否被一个外部 status 内合并，而不是 1→2→3…逐个回模型；
- 内部 probe 若可见，每段 `wait_ms <= 25000`；
- 总 deadline 不因 progress revision 重置；
- deadline 到达时存在最终内部 `wait_ms=0` 快照；
- 两次 status 之间没有“我再等一轮/继续等待”等用户可见叙述。

### 4.3 terminal 提前返回与同会话闭环

长预算不是固定 sleep。若 Codex 选择较长预算且 AGY 在预算内 terminal，当前 status tool call 应在 terminal 后返回，不等待满预算。同一个 Codex 会话应继续处理到 Worker terminal，并以真实 operation exit code 得出结论。

真实业务场景未自然覆盖某个细分现象时写 `not_observed`，不要伪造；但“新 Codex 会话实际发起、第一笔 worker 提交、同会话是否到 terminal”属于本轮必须执行项目，不能继续全部留作 unknown。

## 5. 返回 ChatGPT 的报告模板

```text
branch_head:
recheck_target_is_ancestor:
post_target_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:
stopiteration_seen: yes/no

schema_generation_exit:
schema_regeneration_diff: none/details
status_wait_default:
status_wait_minimum:
status_wait_maximum:
hidden_worker_fields_absent: yes/no

register_exit:
codex_tool_timeout_sec:
user_developer_instructions_preserved: yes/no
managed_routing_block_count:
other_mcp_config_preserved: yes/no

new_codex_session: yes/no
natural_language_request:
observed_tools_in_order:
capabilities_call_count:
first_worker_arguments:
first_worker_submit_success: yes/no
pre_mcp_discovery_shell_seen: yes/no
direct_agy_cli_seen: yes/no
chat_thread_subagent_route_seen: yes/no

codex_visible_status_call_count:
status_calls:
first_status_without_revision_was_immediate_snapshot: yes/no/unknown
status_public_wait_values_or_omitted:
internal_status_wait_values_if_observed:
internal_status_wait_all_le_25000: yes/no/unknown
progress_revision_roundtrip_pattern:
total_deadline_reset_seen: yes/no/unknown
deadline_final_snapshot_seen: yes/no/not_observed
long_wait_terminal_early_return: yes/no/not_observed
long_wait_selected_ms_if_observed:
long_wait_actual_elapsed_if_observed:
unchanged_user_narration_seen: yes/no
same_codex_session_reached_terminal: yes/no
worker_terminal_status:
operation_exit_code:
artifact_reads:

working_tree_after:
open_findings:
overall_recheck: PASS/FAIL
```

只有自动化、schema regeneration 和真实 Codex 闭环全部满足门禁后，才报告 overall PASS。