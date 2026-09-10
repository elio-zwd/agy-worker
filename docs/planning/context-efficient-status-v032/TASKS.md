# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: adaptive_status_wait_awaiting_local_recheck
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
original_production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
previous_validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
routing_direct_cli_fix_head: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
routing_windows_pass_head: 87fb3ddd34c595c0b1be78db1a446711b994895f
routing_chat_thread_fix_head: 73a2015c04dc84ad0d755cfe4831fb84fe4b6e17
routing_upgrade_fix_head: 31119240a5d5388b17f3f0d724644a479ec77b21
mcp_hot_path_code_head: 70577e68e9843b187feeda9080d5ce976c19fbe4
mcp_hot_path_local_fail_head: b34e9879cf60776a2970f56884fc1efecd99d531
mcp_request_status_red_head: cb3ebcd024f47bca0a06cc0876112477ea41a832
mcp_unchanged_narration_red_head: 09ca41af1b36baaeec53dfbbabb2e7b06a0bd76c
mcp_public_request_model_head: 7ea69d7c028eeb1f2af4369642f8081c4f8c1a54
mcp_request_status_code_head: 55f81cc195d9d825b9865f7c412d58b67beef55f
mcp_schema_generator_head: 1084aad69050ccd05bb02a3ad68b42545bab807e
mcp_schema_head: e2fd6b85062398cc9de31f0d29a9a9022bc57340
previous_mcp_request_status_target_head: 094445f4c57663375a725ecae74d236ddaa24567
adaptive_wait_plan_head: 344728eba372c8f86f1473885cdc5ea7eb071a7b
adaptive_wait_tests_head: f90ac64572f45753a54aa4ee029bf25b76c09bd0
adaptive_wait_public_model_head: a143fe9589ff9b3ea1be8c68cad25b9525f914c2
adaptive_wait_server_head: ed7cb63879ab436dfa5b80dc23ddc0bd095876d6
adaptive_wait_schema_generator_head: 0c46fe6daf279e1f287a6fc5e3590bca439f4e8e
adaptive_wait_schema_head: d8bf2521e673912e7d4fde0480927f84d3c595c6
adaptive_wait_host_timeout_test_head: d51676ae126f3c938865e0c03738a3523df0f937
adaptive_wait_production_target_head: 36d820aac4786eafdfb047a08e8fe038392f63d9
latest_docs_before_tracker_head: 3faa296aa79c0df56f09826c39533fe039bd3735
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
public_status_wait_default_ms: 50000
public_status_wait_min_ms: 50000
public_status_wait_max_ms: 600000
internal_status_slice_max_ms: 25000
codex_mcp_tool_timeout_sec: 660
hot_capabilities_local_at_b34e: passed_700_bytes
windows_check_at_b34e: exit_0_102_passed_0_failed_0_skipped_0_warnings
real_codex_route_at_b34e: mcp_route_succeeded_but_efficiency_failed
real_task_at_b34e: succeeded_exit_0_errors_0_warnings_26
current_windows_check: not_run_after_adaptive_status_wait
current_schema_regeneration: not_run_after_adaptive_status_wait
current_register_recheck: not_run_after_adaptive_status_wait
current_real_codex_route: not_run_after_adaptive_status_wait
open_findings: needs_adaptive_status_wait_local_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 2026-09-10 本地复验结论：代码合同 PASS，真实 Codex 热路径 FAIL

本地 AI 在 `b34e9879cf60776a2970f56884fc1efecd99d531` 获得了权威 Windows 证据：

```text
scripts/check.ps1: exit 0
pytest: 102 passed / 0 failed / 0 skipped / 0 warnings
compileall: PASS
git diff --check: exit 0
working tree before/after: clean
```

MCP 热/冷 capabilities 也真实符合上一轮目标：热 `agy_capabilities` 只有 `schema_version/workspaces`，实际约 700B；没有 controller/limits/permissions/git flags；两个冷资源仍保留完整信息。

真实新 Codex 会话对“使用AGY跑编译测试”已正确进入 `agy_capabilities → agy_worker → agy_status`，没有 pre-MCP shell、direct AGY CLI 或 chat/thread/subagent 绕过；最终任务 `task-7ca1403e181c4915884502e863603e8e` succeeded，`jianyu_compile_test` exit 0、errors 0、warnings 26、未读取 artifact。

但总体仍判 FAIL，原因是：

