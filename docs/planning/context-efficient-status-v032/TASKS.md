# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: adaptive_status_wait_recheck_round2_awaiting_local
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
adaptive_wait_host_timeout_head: 36d820aac4786eafdfb047a08e8fe038392f63d9
adaptive_wait_deadline_red_head: f17b00cb026d0194b3a19663e860c5970952653d
adaptive_wait_runtime_code_head: 02201bd5b779117fb9e04c808b36e95ea80996be
adaptive_wait_previous_local_fail_head: 3086915c2c8865271bcea18275b3fa69964df935
adaptive_wait_clock_test_fix_head: 590629e98b475b20b050e39d4e357fa5a11314b6
adaptive_wait_timeout_test_fix_head: 3a6d7037a474340147dff63aac36ffe36dace160
adaptive_wait_schema_description_sync_head: 802f40405ea74ede2b437887ff6ba9dd2daa2edb
adaptive_wait_recheck_target_head: 802f40405ea74ede2b437887ff6ba9dd2daa2edb
latest_docs_before_tracker_head: 8cb26f9e6abb6580e65f927b281640277ad7b5dc
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
current_windows_check: fail_at_3086915_109_passed_5_failed_0_skipped_2_warnings
current_schema_regeneration: drift_at_3086915_three_generated_schemas_description_only
current_register_recheck: pass_at_3086915_tool_timeout_660_config_preserved
current_real_codex_route: not_run_at_3086915
open_findings: rerun_windows_schema_and_real_codex_on_802f404
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

## 已完成的上一轮修补

- [x] T26 RED：`cb3ebcd...` 增加 MCP consumer-visible 测试，要求 `agy_worker/agy_continue` schema 不再暴露 shell/code_write/write paths 和 artifact/summary byte budgets；MCP 请求进入 Controller 前补齐安全内部默认值；隐藏字段的非安全旧请求在 MCP 边界拒绝；单次 status 能合并 progress/unchanged。
- [x] T27 RED：`09ca41a...` 把 unchanged TextContent 行为锁成“继续轮询，无需用户消息”。ChatGPT Web 未运行 Windows RED，不把 RED 已失败写成执行事实。
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

- [x] T39 设计与计划：`344728e...` 创建 `ADAPTIVE-STATUS-WAIT-PLAN.md`；用户批准默认 50 秒、Codex 自主 50～600 秒、terminal 提前返回、内部 <=25 秒分片。后续 `a351d5b...` 补充 Codex 宿主 timeout 必要条件。
- [x] T40 测试先行：`483e217...` / `f90ac64...` 增加公开 schema default/min/max、非法 49999/600001、默认 50 秒分片、600 秒 terminal 提前返回、无 revision 即时快照、单一 total deadline 等行为测试。**ChatGPT Web 未执行 pytest，RED execution = not_run_in_chatgpt_web。**
- [x] T41 MCP 外部/内部 status 模型：`a143fe9...` 新增 `McpStatusRequest(wait_ms=50000, 50000..600000)`；内部 `StatusRequest` 保持 0..25000。
- [x] T42 Server 自适应 coalescing：`ed7cb63...` 让 `agy_status` 对外使用 `McpStatusRequest`；无 `after_revision` 转内部即时 `wait_ms=0`；已有 revision 时使用公开总 deadline 并按 <=25000ms 内部分片；terminal 立即返回。
- [x] T43 Schema generator：`0c46fe6...` 让 `manage schemas` 使用 `McpStatusRequest`；初版 tracked status schema 同步 default/min/max。
- [x] T44 Codex 宿主 timeout：`d51676a...` 增加 `tool_timeout_sec > 600` 约束；`36d820a...` 把 `manage.register()` 的本 Worker `tool_timeout_sec` 从 60 提高到 660。
- [x] T45 第一轮规格审查发现 deadline 边界竞态：`f17b00c...` 先添加回归；`02201bd...` 在 deadline 到达时使用当前 revision 做内部 `wait_ms=0` 最终快照，不重新开启等待窗口。**ChatGPT Web 未执行该 RED/GREEN 测试。**
- [x] T46 文档/验收同步：README、实施设计、SPEC、ADAPTIVE plan 和本地复验文档同步为 50～600 秒公开合同、<=25 秒内部分片、deadline 最终快照、660 秒宿主上限、非 push 语义。

## 2026-09-11 首轮自适应本地复验：FAIL 与技术复核

本地 AI 在 `3086915c2c8865271bcea18275b3fa69964df935` 返回：

```text
scripts/check.ps1: exit 1
pytest: 109 passed / 5 failed / 0 skipped / 2 warnings
compileall: PASS
git diff --check: exit 0
schema regeneration: 3 个 schema 出现 description 差异，副作用已撤销
register: exit 0 / tool_timeout_sec=660 / 用户配置保留
hot capabilities: 700 bytes / 冷资源保留
真实新 Codex 自然语言会话: 未执行
```

