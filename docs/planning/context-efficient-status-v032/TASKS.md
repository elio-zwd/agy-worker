# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: adaptive_status_wait_recheck_round2_awaiting_local
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
adaptive_wait_runtime_code_head: 02201bd5b779117fb9e04c808b36e95ea80996be
adaptive_wait_previous_local_fail_head: 3086915c2c8865271bcea18275b3fa69964df935
adaptive_wait_clock_test_fix_head: 590629e98b475b20b050e39d4e357fa5a11314b6
adaptive_wait_timeout_test_fix_head: 3a6d7037a474340147dff63aac36ffe36dace160
adaptive_wait_schema_description_sync_head: 802f40405ea74ede2b437887ff6ba9dd2daa2edb
adaptive_wait_recheck_target_head: 802f40405ea74ede2b437887ff6ba9dd2daa2edb
local_recheck_round2_doc_head: 8cb26f9e6abb6580e65f927b281640277ad7b5dc
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
public_status_wait_default_ms: 50000
public_status_wait_min_ms: 50000
public_status_wait_max_ms: 600000
internal_status_slice_max_ms: 25000
codex_mcp_tool_timeout_sec: 660
current_windows_check: fail_at_3086915_109_passed_5_failed_0_skipped_2_warnings
current_schema_regeneration: drift_at_3086915_three_generated_schemas_description_only
current_register_recheck: pass_at_3086915_tool_timeout_660_config_preserved
current_real_codex_route: not_run_at_3086915
open_findings: rerun_windows_schema_and_real_codex_on_802f404
merge_authorized: false
open_pr: "#2_draft"
```

## 已验证历史基线

`b34e9879cf60776a2970f56884fc1efecd99d531` 曾真实通过：

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
real jianyu_compile_test: succeeded / exit 0 / errors 0 / warnings 26
```

该基线之后暴露了 worker schema 诱导隐藏字段、progress revision 逐轮回 Codex、等待叙述和原会话未到 terminal 等问题，因此不能作为当前 v0.3.2 完成证据。

## 自适应 status 最终设计

用户批准：

```text
public agy_status default: 50s
public Codex-selected range: 50..600s
internal Controller long-poll slice: <=25s
terminal: return immediately, do not sleep to budget
no after_revision: immediate internal wait_ms=0 snapshot
public deadline reached: one final internal wait_ms=0 snapshot
Codex MCP tool_timeout_sec: 660
push/webhook/task-subscription: not implemented
```

`02201bd...` 是这套行为的 Runtime/MCP 生产代码点。之后的当前修补只处理测试、tracked generated schema 和验收文档，没有修改 Runtime、Controller、权限、协议或任何 `AGENTS.md`。

## 2026-09-11 首轮自适应本地复验：FAIL

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

同时受控 probe 已观察：

```text
first status without revision -> internal wait_ms=0
internal slices -> [25000,25000], [25000,15000,5000], [25000,0]
all internal wait_ms <=25000
progress revisions coalesced
total deadline not reset
deadline final snapshot observed
600000 budget can return terminal early in controlled probe
```

这些 probe 不能替代真实 Codex transcript。

## 技术复核与修补

ChatGPT 按 `receiving-code-review + systematic-debugging` 验证了本地意见，没有直接照改。

### F1 — 4 个 StopIteration

根因：deadline 测试使用 `monkeypatch.setattr(server_module.time, 'monotonic', ...)`。`server_module.time` 原本就是 Python 共享标准库 `time` 模块，因此这个 patch 同时改写了 `asyncio` event loop 使用的 `time.monotonic`；有限 iterator 被测试代码之外的 event loop 消耗，产生 `StopIteration`。

修补：

- [x] `590629e...` 新增 `tests/conftest.py`；每个测试先把 `server_module.time` 换成模块局部 `SimpleNamespace(monotonic=stdlib_time.monotonic)`。
- [x] 原 deadline 测试继续 patch `server_module.time.monotonic`，但不会再污染 asyncio 全局时钟。
- [x] 没有为测试修改生产 deadline 实现。

### F2 — 第 5 个失败仍断言 tool_timeout_sec=60

根因：`tests/test_controller_reconnect.py` 仍保留 v0.3.1 的旧宿主 timeout 测试；而用户批准合同、`manage.register()` 以及上一轮真实注册证据都是 660。

修补：

- [x] `3a6d703...` 将测试名和断言同步到 `660`。
- [x] `manage.register()` 生产代码不回退。

### F3 — 三个 generated schema 有 description diff

根因：Pydantic 会把 `McpWorkerRequest`、`McpPermissions`、`McpLimits`、`McpStatusRequest` 的 docstring 生成到 JSON Schema `description`，但此前 tracked `agy_worker.json / agy_continue.json / agy_status.json` 手工同步时遗漏这些字段。

修补：

- [x] `aa8fc85...` 同步 worker schema description。
- [x] `0dda8b1...` 同步 continue schema 中共享 defs description。
- [x] `802f404...` 同步 status schema description。
- [x] 数值合同仍为 status 50000/50000/600000、worker/continue limits 仅 total_timeout_sec。

### F4 — 真实 Codex 闭环未执行

这不是代码意见，仍是缺失验收证据。本轮不能通过受控 probe 把它写成 PASS。

## 当前固定复验 target

```text
RECHECK_TARGET_HEAD = 802f40405ea74ede2b437887ff6ba9dd2daa2edb
```

远端 compare 已确认 `3086915... → 802f404...` 只改：

```text
tests/conftest.py
tests/test_controller_reconnect.py
schemas/agy_worker.json
schemas/agy_continue.json
schemas/agy_status.json
```

没有 `src/`、Controller、Runtime、权限、协议、config、依赖或 `AGENTS.md` 变化。`802f404...` 之后只允许验收/Task 文档。

## 下一轮门禁

严格执行：

`docs/planning/context-efficient-status-v032/LOCAL-ROUTING-RECHECK.md`

- [ ] T57 Windows 二次回归：`scripts/check.ps1` exit 0 / pytest 0 failed / compileall PASS；记录 warnings，并确认不再出现 StopIteration。
- [ ] T58 schema 二次生成：`python -m agy_worker.manage schemas` 后 `git diff -- schemas` 必须为空；如有差异返回完整具体 diff。
- [ ] T59 注册幂等确认：`tool_timeout_sec=660`、managed routing block 一份、用户 instructions 与其他 MCP 保留。
- [ ] T60 真实 Codex：新会话只发“使用AGY跑编译测试”，验证第一笔 worker、无 discovery/direct CLI/chat-thread、真实自适应 status、同会话 terminal 和真实 operation exit code。
- [ ] T61 ChatGPT 收到上述新鲜证据后执行 `receiving-code-review + verification-before-completion`；全部通过才恢复 `accepted`。

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。