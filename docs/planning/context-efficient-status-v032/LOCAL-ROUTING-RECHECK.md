# AGY Worker v0.3.2 MCP 请求与状态合并本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不修改任何 `AGENTS.md`、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
PREVIOUS_LOCAL_FAIL_HEAD: b34e9879cf60776a2970f56884fc1efecd99d531
MCP_REQUEST_STATUS_TARGET_HEAD: 094445f4c57663375a725ecae74d236ddaa24567
package: 0.3.2
controller protocol: 2
MCP tools: 6
```

`MCP_REQUEST_STATUS_TARGET_HEAD` 包含本轮全部生产代码、公开 schema 与测试。它之后只允许 `README.md`、`docs/planning/context-efficient-status-v032/**`、`docs/实施设计.md` 等文档变化；若 target 之后出现新的 `src/`、`tests/`、scripts、config、依赖或任何 `AGENTS.md` 变化，停止并报告。

## 1. 上一轮已确认事实

`b34e987...` 已真实通过：

```text
scripts/check.ps1: exit 0
pytest: 102 passed / 0 failed / 0 skipped / 0 warnings
compileall: PASS
git diff --check: exit 0
hot agy_capabilities: 700 bytes
cold capabilities/workspaces: preserved
pre-MCP shell: none
direct AGY CLI: none
chat/thread/subagent route: none
real jianyu_compile_test: succeeded, exit 0, errors 0, warnings 26
```

但总体 FAIL：前两次 `agy_worker` 填了 `artifact_max_bytes=20000` 和 `permissions.shell=true` 被拒绝；status 虽使用 `after_revision + wait_ms=25000`，却因 progress revision 1..14 持续提前返回；unchanged 后出现“我再等一轮”；原 Codex 会话在 terminal 前结束。

本轮只修 MCP 外部契约和 MCP status 聚合，不改 Agents、Runtime progress 记录、Controller、权限执行层、协议、工具数量或单执行槽。

## 2. 安全前置与 HEAD

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '094445f4c57663375a725ecae74d236ddaa24567'
git merge-base --is-ancestor $Target HEAD
Write-Host "mcp_request_status_target_is_ancestor exit=$LASTEXITCODE"
git diff --name-only "$Target..HEAD"
git status --short
```

要求：开始工作区 clean；ancestor exit 0；target 后仅允许文档；不得修改任何 `AGENTS.md`。

## 3. 权威 Windows 回归

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"

git diff --check 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD'
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

必须记录实际 pytest passed/failed/skipped/warnings 与 compileall；要求 check exit 0、0 failed、diff-check exit 0。上一轮 102 passed 不能替代当前证据。

## 4. 公开 MCP Schema 复核

通过真实 MCP `list_tools` 或等价只读 probe 检查 `agy_worker` 与 `agy_continue` 的 `inputSchema`。

两者必须满足：

- `kind` 只有 `build/test/log/browser/android-ui/vision`，**没有 `shell`**；
- permissions 不含 `shell`、`code_write`、`write_paths`、`write_reason`；
- permissions 仍含当前公开的 build/test/log/browser/browser_interact/android-ui/vision 等字段；
- `limits` 仅含 `total_timeout_sec`，范围 10..1800，默认 300；
- 不含 `summary_max_bytes`、`artifact_max_bytes`；
- tool count 仍为 6。

同时执行仓库 schema 生成入口或检查 `manage schemas` 生成结果与 tracked `schemas/agy_worker.json` / `schemas/agy_continue.json` 无差异。不要为了检查而提交生成文件。

## 5. Hot/cold capabilities 回归

上一轮已通过，但当前 server 有变化，重新做轻量确认：

- 热 `agy_capabilities` 顶层仅 `schema_version/workspaces`；
- workspace 为 `workspace_id/registered_path/allowed_commands`，仅存在额外 worktree 时带 `known_worktrees`；
- 热结果不含 controller/limits/permissions/git flags；
- `agy://capabilities` 与 `agy://workspaces` 冷资源仍完整。

记录 hot JSON bytes；预计仍约上一轮 700B，但以实际结果为准。

## 6. 新 Codex 会话真实行为

使用已有“AGY是MCP”规则的业务项目，**不要编辑 Agents**。新开 Codex 会话，只发送：

```text
使用AGY跑编译测试
```

### 硬性 PASS 条件

1. 路由仍为 `agy_worker` MCP；无 AGY discovery shell、direct `agy/agy.exe/agy -p`、chat/thread/subagent。
2. 新会话若映射未知，最多一次紧凑 `agy_capabilities`；映射已知可直接 `agy_worker`。
3. **第一笔 `agy_worker` 调用必须通过 MCP 参数校验并提交任务**。不得再出现因 `permissions.shell`、`kind=shell`、`artifact_max_bytes`、`summary_max_bytes` 导致的参数重试。
4. 记录第一笔 `agy_worker` arguments。不得出现已从 schema 隐藏的上述字段；`limits` 若存在只能含 `total_timeout_sec`。
5. terminal 结论来自 Worker status/result 的真实 operation exit code；成功路径不无条件读 artifacts。
6. 同一 Codex 会话应持续查询到 terminal。若宿主主动结束而任务仍非终态，保存 transcript 并判本项 FAIL/待技术复核，不能用另一个 follow-up 冒充原会话闭环。

## 7. Status coalescing 复核

首个非终态后，Codex 应使用：

```text
after_revision=<last visible revision>
wait_ms=25000
```

本轮新增的是 **MCP server 内部 coalescing**：Runtime 仍可能生成很多 progress revision，但它们不应逐个成为 Codex 可见的 `agy_status` tool result。

记录：

- Codex 可见 `agy_status` 调用次数；
- 每次可见调用的传入 after_revision/wait_ms；
- 每次返回 revision/status/unchanged；
- 如果能看 Controller/internal probe，可补充内部被合并的 revision 数量，但不是硬性要求。

不要用固定“最多 N 次”作为硬门槛，因为构建时长不同。核心判定是：**短时间连续 progress revision 不再造成 revision 1→2→3→… 每个都回到 Codex。** 一个 25 秒窗口内如果任务持续产生 progress，MCP 应尽量在内部消费并在 terminal 或总等待窗口结束时才返回一个观察点。

总等待预算不能因中间 revision 重置；一次 `wait_ms=25000` 的 MCP 调用不能变成每个 revision 再等 25 秒。

如果 25 秒总窗口结束仍非终态，Codex 应立即再次 `agy_status`。两次 status 之间不得出现“我再等一轮”“继续等待”等面向用户的等待说明。若返回 `unchanged=true`，TextContent 应提示继续轮询/无需用户消息。

## 8. 返回 ChatGPT 的报告模板

```text
branch_head:
mcp_request_status_target_is_ancestor:
post_target_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:

mcp_tool_count:
worker_kind_enum:
worker_permission_keys:
worker_limit_keys:
continue_schema_matches_worker_surface: yes/no
hidden_shell_absent: yes/no
hidden_code_write_absent: yes/no
hidden_artifact_summary_limits_absent: yes/no
tracked_schema_regeneration_diff: none/details

hot_capabilities_bytes:
hot_capabilities_keys:
cold_capabilities_full_preserved: yes/no
cold_workspaces_full_preserved: yes/no

new_codex_session: yes/no
natural_language_request:
observed_tools_in_order:
capabilities_call_count:
agy_worker_call_count_before_submit_success:
first_worker_arguments:
first_worker_submit_success: yes/no
hidden_fields_seen_in_worker_args: yes/no + details
pre_mcp_shell_seen: yes/no
direct_agy_cli_seen: yes/no
chat_thread_subagent_route_seen: yes/no

codex_visible_status_call_count:
status_calls:
progress_revision_roundtrip_pattern:
status_after_revision_seen: yes/no/unknown
status_wait_25000_seen: yes/no/unknown
unchanged_user_narration_seen: yes/no
same_codex_session_reached_terminal: yes/no
worker_terminal_status:
operation_exit_code:
artifact_reads:
queue_wait_if_observed:

working_tree_after:
open_findings:
overall_recheck: PASS/FAIL
```

本地 AI 只验收，不修代码。失败时保留 transcript、MCP arguments/result、命令输出与 exit code，交回 ChatGPT 技术复核。
