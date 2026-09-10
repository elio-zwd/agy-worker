# AGY Worker v0.3.2 Context-Efficient Status Hub

本目录是 `perf/context-efficient-status-v032` 的跨对话持久上下文。目标不是让 AGY 少做工作，而是让 **Codex 默认只接收足够做下一步判断的摘要，完整诊断按需从 artifact 读取**。

## 阅读顺序

1. `SPEC.md` — 最终 compact status/result 合同、字节预算、兼容范围和完成定义；冲突时高于施工计划。
2. `TASKS.md` — **唯一当前进度状态源**；实现、审查、测试、本地 AGY 验收和 PR 状态都回填这里。
3. `LOCAL-ACCEPTANCE.md` — 当前候选代码的 Windows + 真实 AGY 一次性验收协议。
4. `PLAN.md` — 原始 T1～T4 RED/GREEN/REFACTOR 实施步骤；实施中发现的必要兼容调整以最终 `SPEC.md` + `TASKS.md` 为准。

后续新对话不要把整份历史聊天重新灌进上下文。先读本 README + TASKS，再按当前任务最小读取 SPEC/PLAN、验收证据和相关源码。

## 当前状态

```text
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
phase: awaiting_local_acceptance
target code head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
production code changed: true
package target: 0.3.2
controller protocol target: 2
implementation authorized: true
remote spec/code review: complete; no open Critical/Important finding
GitHub CI: unavailable / no workflow runs
Windows scripts/check.ps1: not run
real AGY acceptance: not run
merge authorized: false
open PR: #2 (Draft)
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

`target code head` 是最后一个生产代码 commit。之后允许提交本目录的 handoff/planning 文档；本地 AI 开始验收时必须先确认 target 之后没有新的非 planning 代码变化。

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

普通 JSON MCP 工具以 `structuredContent` 为 canonical machine result；TextContent 只保留短摘要，不再复制完整 JSON。`agy_artifact_read` 是显式冷路径，文本/metadata 只发送一份实际 payload；图片仍走 ImageContent。

## 当前硬预算

```text
unchanged status <= 256 bytes
changed nonterminal status <= 512 bytes
build/test terminal status <= 1536 bytes
other terminal status <= 2048 bytes
hot-path TextContent <= 256 bytes
changed-file preview item <= 128 bytes
public runtime error message <= 1024 bytes
```

终态不再返回 stale `progress`。如果 `source_changed=true`，只公开最多 5 个 UTF-8 有界路径 preview 和完整 `changed_files_count`；完整路径仍保存在冷证据，不因 public budget 被删除。

## 实施中 review 已修复的关键兼容问题

除了核心 Runtime/server 压缩，独立代码质量 review 还发现并修复：

- `scripts/run-task.py` 原先把 TextContent 当完整 JSON，新合同下会崩溃；现已改为 structured-first + legacy JSON text fallback；
- `scripts/verify-controller.py` 原先仍锁定 package 0.3.1；已同步 0.3.2；
- changed-files preview 截断可能导致总数误报；现持久化完整 count；
- 多字节 Runtime error、超长 changed path 可能突破 terminal 字节门槛；现仅在 public view 做 UTF-8 有界截断；
- terminal record 可能残留 running progress；现只在非终态公开 progress。

这些调整已经写入 `SPEC §9.1` 的必要配套范围，没有扩大 Controller lifecycle、协议、权限、Broker、Browser、数据库或执行槽语义。

## 已验证与未验证

### 已有远端证据

- GitHub 当前分支与固定 base 的 compare/diff 已复核；
- package 源码目标为 `0.3.2`；
- `controller_protocol.py` 保持 `PROTOCOL_VERSION=2`；
- `server.py` 公开 MCP 工具仍为 6 个；
- `models.py` / `schemas/*.json` 不在实现 diff 中；
- review 发现的 Critical/Important 代码问题已修复，当前无开放 Critical/Important finding；
- 候选 commit 没有 GitHub Actions workflow run，仓库也没有可用 status check 作为测试证据；
- 远端容器尝试 checkout GitHub 时 DNS 失败，因此没有可执行 Windows 仓库副本。

### 明确尚未验证

- `pwsh.exe -NoProfile -File scripts/check.ps1` 的实际 exit code 与 pytest 数字；
- `git diff --check` 的本地新鲜结果；
- 安装后的 metadata / Controller 0.3.2 真实运行；
- 真实 AGY warnings build/test 的 submit/status/terminal 字节数；
- 真实 artifact drill-down；
- Codex 宿主 transcript 是否确实不再出现同一完整 JSON 双份。

因此当前状态是 **`awaiting_local_acceptance`，不是 `accepted` / 完成 / 可合并**。

## 下一步

把 `LOCAL-ACCEPTANCE.md` 交给用户本地 AI，基于精确 `TARGET_CODE_HEAD` 执行一次性验收并返回完整报告：

```text
本地 AI 运行 Windows/AGY 验收
→ 返回命令、exit code、pytest 数字、payload bytes、原始证据
→ ChatGPT 按 receiving-code-review 逐条技术复核
→ 如有真实问题，回到当前 branch 修复并重新绑定新的 target code head
→ 如全部完成定义满足，TASKS 改为 accepted
→ 仍由用户决定是否 merge PR #2
```

未经用户明确授权，不 merge `main`、不删除分支、不启用自动合并。
