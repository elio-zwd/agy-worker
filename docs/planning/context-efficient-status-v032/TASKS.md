# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的最终验收状态源。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 最终状态

```text
phase: accepted_for_merge
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
windows_check: pass_114_passed_0_failed_0_skipped_0_warnings
schema_regeneration: pass_no_diff
register_recheck: pass_tool_timeout_660_config_preserved
real_codex_route: pass_core_flow
merge_authorized: true
open_pr: "#2"
```

## 自动化与生成物验收

2026-09-11 本地复验得到：

```text
scripts/check.ps1: exit 0
pytest: 114 passed / 0 failed / 0 skipped / 0 warnings
compileall: PASS
StopIteration: absent
git diff --check: exit 0
python -m agy_worker.manage schemas: exit 0
git diff -- schemas: empty
Codex MCP tool_timeout_sec: 660
user developer instructions: preserved
other MCP config: preserved
```

此前 `3086915...` 的 5 个 pytest 失败已经完成技术复核并关闭：4 个 `StopIteration` 来自测试 patch 共享标准库 `time.monotonic` 污染 asyncio；第 5 个来自遗留测试仍断言旧 `tool_timeout_sec=60`。三个 schema drift 是 Pydantic docstring 自动生成 `description` 后 tracked generated files 未同步。对应修补固定在 `802f404...`，没有修改 Runtime/Controller 权限或协议语义。

## 真实 Codex / AGY 验收

用户随后在真实业务项目中连续执行 AGY 编译测试：

1. 第一次 `jianyu_compile_test`：`succeeded`，operation exit code `0`，约 225 秒，errors `0`，warnings `25`；Codex 可见流程为 `agy_capabilities → agy_worker → agy_status`，单次可见 status 直接返回 terminal。
2. 第二次相同命令：`succeeded`，operation exit code `0`，约 201 秒，errors `0`，warnings `25`；已知 workspace 后直接 `agy_worker → agy_status`，单次可见 status 直接返回 terminal。
3. 第三次相同命令：Worker 正常提交并等待，最终 `failed` / operation exit code `130` / `termination_reason=timed_out`，命令进程约 267 秒；日志停在 `:app:kspDebugUnitTestKotlin` 附近，没有编译错误或测试断言失败。

前两次 201～225 秒任务均通过单个 Codex 可见 `agy_status` 调用等到 terminal，证明 v0.3.2 的长等待/coalescing 核心目标在真实使用中生效。第三次失败属于后续已知问题，不判定为本 PR 的功能回归：Worker 的任务 `total_timeout_sec` 默认是 300 秒，而真正启动命令时使用“总预算减去前置 AGY/快照/调度耗时”的剩余时间，因此进程约 267 秒被终止与该默认预算相符。

真实 follow-up 还观察到一次 Codex 主动发送低于公开下限的 `agy_status.wait_ms`，被 MCP 以 `invalid_request: wait_ms 最小为 50000` 正确拒绝，随后重试取得既有 terminal。这是调用侧易用性问题，当前 fail-closed 行为正确，也不阻塞本版本使用。

上述两个非阻断问题（长构建默认任务预算不足、follow-up status 偶发选择非法短等待）不在 PR #2 内继续修复；合并后单独建立后续 Draft PR 记录，当前项目暂停继续开发。

## Merge Gate

```text
merge_authorized: true
```

2026-09-11 用户明确授权将 PR #2 合并到 `main`。采用 merge commit 保留完整开发与修补历史；不启用 auto-merge，不删除远端分支。