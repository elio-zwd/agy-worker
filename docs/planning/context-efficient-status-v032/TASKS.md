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

## 当前复验结论

首轮自适应本地复验在 `3086915...` 为 FAIL：`scripts/check.ps1` exit 1，pytest 109 passed / 5 failed，compileall PASS，diff-check PASS；schema regeneration 有 3 个 description drift；注册 660 已通过；真实新 Codex 会话未执行。

ChatGPT 按 `receiving-code-review + systematic-debugging` 技术复核后确认：4 个 StopIteration 来自测试 patch 共享标准库 `time.monotonic` 污染 asyncio；第 5 个失败来自旧测试仍断言 `tool_timeout_sec=60`；三个 schema drift 来自 Pydantic 模型 docstring 自动生成的 `description` 未同步到 tracked generated files。

对应修补：

- `590629e...`：新增 `tests/conftest.py` 隔离 server 测试时钟，不修改生产 deadline 逻辑；
- `3a6d703...`：旧注册测试合同从 60 同步为 660；
- `aa8fc85...` / `0dda8b1...` / `802f404...`：同步 worker/continue/status generated schema description。

固定二次复验 target：

```text
802f40405ea74ede2b437887ff6ba9dd2daa2edb
```

远端 compare 已确认 `3086915... → 802f404...` 只修改 `tests/conftest.py`、`tests/test_controller_reconnect.py` 和三个 `schemas/*.json`；没有 `src/`、Runtime、Controller、权限、协议、config、依赖或 `AGENTS.md` 变化。target 后只有验收/Task 文档变化。

## 下一轮门禁

严格执行 `docs/planning/context-efficient-status-v032/LOCAL-ROUTING-RECHECK.md`：

- [ ] `scripts/check.ps1` exit 0 / pytest 0 failed / compileall PASS，并确认 StopIteration 消失；
- [ ] `python -m agy_worker.manage schemas` 后 `git diff -- schemas` 为空；
- [ ] 注册仍为 `tool_timeout_sec=660` 且用户配置/其他 MCP 保留；
- [ ] 新 Codex 会话只发“使用AGY跑编译测试”，验证第一笔 worker、无 discovery/direct CLI/chat-thread、真实自适应 status、同会话 terminal 和 operation exit code；
- [ ] ChatGPT 收到新鲜证据后再执行 `verification-before-completion`。

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。