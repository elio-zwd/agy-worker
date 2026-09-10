# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: mcp_request_status_fix_awaiting_local_recheck
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
mcp_request_status_target_head: 094445f4c57663375a725ecae74d236ddaa24567
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
hot_capabilities_local_at_b34e: passed_700_bytes
windows_check_at_b34e: exit_0_102_passed_0_failed_0_skipped_0_warnings
real_codex_route_at_b34e: mcp_route_succeeded_but_efficiency_failed
real_task_at_b34e: succeeded_exit_0_errors_0_warnings_26
current_windows_check: not_run_after_request_status_fix
current_real_codex_route: not_run_after_request_status_fix
open_findings: needs_request_status_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 2026-09-10 本地复验结论：代码合同 PASS，真实 Codex 热路径 FAIL

本地 AI 在 `b34e9879cf60776a2970f56884fc1efecd99d531` 获得了新的权威 Windows 证据：

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
- Runtime progress 记录每次 `captured_bytes` 变化都会 `_save()` 并提高 revision，因此只强调 `wait_ms=25000` 不能减少工具轮数。

## 当前修补

- [x] T26 RED：`cb3ebcd...` 增加 MCP consumer-visible 测试，要求 `agy_worker/agy_continue` schema 不再暴露 shell/code_write/write paths 和 artifact/summary byte budgets；MCP 请求进入 Controller 前补齐安全内部默认值；隐藏字段的非安全旧请求在 MCP 边界拒绝；单次 status 能合并 progress/unchanged。
- [x] T27 RED：`09ca41a...` 把 unchanged TextContent 行为锁成“继续轮询，无需用户消息”，不再只是“无变化”。ChatGPT Web 未运行 Windows RED，不把 RED 已失败写成执行事实。
- [x] T28 MCP 外部/内部模型分层：`7ea69d7...` 新增 `McpPermissions/McpLimits/McpWorkerRequest/McpContinueRequest`。Codex 公开 schema 只保留当前可用权限；limits 只允许 `total_timeout_sec`。内部 `Permissions/Limits/WorkerRequest/ContinueRequest` 仍保留完整 fail-closed 字段与默认值。
- [x] T29 status coalescing：`55f81cc...` 在 MCP server 的单次 `wait_ms` 总预算内吞掉中间 progress/unchanged revision，优先返回终态；`wait_ms=0` 即时查询语义不变，Runtime progress/audit 不节流、不删除。
- [x] T30 schema 事实来源同步：`1084aad...` 让 `manage schemas` 使用 MCP 外部模型；tracked `agy_worker.json/agy_continue.json` 已同步到瘦契约，最终 schema commit `e2fd6b8...`。
- [x] T31 测试质量复核：MCP tool schema 通过 wire alias `model_dump(by_alias=True)['inputSchema']` 检查；增加总等待预算回归，确保内部 revision 变化不会把 25 秒总预算重置为每轮新的 25 秒。当前代码+测试 target：`094445f4c57663375a725ecae74d236ddaa24567`。
- [x] T32 安全边界：本轮未修改 Runtime/Controller 权限实现、单执行槽、协议版本或工具数量；未修改任何 `AGENTS.md`。
- [ ] T33 当前 target Windows 全量回归：`scripts/check.ps1` exit 0、0 failed；`git diff --check` exit 0。
- [ ] T34 MCP schema 实机复核：新会话看到的 `agy_worker/agy_continue` 不含 shell/code_write/write fields，也不含 artifact/summary byte budgets；只允许 `total_timeout_sec`。
- [ ] T35 真实 Codex 第一提交复核：发送“使用AGY跑编译测试”，`agy_worker` 第一次调用即应通过，不再因 `shell=true` 或 `artifact_max_bytes` 重试。
- [ ] T36 status coalescing 复核：记录 Codex 可见 `agy_status` 调用次数与参数；中间 progress revision 应在单次 MCP 调用内部合并。若 25 秒总窗口到期仍非终态，下一次 status 应直接调用，不插入“我再等一轮”等用户消息。
- [ ] T37 原会话终态复核：正常任务应由同一 Codex 会话继续到 Worker terminal；若仍提前结束，保存 transcript，区分 MCP 行为与 Codex 宿主行为后再判断下一步。
- [ ] T38 ChatGPT 收到本地证据后执行 `receiving-code-review` + `verification-before-completion`；全部门禁满足后才恢复 `accepted`。

## 设计取舍

本轮继续遵守用户要求：**不修改任何 `AGENTS.md`**。业务项目现有“AGY是MCP”规则保持原状。

公开 MCP schema 现在有意收缩，但内部 Runtime 模型不删除旧 fail-closed 字段。这样 Codex 不会再被不可用权限诱导，维护/内部验证仍能明确拒绝 shell/code_write。`summary_max_bytes` 与 `artifact_max_bytes` 改为服务端内部预算；普通 MCP 只在确需延长任务时设置 `total_timeout_sec`。

本轮不节流 Runtime progress revision。完整进度仍保存用于审计与本地诊断；仅在 MCP server 的一次 25 秒总等待预算内 coalesce 中间 revision，因此优化 Codex round-trip 而不牺牲证据。

## 保留的已验证事实

`b34e...` 之前已经真实验证：hot capabilities 700B、冷资源完整、没有 pre-MCP shell/direct CLI/chat-thread 路由；真实 `jianyu_compile_test` 最终 succeeded/exit 0。**这些证据不能替代 `094445f...` 新请求 schema/status coalescing 代码的 Windows 与真实 Codex 复验。**

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。
