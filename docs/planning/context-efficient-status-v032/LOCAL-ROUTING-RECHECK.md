# AGY Worker v0.3.2 MCP 请求与自适应状态等待本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不修改任何 `AGENTS.md`、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
PREVIOUS_LOCAL_FAIL_HEAD: b34e9879cf60776a2970f56884fc1efecd99d531
PREVIOUS_MCP_REQUEST_STATUS_TARGET_HEAD: 094445f4c57663375a725ecae74d236ddaa24567
ADAPTIVE_STATUS_WAIT_TARGET_HEAD: 02201bd5b779117fb9e04c808b36e95ea80996be
package: 0.3.2
controller protocol: 2
MCP tools: 6
public agy_status default wait: 50000 ms
public agy_status explicit wait range: 50000..600000 ms
internal controller status slice: <=25000 ms
Codex MCP tool_timeout_sec: 660
```

`ADAPTIVE_STATUS_WAIT_TARGET_HEAD` 包含本轮自适应等待的全部生产代码、公开 schema 与测试，包括 deadline 到达后的最终即时 status 快照边界；`094445f...` 是上一版固定 25 秒策略的旧 target，已被本 target 取代。新 target 之后只允许 `README.md`、`docs/planning/context-efficient-status-v032/**`、`docs/实施设计.md` 等文档变化；若 target 之后出现新的 `src/`、`tests/`、scripts、config、依赖或任何 `AGENTS.md` 变化，停止并报告。

## 1. 上一轮已确认事实与本轮变化

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

但该轮总体 FAIL：前两次 `agy_worker` 填了 `artifact_max_bytes=20000` 和 `permissions.shell=true` 被拒绝；status 虽使用 `after_revision + wait_ms=25000`，却因 progress revision 1..14 持续提前返回；unchanged 后出现“我再等一轮”；原 Codex 会话在 terminal 前结束。

`094445f...` 随后收缩了 MCP worker/continue schema 并在 MCP server 内 coalesce progress revision。用户进一步确认新的 status 策略：**公开默认 50 秒，Codex 可自主选择 50～600 秒；MCP 内部仍按最多 25 秒的 Controller long-poll 分片；AGY 提前 terminal 时当前 tool call 立即返回。** 本轮不实现 webhook、push notification、MCP Tasks subscription，不改 Runtime progress 记录、Controller protocol、权限执行层、工具数量或单执行槽，也不修改任何 `AGENTS.md`。

规格审查额外发现一个截止点竞态：若最后一个内部 long-poll 返回 running/unchanged 后恰好跨过公开 deadline，而任务在该边界已经 terminal，直接返回旧 `latest` 会延迟终态到下一轮 Codex status。`02201bd...` 已改为 deadline 到达时再执行一次内部 `wait_ms=0` 最终快照；对应回归在 `tests/test_adaptive_status_deadline.py`。

## 2. 安全前置与 HEAD

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '02201bd5b779117fb9e04c808b36e95ea80996be'
git merge-base --is-ancestor $Target HEAD
Write-Host "adaptive_status_wait_target_is_ancestor exit=$LASTEXITCODE"
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

必须记录实际 pytest passed/failed/skipped/warnings 与 compileall；要求 check exit 0、0 failed、diff-check exit 0。任何上一轮通过数字都不能替代当前 target 的新鲜证据。

## 4. 公开 MCP Schema 与生成器复核

通过真实 MCP `list_tools` 或等价只读 probe 检查全部 6 个工具，重点检查 `agy_worker`、`agy_continue`、`agy_status`。

`agy_worker/agy_continue` 必须满足：

- `kind` 只有 `build/test/log/browser/android-ui/vision`，**没有 `shell`**；
- permissions 不含 `shell`、`code_write`、`write_paths`、`write_reason`；
- permissions 仍含当前公开的 build/test/log/browser/browser_interact/android-ui/vision 等字段；
- `limits` 仅含 `total_timeout_sec`，范围 10..1800，默认 300；
- 不含 `summary_max_bytes`、`artifact_max_bytes`。

`agy_status` 必须满足：

```text
properties: task_id / after_revision / wait_ms
wait_ms default: 50000
wait_ms minimum: 50000
wait_ms maximum: 600000
tool count: 6
```

额外做两个非法参数 probe：`wait_ms=49999` 与 `wait_ms=600001` 都必须在 MCP 参数校验阶段返回 `invalid_request`，不得进入 Controller status。

执行公开 schema 生成入口，确认 tracked schema 无变化：

```powershell
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
git diff -- schemas
```

要求 `schemas/agy_status.json` 仍是 50000/50000/600000；`agy_worker.json` / `agy_continue.json` 仍保持瘦契约；生成后 `git diff -- schemas` 为空。不要为了检查提交生成文件。

## 5. Codex MCP 注册配置复核

最长公开等待为 600 秒，因此真实 Codex 复验前必须把新宿主配置应用到当前用户配置。执行：

```powershell
pwsh.exe -NoProfile -File scripts/register.ps1
$RegisterExit = $LASTEXITCODE
Write-Host "scripts/register.ps1 exit=$RegisterExit"
```

然后只读检查当前 Codex `config.toml` 中本 Worker 的配置，要求：

```text
mcp_servers.agy_worker.tool_timeout_sec = 660
enabled_tools = 6 个既有 agy_* 工具
```

同时确认：

- 用户原有 `developer_instructions` 前缀仍保留；
- managed AGY Worker routing block 只有一份；
- 其他 MCP 配置没有被覆盖；
- 不修改业务项目的任何 `AGENTS.md`。

如果 Codex 需要重载 MCP/新开会话才能读取更新后的注册配置，按宿主正常方式重新加载；不要用 direct `agy` CLI 替代 MCP 验收。

## 6. Hot/cold capabilities 回归

上一轮已通过，但当前 server 有变化，重新做轻量确认：

- 热 `agy_capabilities` 顶层仅 `schema_version/workspaces`；
- workspace 为 `workspace_id/registered_path/allowed_commands`，仅存在额外 worktree 时带 `known_worktrees`；
- 热结果不含 controller/limits/permissions/git flags；
- `agy://capabilities` 与 `agy://workspaces` 冷资源仍完整。

记录 hot JSON bytes；预计仍约上一轮 700B，但以实际结果为准。

## 7. 新 Codex 会话真实行为

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

## 8. 自适应 Status 等待与 coalescing 复核

第一次只拿到 `task_id` 而还没有可作为基线的 revision 时，Codex 可以只调用：

```text
agy_status(task_id=<id>)
```

MCP 内部应把这次变成即时快照 `wait_ms=0`，不应因为公开默认 50000 而先阻塞 50 秒。拿到非终态 revision 后，后续 status 应传：

```text
after_revision=<last visible revision>
wait_ms=<可省略，或 Codex 自主选择 50000..600000>
```

`wait_ms` 省略时公开默认 50000。不要把“必须显式看到 50000”作为硬门槛，因为正确调用可以省略字段使用 schema 默认值；如果显式填写，则必须在 50000..600000 范围内。允许 Codex 根据预计耗时选择更长预算，不要求固定档位。

记录：

- Codex 可见 `agy_status` 调用次数；
- 每次可见调用的传入 `after_revision` / `wait_ms`（区分“省略=默认 50000”）；
- 每次返回 revision/status/unchanged；
- 如果能看 Controller/internal probe，记录每个内部 status 的 wait_ms，硬性要求 `0 <= wait_ms <= 25000`；
- 如果能观察内部 revision，记录一个外部 status 内被合并的 progress revision 数量；不是硬性要求。

不要用固定“最多 N 次”作为硬门槛，因为构建时长与 Codex 自主预算选择不同。核心判定是：**短时间连续 progress revision 不再造成 revision 1→2→3→… 每个都回到 Codex。** 一个公开 50～600 秒总窗口内，MCP 应在内部持续消费中间 progress/unchanged，并在 terminal 或总等待预算结束时才返回一个观察点。

总等待 deadline 不能因中间 revision 重置。若 Codex 选择 `wait_ms=120000`，不是“每个 revision 再等 120 秒”；内部应按剩余预算切成多个不超过 25000ms 的 Controller long-poll。

### deadline 最终快照硬条件

若最后一个内部 long-poll 返回 running/unchanged 后公开总 deadline 已到，MCP 必须再执行一次内部 `wait_ms=0` 最终快照；若任务已经 terminal，应直接返回 terminal，不能把此前缓存的 running/unchanged 当作本轮最终结果。该最终快照不重新开启新的等待窗口。

### terminal 提前返回硬条件

长预算不是固定 sleep。若一次外部 status 选择例如 `wait_ms=120000`，而 AGY 在调用后约 20 秒进入 terminal，本次 tool call 应在 terminal 出现后尽快返回；不得继续等待到 120 秒。若实际业务构建没有自然形成便于判断的场景，可以用等价受控 probe 验证，但要区分 probe 与真实业务证据。

若公开总窗口结束仍非终态，Codex 应立即再次 `agy_status`。两次 status 之间不得出现“我再等一轮”“继续等待”等面向用户的等待说明。若返回 `unchanged=true`，TextContent 应提示继续轮询/无需用户消息。

这不是 server-initiated push 验收：不要要求 webhook、MCP task notification 或 Worker 主动新开 Codex turn。验收目标是**已有的挂起 status tool call 在 AGY terminal 时返回，从而让同一 Codex turn 继续**。

## 9. 返回 ChatGPT 的报告模板

```text
branch_head:
adaptive_status_wait_target_is_ancestor:
post_target_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:

schema_regeneration_diff: none/details
mcp_tool_count:
worker_kind_enum:
worker_permission_keys:
worker_limit_keys:
continue_schema_matches_worker_surface: yes/no
hidden_shell_absent: yes/no
hidden_code_write_absent: yes/no
hidden_artifact_summary_limits_absent: yes/no
status_schema_keys:
status_wait_default:
status_wait_minimum:
status_wait_maximum:
status_49999_rejected_before_controller: yes/no
status_600001_rejected_before_controller: yes/no

register_exit:
codex_tool_timeout_sec:
user_developer_instructions_preserved: yes/no
managed_routing_block_count:
other_mcp_config_preserved: yes/no

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
first_status_without_revision_was_immediate_snapshot: yes/no/unknown
status_public_wait_values_or_omitted:
internal_status_wait_values_if_observed:
internal_status_wait_all_le_25000: yes/no/unknown
progress_revision_roundtrip_pattern:
total_deadline_reset_seen: yes/no/unknown
deadline_final_snapshot_seen: yes/no/unknown
long_wait_terminal_early_return: yes/no/not_observed
long_wait_selected_ms_if_observed:
long_wait_actual_elapsed_if_observed:
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