1. 前两次 `agy_worker` 请求主动填写 `artifact_max_bytes=20000`，低于 1 MiB 下限，被拒绝；第三次省略后才成功。
2. 前两次请求还填写 `permissions.shell=true`。虽然未执行 direct shell，但公开 MCP schema 当时错误地把 Runtime 永远拒绝的 shell 权限暴露给 Codex。
3. `agy_status` 虽然每次都用了 `after_revision=1..14` 和 `wait_ms=25000`，Runtime 的 `captured_bytes/progress` 每次变化都会提高 revision，使 long-poll 很快返回，因此仍产生很多 Codex tool round-trip。
4. unchanged 后出现用户可见“我再等一轮”说明；原 Codex 会话也在终态前结束，最终 terminal 是后续 MCP status follow-up 取得。

## 根因确认

- `config/runtime.toml` 正式 `enabled_kinds` 不含 shell；Runtime 对 `permissions.shell` / `code_write` 继续 fail-closed。
- 旧 `WorkerRequest` / `schemas/agy_worker.json` 却公开了 `kind=shell`、`permissions.shell`、`code_write` 与 artifact/summary byte budgets，形成“schema 宣称可填、Runtime 永远拒绝/无需填”的矛盾。
- Runtime fingerprint 基于 Pydantic 完整 `WorkerRequest.model_dump()`；MCP 瘦请求只要扩展回原有默认值，正常省略字段的 request fingerprint 不变。
- Runtime progress 记录每次 `captured_bytes` 变化都会 `_save()` 并提高 revision，因此只强调固定 25 秒公开等待不能减少长任务的 Codex tool round-trip。
- `manage schemas` 如果继续使用内部 `StatusRequest`，会把公开 50～600 秒合同重新生成回 0～25 秒；因此需要 `McpStatusRequest` 作为公开 schema 事实来源。
- Codex MCP 注册原 `tool_timeout_sec=60` 小于最大合法 600 秒 status 等待；若不调整，宿主会在 Worker 合法等待结束前截断，因此本轮把宿主上限提高到 660 秒。

## 已完成的修补

- [x] T26 RED：`cb3ebcd...` 增加 MCP consumer-visible 测试，要求 `agy_worker/agy_continue` schema 不再暴露 shell/code_write/write paths 和 artifact/summary byte budgets；MCP 请求进入 Controller 前补齐安全内部默认值；隐藏字段的非安全旧请求在 MCP 边界拒绝；单次 status 能合并 progress/unchanged。
- [x] T27 RED：`09ca41a...` 把 unchanged TextContent 行为锁成“继续轮询，无需用户消息”，不再只是“无变化”。ChatGPT Web 未运行 Windows RED，不把 RED 已失败写成执行事实。
- [x] T28 MCP 外部/内部 worker 模型分层：`7ea69d7...` 新增 `McpPermissions/McpLimits/McpWorkerRequest/McpContinueRequest`。Codex 公开 schema 只保留当前可用权限；limits 只允许 `total_timeout_sec`。内部模型仍保留完整 fail-closed 字段与默认值。
- [x] T29 status coalescing：`55f81cc...` 在 MCP server 的单次等待预算内吞掉中间 progress/unchanged revision，优先返回终态；Runtime progress/audit 不节流、不删除。
- [x] T30 schema 事实来源同步：`1084aad...` 让 worker/continue 的 `manage schemas` 使用 MCP 外部模型；tracked schema 同步。
- [x] T31 上一版测试质量复核：MCP tool schema 通过 wire alias 检查；增加总等待预算回归。上一版代码+测试 target 为 `094445f...`。
- [x] T32 安全边界：上一版未修改 Runtime/Controller 权限实现、单执行槽、协议版本或工具数量；未修改任何 `AGENTS.md`。

## 2026-09-11 自适应 status 等待

用户确认最终设计：

```text
public agy_status default: 50s
public Codex-selected range: 50..600s
internal Controller long-poll slice: <=25s
terminal: return immediately, do not sleep to budget
push/webhook/task-subscription: not implemented
```

这是“一个挂起中的 `agy_status` tool call 在 AGY terminal 时返回”的等价唤醒效果，不是 Worker 主动创建新的 Codex turn。

