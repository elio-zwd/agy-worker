# AGY Worker v0.3.2 Context-Efficient Status Hub

本目录是 `perf/context-efficient-status-v032` 的跨对话持久上下文。目标是让 Codex 默认只接收足够做下一步判断的摘要，完整诊断按需从 artifact 读取。

## 阅读顺序

1. `SPEC.md` — 最终 compact status/result 合同、字节预算、兼容范围和完成定义。
2. `TASKS.md` — **唯一当前进度状态源**。
3. `LOCAL-ACCEPTANCE.md` — 首轮 Windows + 真实 AGY 验收协议。
4. `LOCAL-RECHECK.md` — 5 个测试回归修正后的最小复验协议。
5. `PLAN.md` — 原始 T1～T4 实施计划。

## 当前状态

```text
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
phase: accepted
production code head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
test fix head: 238da44b4f23e3496f6b283f7e87d86f583879a3
validated head: 4e555315cbdc187f905c6222c2a8432b3feef077
package: 0.3.2
controller protocol: 2
MCP tools: 6
Windows scripts/check.ps1: PASS, 91 passed / 0 failed
real AGY acceptance: PASS
open findings: none
Codex UI transcript duplicate check: not_available
merge authorized: false
open PR: #2 (Draft)
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

`accepted` 表示规格、实现、远端 review、Windows 全量检查和真实 AGY 行为证据已经完成技术复核；**不代表已合并到 main**。最终集成仍由用户决定。

## 已实现的数据流

```text
Codex
  │
  │ submit / status / cancel
  ▼
compact public envelope
  - task/status/revision
  - tiny progress only while nonterminal
  - summary + exit/counts + evidence ids when terminal
  - unchanged=true when long-poll timed out without new revision
  │
  ├── enough → Codex continues decision-making
  │
  └── need evidence
       ▼
agy_artifact_read (explicit cold path)
  - errors
  - operation-log selected lines
  - result
  - image/other evidence
```

普通 JSON MCP 工具以 `structuredContent` 为 canonical machine result；TextContent 只保留短摘要，不再复制完整 JSON。`agy_artifact_read` 文本/metadata 只发送一份实际 payload；图片继续走 ImageContent。

## 最终字节证据

首轮真实 `jianyu_lint_assemble`：

```text
submit:      148B structured / 70B TextContent
running:     148–199B / 70–71B
unchanged:   100B / 37B
terminal:    571B / 67B
warnings:    19
errors:      0
exit_code:   0
final_status: succeeded
```

终态没有 stale progress；diagnostics / operation-log / result artifact 均通过单 TextContent drill-down。direct MCP probe 没有出现同一完整 JSON 的 TextContent + structuredContent 双份。Codex UI transcript 本轮不可访问，因此保留 `not_available`，不以 direct probe 冒充 UI 证据。

## 最终验证

首次 Windows/真实 AGY 验收暴露 5 个 pytest 回归。技术复核后确认均是测试契约/fixture 问题，没有要求修改已经通过真实 AGY 验收的生产协议。test-only 修正后，第二轮本地复验在 `4e555315cbdc187f905c6222c2a8432b3feef077` 上得到：

```text
pwsh.exe -NoProfile -File scripts/check.ps1
exit_code: 0
pytest: 91 passed / 0 failed / 0 skipped / 0 warnings

git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD
exit_code: 0

working_tree_before: clean
working_tree_after: clean
open_findings: none
```

`c194919..238da44` 的净变化只有三个测试文件；`238da44..4e55531` 只有本目录 planning 文档，所以无需重复消耗 AGY 额度。

## 集成说明

feature branch 历史中包含修测试及最终记录阶段由 ChatGPT 误用 GitHub contents API 产生、随后被正确内容覆盖的临时 `noop/placeholder` 中间提交。最终净 tree 已恢复正确，main 从未被修改，也没有 force-push。若用户选择合并 PR #2，建议使用 **Squash merge**，让 main 只接收一个干净的最终提交。

未经用户明确授权，不 merge `main`、不删除 feature branch、不启用 auto-merge、不重写历史。