ChatGPT 没有直接照改，而是按 review/debugging 逐条验证。结论：

- 4 个 `StopIteration` 的根因不是 deadline 生产逻辑，而是测试把 `server_module.time.monotonic` 打桩时实际修改了 Python 共享 `time` 模块，`asyncio` event loop 也会消耗同一有限 iterator。
- 第 5 个失败来自 `tests/test_controller_reconnect.py` 仍硬编码旧 `tool_timeout_sec == 60`；当前用户批准合同、`manage.register()` 和真实注册证据均为 660。
- 3 个 schema regeneration 差异来自模型 docstring 自动生成的 `description` 没有进入 tracked generated files；生成器事实来源本身正确。
- 真实 Codex “使用AGY跑编译测试”没有执行，因此路由、第一笔 worker 参数、真实 status round-trip 和同会话 terminal 仍然未验证。

已实施最小修补：

- [x] T53 测试时钟隔离：`590629e...` 新增 `tests/conftest.py`，每个测试先把 `server_module.time` 替换成模块局部 `SimpleNamespace(monotonic=stdlib_time.monotonic)`；原 deadline 测试继续 monkeypatch 同名入口，但不再污染 asyncio 的标准库时钟。**没有改生产 server deadline 逻辑。**
- [x] T54 旧注册测试合同：`3a6d703...` 把 reconnect 测试名和断言从 60 同步为 660；`manage.register()` 生产代码未改。
- [x] T55 generated schema 同步：`aa8fc85...`、`0dda8b1...`、`802f404...` 将 Pydantic 实际生成的 worker/continue/status `description` 补入 tracked schema；模型、生成器与公开数值合同未变。
- [x] T56 远端范围审查：`3086915... → 802f404...` 只有 `tests/conftest.py`、`tests/test_controller_reconnect.py` 和三个 `schemas/*.json`；没有 `src/`、Controller、Runtime、权限、协议、config、依赖或 `AGENTS.md` 修改。**新的本地复验 target：`802f40405ea74ede2b437887ff6ba9dd2daa2edb`。**
- [ ] T57 Windows 二次回归：在 target 后仅文档的 HEAD 上执行 `scripts/check.ps1`，要求 exit 0 / 0 failed；记录 warnings，并确认不再出现 StopIteration。
- [ ] T58 schema 二次生成：`python -m agy_worker.manage schemas` 后 `git diff -- schemas` 必须为空；若不为空返回完整具体 diff。
- [ ] T59 真实 Codex 闭环：新会话只发“使用AGY跑编译测试”，记录路由、第一笔 worker 参数、自适应 status、terminal 提前返回、无用户等待叙述以及同会话是否到 terminal。
- [ ] T60 ChatGPT 收到二次本地证据后按 `receiving-code-review + verification-before-completion` 复核；只有自动化、schema 与真实 Codex 闭环均通过才恢复 `accepted`。

## 设计取舍

本轮继续遵守用户要求：**不修改任何 `AGENTS.md`**。业务项目现有“AGY是MCP”规则保持原状。

公开 worker/continue schema 有意收缩，但内部 Runtime 模型不删除旧 fail-closed 字段。`summary_max_bytes` 与 `artifact_max_bytes` 是服务端内部预算；普通 MCP 只在确需延长任务时设置 `total_timeout_sec`。

status 采用“公开总预算 / 内部单段预算”分层：Codex 面向任务预计耗时选择 50～600 秒，一次 MCP 调用内部仍只使用 <=25 秒 Controller long-poll。完整 progress/revision 继续保存；总 deadline 到达后额外一次内部 `wait_ms=0` 最终快照只用于消除截止点 stale-result 竞态，不延长公开等待预算。

`tool_timeout_sec=660` 只扩大 Codex 宿主允许该 MCP 调用存活的上限，不改变 AGY 任务 `total_timeout_sec`、公开 status 最大 600 秒、Controller HTTP timeout 30 秒、内部 status 最大 25 秒、权限或协议。

本轮不实现 webhook、server-initiated push 或 MCP Tasks subscription。若未来确认 Codex 宿主支持可靠的 task notification → model continuation，需要作为独立设计重新评估，不能把当前挂起 tool call 伪装成 push。

## 保留的已验证事实

`b34e...` 已真实验证 hot capabilities 700B、冷资源完整、没有 pre-MCP shell/direct CLI/chat-thread 路由，真实 `jianyu_compile_test` 最终 succeeded/exit 0。`3086915...` 又真实验证 public status schema 为 50000/50000/600000、非法边界在 Controller 前拒绝、注册 660 且用户配置保留、受控 probe 的内部 status 分片和 deadline 最终快照符合合同。**这些证据都不能替代 `802f404...` 的 Windows 二次回归、schema regeneration 与新的真实 Codex 闭环。**

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。