- [x] T39 设计与计划：`344728e...` 创建 `ADAPTIVE-STATUS-WAIT-PLAN.md`；用户批准默认 50 秒、Codex 自主 50～600 秒、terminal 提前返回、内部 <=25 秒分片。后续 `a351d5b...` 补充发现的 Codex 宿主 timeout 必要条件。
- [x] T40 测试先行：`483e217...` / `f90ac64...` 增加公开 schema default/min/max、非法 49999/600001、默认 50 秒分片、600 秒 terminal 提前返回、无 revision 即时快照、单一 total deadline 等行为测试。**ChatGPT Web 未执行 pytest，RED execution = not_run_in_chatgpt_web。**
- [x] T41 MCP 外部/内部 status 模型：`a143fe9...` 新增 `McpStatusRequest(wait_ms=50000, 50000..600000)`；内部 `StatusRequest` 保持 0..25000。
- [x] T42 Server 自适应 coalescing：`ed7cb63...` 让 `agy_status` 对外使用 `McpStatusRequest`；无 `after_revision` 转内部即时 `wait_ms=0`；已有 revision 时使用公开总 deadline 并按 <=25000ms 内部分片；terminal 立即返回；server instructions 不再固定要求 25000。
- [x] T43 Schema generator 与 tracked schema：`0c46fe6...` 让 `manage schemas` 使用 `McpStatusRequest`；`d8bf252...` 同步 `schemas/agy_status.json` 为 default 50000/min 50000/max 600000。
- [x] T44 Codex 宿主 timeout 测试与实现：`d51676a...` 先增加 `tool_timeout_sec > 600` 回归约束；`36d820a...` 把 `manage.register()` 的本 Worker `tool_timeout_sec` 从 60 提高到 660。**新的生产代码+测试+公开 schema target：`36d820aac4786eafdfb047a08e8fe038392f63d9`。**
- [x] T45 文档/验收同步：README、`docs/实施设计.md`、SPEC、ADAPTIVE plan、`LOCAL-ROUTING-RECHECK.md` 已更新为 50～600 秒公开合同、<=25 秒内部分片、660 秒宿主上限、非 push 语义和重新注册要求。
- [ ] T46 当前 target Windows 全量回归：`scripts/check.ps1` exit 0、0 failed；`git diff --check` exit 0。必须记录新鲜 passed/failed/skipped/warnings 与 compileall；旧 102 passed 不能替代。
- [ ] T47 Schema/注册实机复核：真实 `list_tools` 的 `agy_status.wait_ms` 为 default 50000/min50000/max600000；非法 49999/600001 在 Controller 前拒绝；`manage schemas` 无 tracked diff；重新运行 `scripts/register.ps1` 后 Codex config 的 `tool_timeout_sec=660` 且用户 instructions/其他 MCP 保留。
- [ ] T48 真实 Codex 第一提交复核：只发“使用AGY跑编译测试”，`agy_worker` 第一调用即成功提交，不出现 shell/artifact/summary 隐藏字段重试，无 discovery shell/direct CLI/chat-thread。
- [ ] T49 自适应 status 实机复核：第一次无 revision status 为即时快照；后续 `after_revision` + 省略默认 50 秒或自主 50～600 秒；Controller/internal probe 若可见，每段 <=25000ms；progress revision 不逐个回 Codex；deadline 不因 revision 重置。
- [ ] T50 terminal 提前返回与原会话闭环：较长预算下 AGY terminal 后 tool call 应提前返回而非睡满预算；两次 status 之间无用户等待叙述；同一 Codex 会话继续到 Worker terminal。若场景未自然观察到必须写 `not_observed`，不能伪造。
- [ ] T51 ChatGPT 收到本地证据后执行 `receiving-code-review` + `verification-before-completion`；全部门禁满足后才恢复 `accepted`。

## 设计取舍

本轮继续遵守用户要求：**不修改任何 `AGENTS.md`**。业务项目现有“AGY是MCP”规则保持原状。

公开 worker/continue schema 有意收缩，但内部 Runtime 模型不删除旧 fail-closed 字段。`summary_max_bytes` 与 `artifact_max_bytes` 是服务端内部预算；普通 MCP 只在确需延长任务时设置 `total_timeout_sec`。

status 则反向做“公开总预算 / 内部单段预算”分层：Codex 面向任务预计耗时选择 50～600 秒，一次 MCP 调用内部仍只使用 <=25 秒 Controller long-poll。这样保留 Runtime 完整 progress/revision 审计，不需要通过节流或删除进度事实来减少模型轮询。

`tool_timeout_sec=660` 只扩大 Codex 宿主允许该 MCP 调用存活的上限，不改变 AGY 任务 `total_timeout_sec`、公开 status 最大 600 秒、Controller HTTP timeout 30 秒、内部 status 最大 25 秒、权限或协议。

本轮不实现 webhook、server-initiated push 或 MCP Tasks subscription。若未来确认 Codex 宿主支持可靠的 task notification → model continuation，需要作为独立设计重新评估，不能把当前挂起 tool call 伪装成 push。

## 保留的已验证事实

`b34e...` 已真实验证：hot capabilities 700B、冷资源完整、没有 pre-MCP shell/direct CLI/chat-thread 路由；真实 `jianyu_compile_test` 最终 succeeded/exit 0。**这些证据不能替代 `36d820a...` 自适应 status、MCP schema 与 660 秒注册配置的 Windows/真实 Codex 复验。**

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。