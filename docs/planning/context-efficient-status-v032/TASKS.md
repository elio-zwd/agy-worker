# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> 规格：`SPEC.md`；实施计划：`PLAN.md`；首次完整验收：`LOCAL-ACCEPTANCE.md`；回归复验：`LOCAL-RECHECK.md`。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: accepted
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
first_acceptance_head: c19491917a6f6da5ca0f3c8242dad46f3891d1cd
test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
windows_check_ps1: passed_91_0
windows_diff_check: passed_exit_0
controller_verification: passed
real_agy_payload_acceptance: passed
codex_transcript_duplicate_check: not_available
open_findings: none
merge_authorized: false
open_pr: "#2_draft"
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

`accepted` 表示 SPEC 的完成定义已由 ChatGPT 结合远端仓库事实、首轮 Windows/真实 AGY 验收和第二轮 Windows 回归复验完成技术复核。**它不等于已合并。** 最终是否将 PR #2 合入 `main` 仍由用户决定。

## 最终验收证据

### 1. 首轮 Windows + 真实 AGY

首轮验收分支 HEAD：`c19491917a6f6da5ca0f3c8242dad46f3891d1cd`。

- package version：`0.3.2`
- Controller：`0.3.2 / protocol 2 / tools 6/6`，验证通过
- `git diff --check`：exit `0`
- 真实 `jianyu_lint_assemble`：task `succeeded`，operation exit `0`，errors `0`，warnings `19`
- submit：`148B structured / 70B TextContent`
- running：`148–199B structured / 70–71B TextContent`
- naturally observed unchanged：`100B structured / 37B TextContent`
- terminal：`571B structured / 67B TextContent`
- terminal stale progress：不存在
- diagnostics artifact：PASS，单 TextContent，6619B
- operation-log artifact：PASS，单 TextContent，7193B
- result artifact：PASS，单 TextContent，3988B
- direct MCP probe：`duplicate_full_json_in_mcp_result=false`
- Codex UI transcript：`not_available`

真实任务自然出现多次 `unchanged=true`，未因安静窗口自动 cancel，最终正常 succeeded；因此“无 revision/stdout 增长不是 hang detector”已获得真实运行证据。

首轮唯一阻断是全量 `scripts/check.ps1`：`86 passed / 5 failed`。

### 2. 五个失败的技术复核与 test-only 修正

ChatGPT 按 `receiving-code-review` + `systematic-debugging` 逐项复核后确认，5 个失败均为测试契约/fixture 问题，不要求回退已被真实 AGY 验证的新生产协议：

1. `tests/test_controller.py` 仍从 artifact `structured_content` 读取正文；v0.3.2 文本 artifact 合同为单 TextContent。
2. `tests/test_runtime.py` 把大量 diagnostics 用单行 JSON 写入，触发既有 `Artifacts.read()` 单行 `64 KiB` 保护；改为多行 fixture。
3. `tests/test_server.py` 的三个 handler test 使用 MCP wire camelCase 名称读取 Python 对象；改为 Python SDK v2 的 `structured_content` / `is_error`。

修正固定在：

```text
test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
```

GitHub compare `c194919...238da44...` 的最终净变化只有：

```text
tests/test_controller.py  +5/-1
tests/test_runtime.py     +1/-1
tests/test_server.py      +6/-6
```

无 `src/`、scripts 生产逻辑、package、schema、Controller/Broker/权限/数据库变化。因此首轮真实 AGY 证据仍对应相同生产实现。

> 过程记录：修测试时 ChatGPT 曾误用 GitHub contents API，feature branch 历史中产生临时 `noop/placeholder` commit。未修改 main、未 force-push、未丢历史；最终通过已校验 Git tree 恢复。完成判断以最终净 tree/compare 为准。若后续合并，建议使用 Squash merge，避免把这些中间历史带入 main。

### 3. 最小回归复验

复验 HEAD：

```text
validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
```

本地 AI 只读复验结果：

```text
working_tree_before: clean
post_test_fix_non_planning_files: none
scripts/check.ps1: exit 0
pytest: 91 passed / 0 failed / 0 skipped / 0 warnings
git diff --check: exit 0
working_tree_after: clean
open_findings: none
overall_recheck: PASS
```

`238da44..4e55531` 只有本目录 planning 文档，因此没有重新消耗真实 AGY 额度。

## SPEC 完成定义核对

- [x] compact unchanged envelope：真实观察，100B structured。
- [x] changed nonterminal hot payload：真实观察，最大 199B structured。
- [x] build/test terminal hot payload：真实观察，571B structured，远低于 1536B gate。
- [x] hot TextContent：真实观察，最大 71B，远低于 256B gate。
- [x] terminal 不含 stale progress。
- [x] warnings/errors/artifact manifest 不默认展开到 terminal hot path。
- [x] diagnostics/result/operation-log 仍能从 artifact 冷路径按需读取。
- [x] 普通 MCP structuredContent 为 canonical；未出现完整 JSON text+structured 双份。
- [x] unchanged 不作为 hang/cancel 判定。
- [x] Controller protocol 保持 2，MCP tools 保持 6，package 为 0.3.2。
- [x] 权威 Windows `scripts/check.ps1`：91 passed / 0 failed。
- [x] `git diff --check`：exit 0。
- [x] 最终工作区 clean。
- [x] 当前 open findings：none。

唯一明确的验证限制：`codex_transcript_duplicate_check=not_available`。direct MCP probe 已证明实际 MCP result 不再携带双份完整 JSON，但没有把该结果冒充 Codex UI transcript 证据。

## Merge Gate

```text
merge_authorized: false
```

任务状态已经是 `accepted`；PR #2 可以进入用户的集成决策阶段。未经用户明确授权，不 merge `main`、不删除 feature branch、不启用 auto-merge、不重写历史。
