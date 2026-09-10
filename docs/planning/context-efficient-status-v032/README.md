# AGY Worker v0.3.2 Context-Efficient Status Planning Hub

本目录是 `perf/context-efficient-status-v032` 的跨对话持久上下文。目标不是让 AGY 少做工作，而是让 **Codex 默认只接收足够做下一步判断的摘要，完整诊断按需从 artifact 读取**。

## 阅读顺序

1. `SPEC.md` — 真实问题、根因、已锁定的 compact status/result 合同、字节预算和完成定义；冲突时高于施工计划。
2. `TASKS.md` — **唯一当前进度状态源**；后续所有实现、审查、测试、本地 AGY 验收和 PR 状态都回填这里。
3. `PLAN.md` — T1～T4 的 RED/GREEN/REFACTOR 实施步骤、准确文件边界、命令和交接要求。

后续新对话不要把整份历史聊天重新灌进上下文。先读本 README + TASKS，再按当前任务最小读取 SPEC/PLAN 段落和相关源码。

## 当前状态

```text
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
phase: draft_pr_open_waiting_implementation_authorization
production code changed: false
package target: 0.3.2
controller protocol target: 2
implementation authorized: false
real v0.3.2 tests: not run
real AGY acceptance: not run
merge authorized: false
open PR: #2 (Draft)
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

用户本轮已明确授权：分析实践数据，并在 GitHub 建立 PR、PLAN、TASK，避免上下文丢失。本轮授权覆盖这些规划 artifact 和 Draft PR；不自动等价于授权开始生产实现。

## 结论摘要

当前 token 浪费来自三层叠加，而不是单一日志过长：

1. **MCP 表示层重复**：`server.py` 把同一个 result 同时完整序列化到 TextContent 和 `structuredContent`。
2. **状态 long-poll 无 delta 语义**：`Runtime.status()` 在 `after_revision` 没变化但等待到期时仍返回完整 public record，所以同一个 revision 会重复进入上下文。
3. **终态热/冷数据混合**：status 直接展开 warnings/errors 和 artifact manifest；这些信息其实已经有 `errors`、`operation-log`、`result` 等显式证据入口。

实践记录还说明：`captured_bytes` 一段时间不增长只代表没有新 stdout chunk，不代表 Gradle/AGY 卡死。v0.3.2 明确不引入基于日志静默的自动取消。

## 目标数据流

```text
Codex
  │
  │ submit / status / cancel
  ▼
compact public envelope
  - task/status/revision
  - tiny progress when changed
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

## 关键预算

```text
unchanged status <= 256 bytes
changed running status <= 512 bytes
build/test terminal status <= 1536 bytes
other terminal status <= 2048 bytes
hot-path TextContent <= 256 bytes
```

普通 JSON 工具继续用 `structuredContent` 作为 canonical machine result；TextContent 只给短摘要，禁止再复制完整 JSON。`agy_artifact_read` 是显式冷路径，文本/metadata 只发送一份实际 payload；图片仍走 ImageContent。

## 为什么不直接把 warning 全删掉

失败定位仍必须保留：

- `exit_code`；
- `total_errors` / `total_warnings`；
- `termination_reason`；
- `source_changed`；
- `operation-log` evidence ID；
- `diagnostics_artifact_id=errors`；
- `result_artifact_id=result`。

差别是正文不再默认灌进 status。Codex 判断有必要时，才读取具体 artifact 的必要行。这样保持 Evidence over claims，同时避免 Evidence everywhere。

## 为什么 v0.3.2 不做 progress 节流

真实数据已经足够证明双份 JSON、unchanged full-record 和 terminal full-ish result 是直接放大器；progress revision 是否仍然是 v0.3.2 后的主要成本还没有证据。按 YAGNI，本 PR 先不改 revision 发布频率，避免把 token 优化扩大成时序/调度重构。

如果真实验收后 status 调用频率仍明显过高，再单独建立 progress-coalescing spec，不把未经验证的问题偷带进当前 PR。

## 开发门禁

用户后续明确说“开始开发/实施”后：

```text
读取当前 GitHub HEAD + AGENTS.md + 本目录
→ T1 Runtime compact view (TDD)
→ T2 MCP representation 去重 (TDD)
→ T3 0.3.2 docs/version
→ spec review
→ code-quality review
→ scripts/check.ps1 + diff-check
→ 本地 AI 真实 Windows/AGY 字节与 transcript 验收
→ receiving-code-review 复核
→ 回填 TASKS
→ 等用户决定是否 merge
```

## 已验证与未验证

已验证的是**问题根因与当前代码路径的对应关系**：实践记录中的重复输出与当前 `server.py`/`runtime.py` 行为一致。

尚未验证的是 v0.3.2 未来实现本身：当前分支此时只有规划文档，没有生产代码、测试或版本修改，因此不能说 token 优化已经生效，也不能说任何 v0.3.2 测试通过。

未经用户明确授权，不 merge `main`、不删除分支、不启用自动合并。
