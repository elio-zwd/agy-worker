# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> 规格：`SPEC.md`；实施计划：`PLAN.md`；首次完整验收协议：`LOCAL-ACCEPTANCE.md`；本轮最小复验：`LOCAL-RECHECK.md`。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: blocked_waiting_regression_recheck
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
first_acceptance_branch_head: c19491917a6f6da5ca0f3c8242dad46f3891d1cd
test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
production_code_changed_after_first_acceptance: false
package_target: 0.3.2
controller_protocol_target: 2
mcp_tool_count_target: 6
windows_check_ps1_first_run: failed_5_tests_86_passed
windows_diff_check_first_run: passed_exit_0
controller_verification_first_run: passed
real_agy_payload_acceptance_first_run: passed
codex_transcript_duplicate_check: not_available
rerun_required: scripts/check.ps1_and_git_diff_check_only
real_agy_rerun_required: false_no_production_change
merge_authorized: false
open_pr: "#2_draft"
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

当前不能标记 `accepted`：首次本地全量检查 `scripts/check.ps1` 为 exit 1。ChatGPT 已按 `receiving-code-review`、`systematic-debugging` 对 5 个失败逐项复核，确认根因均位于测试契约/测试夹具，与已经通过真实 MCP/AGY 验收的生产行为不冲突。修正后必须重新跑权威全量检查。

## 第一轮本地验收证据（2026-09-10）

```text
branch_head: c19491917a6f6da5ca0f3c8242dad46f3891d1cd
target_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
post_target_non_planning_files: none
working_tree_before: clean
package_version: 0.3.2

scripts/check.ps1: exit 1
pytest: 86 passed / 5 failed / 0 skipped / 0 warnings
git diff --check: exit 0

controller verification:
  exit 0
  server version 0.3.2 / 0.3.2
  protocol 2
  tools 6 / 6

real AGY:
  request_id: req-610ba03069e444d9b1097f93b83506ed
  task_id: task-937730060fb24a0b9309e980fc1bbc2f
  final status: succeeded
  operation exit: 0
  total errors: 0
  total warnings: 19
  submit: 148B structured / 70B TextContent
  running: 148–199B structured / 70–71B TextContent
  unchanged: 100B structured / 37B TextContent
  terminal: 571B structured / 67B TextContent
  terminal stale progress: absent
  diagnostics artifact: PASS, single TextContent, 6619B
  operation-log artifact: PASS, single TextContent, 7193B
  result artifact: PASS, single TextContent, 3988B
  duplicate_full_json_in_mcp_result: false
  codex_transcript_duplicate_check: not_available
```

真实任务自然出现多次 `unchanged=true`，没有触发自动 cancel，最终正常 `succeeded`。因此“无 revision/stdout 增长不是 hang detector”的行为已经获得真实证据。

## 五个失败的技术复核

### F1 — `tests/test_controller.py::test_two_stdio_bridges_share_controller`

**分类：旧测试契约。**

v0.3.2 文本 artifact 明确使用单载荷冷路径：实际 payload 只在唯一 TextContent，`structured_content is None`。旧测试仍读取 `artifact.structured_content["text"]`，与新合同冲突。真实 AGY 已证明 diagnostics / operation-log / result 均可通过单 TextContent 读取。

修正：集成测试改为验证 `structured_content is None`、只有一个 text block，并从该 TextContent JSON 取 `text`。

### F2 — `tests/test_runtime.py::test_terminal_public_result_is_compact_and_keeps_artifact_drill_down`

**分类：测试夹具违反既有 artifact 行大小合同。**

测试构造 20 条超长 error + 20 条超长 warning，却用默认 `json.dumps()` 把 diagnostics 写成一整行；`Artifacts.read()` 既有合同会拒绝首行超过 64 KiB。真实 AGY diagnostics 仅 6619B 且读取成功。

修正：只把 fixture 改成 `json.dumps(..., indent=2)`，让诊断仍保持大体量，但每行符合 artifact 读取边界。生产 `Artifacts.read()`、Runtime renderer 均不修改。

### F3–F5 — `tests/test_server.py`

**分类：MCP Python v2 对象属性名断言错误。**

低层 server 构造可继续使用 wire alias `structuredContent` / `isError`；Python SDK v2 读取属性是 snake_case `structured_content` / `is_error`。真实 `ClientSession` 探针也是通过 snake_case 成功读取。

修正：三个直接 handler 测试只把读取属性改为 `structured_content` / `is_error`，其余去重、字节预算和错误 body 断言不变。

## 测试修正状态

正确净内容已固定在：

```text
test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
```

从首次验收 HEAD `c19491917a6f6da5ca0f3c8242dad46f3891d1cd` 到该 HEAD 的 GitHub compare 最终只有：

```text
tests/test_controller.py  +5/-1
tests/test_runtime.py     +1/-1
tests/test_server.py      +6/-6
```

没有 `src/`、`scripts/`、`pyproject.toml`、schema、Controller/Broker/权限/数据库等生产变化。因此首次真实 AGY payload evidence 仍对应相同生产代码，不要求再次消耗 AGY 额度重跑完整构建。

### 过程记录

应用测试修正时，ChatGPT 曾误用 GitHub contents 更新接口，在 feature branch 上生成数个临时 `noop` / `placeholder` 中间 commit。没有修改 `main`、没有 force-push、没有丢失历史。随后使用已校验完整 Git tree 恢复，GitHub compare 已证明**最终净内容**只有上述 3 个测试文件的预期修正。保留这些中间 commit 以避免未经授权重写历史。

## 当前门禁

### 已满足

- [x] package metadata = `0.3.2`。
- [x] Controller protocol = `2`。
- [x] MCP tools = `6`。
- [x] 首次 `git diff --check` exit 0。
- [x] Controller verification exit 0。
- [x] 真实 AGY warning-producing build/test 成功，19 warnings、operation exit 0。
- [x] unchanged / running / terminal / TextContent 实际字节均低于 SPEC gate。
- [x] terminal 无 stale progress。
- [x] artifact 单载荷 drill-down 可读。
- [x] direct MCP probe 未出现完整 JSON text+structured 双份。
- [x] 5 个 pytest failure 已完成根因定位并形成 test-only 修正。

### 仍阻断完成

- [ ] 在新的 test-fix candidate 上重新运行 `pwsh.exe -NoProfile -File scripts/check.ps1`，必须 exit 0。
- [ ] 重新运行 `git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD`，必须 exit 0。
- [ ] ChatGPT 收到复验输出后按 `verification-before-completion` 复核并写入最终 validated HEAD。

Codex UI transcript 检查仍是 `not_available`。它必须作为已知验证限制保留；当前 direct MCP probe 已证明 `duplicate_full_json_in_mcp_result=false`，但不能把这个结果冒充为 UI transcript 证据。

## 最小复验

见 `LOCAL-RECHECK.md`。由于生产代码自首次真实 AGY 验收后没有变化，本轮**不要重新跑真实 AGY build/test**。只重新验证测试修正和最终 diff。

## Merge Gate

```text
merge_authorized: false
```

未经用户明确授权：不 merge `main`、不删除 feature branch、不启用 auto-merge、不重写历史。
