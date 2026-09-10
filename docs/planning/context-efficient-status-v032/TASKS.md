# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。后续 ChatGPT / 本地 AI / 新对话不要只凭聊天记录判断进度。
> 规格：`SPEC.md`
> 实施计划：`PLAN.md`
> 本地验收：`LOCAL-ACCEPTANCE.md`
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 状态定义

| 状态 | 含义 |
|---|---|
| `planned` | 尚未写对应测试/实现 |
| `implementing` | 正在按 RED/GREEN/REFACTOR 开发 |
| `remote_review` | 生产实现已写，正在做远端规格/代码质量复核 |
| `awaiting_local_acceptance` | 实现与远端静态复核已完成，等待 Windows + 真实 AGY 可执行证据 |
| `accepted` | 本地证据已由 ChatGPT 技术复核，满足 SPEC 完成定义 |
| `blocked` | 有明确阻断问题；必须记录原因与证据 |

## 当前总状态

```text
phase: awaiting_local_acceptance
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
target_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
implementation_authorized: true
production_code_changed: true
package_target: 0.3.2
controller_protocol_target: 2
mcp_tool_count_target: 6
remote_spec_review: complete_no_open_critical_or_important
remote_code_quality_review: complete_no_open_critical_or_important
remote_executable_tests_run: false
github_ci: unavailable_no_workflow_runs
remote_container_checkout: failed_dns_could_not_resolve_github
windows_check_ps1: not_run
git_diff_check: not_run
real_agy_v032_acceptance: not_run
local_acceptance_protocol: docs/planning/context-efficient-status-v032/LOCAL-ACCEPTANCE.md
merge_authorized: false
open_pr: "#2_draft"
```

PR：`https://github.com/elio-zwd/agy-worker/pull/2`

**解释：** 用户已明确要求开始并继续开发，因此生产实现已经授权并完成远端实现 pass。`awaiting_local_acceptance` 不等于“v0.3.2 已完成”：当前没有 Windows `scripts/check.ps1` exit 0、没有真实 `git diff --check`、没有真实 AGY payload/transcript 验收证据，因此任何测试 PASS/可合并结论都必须等待本地 AI 返回证据后再由 ChatGPT 复核。

## 已实现结果摘要

v0.3.2 当前候选代码实现：

1. **Runtime compact public view**
   - same-revision long-poll deadline 返回 `{task_id,status,revision,unchanged:true}`；
   - changed nonterminal 只保留 task/session/turn/status/revision + 小 progress；
   - terminal 不再带 stale progress；
   - terminal result 默认只保留 summary、exit/counts、termination/source-changed、evidence/result artifact ID 等决策字段；
   - diagnostics/artifact manifest/workspace/AGY internals 不再进入 terminal 热路径；
   - summary、runtime error、changed-file preview 均使用 UTF-8 字节预算；preview 最多 5 项且每项最多 128B；
   - 完整 result/errors/operation-log 等本地证据继续保留。
2. **MCP representation 去重**
   - 普通 JSON 工具以 `structuredContent` 为 canonical；
   - TextContent 只保留 <=256B 人类摘要；
   - artifact text/metadata 只返回单份 TextContent；图片继续 ImageContent；
   - WorkerError 保留既有 `error/message` structured body，只去除重复完整 JSON。
3. **内部客户端兼容**
   - `scripts/run-task.py` 优先读 `structured_content`，并兼容旧 server JSON TextContent；
   - 避免 v0.3.2 自己把官方任务验收入口弄坏。
4. **版本与文档**
   - `pyproject.toml` = `0.3.2`；
   - Controller protocol 仍为 v2；
   - six MCP tools 不变；
   - README / `docs/实施设计.md` 已同步 compact/hot-cold contract；
   - `scripts/verify-controller.py` 的版本门禁同步到 0.3.2。

## Review 中发现并已修复的问题

以下问题不是未经验证直接忽略，而是在独立规格/代码质量 review pass 中被发现后补测试与最小修正：

1. **Important — `run-task.py` 会因短 TextContent 解析失败**
   - 原脚本 `json.loads(response.content[0].text)` 与新合同冲突；
   - 已改为 canonical structured first + legacy text fallback；
   - 已增加 `tests/test_run_task.py` 合同测试。
2. **Important — `verify-controller.py` 仍锁定 0.3.1**
   - 已同步 `EXPECTED_VERSION = 0.3.2`；
   - 已增加既有质量测试断言。
3. **Important — changed-files 总数可能被 preview 截断后误报**
   - 完整 result 先持久化 `changed_files_count`；
   - compact renderer 优先读完整计数，preview 仍只显示前 5 个。
4. **Important — 多字节 Runtime error 可能突破 other-terminal 2048B**
   - public error message 使用 UTF-8 1024B 上限；
   - SQLite persisted error 不截断。
5. **Important — terminal 可能残留 running progress，超长 changed path 可突破预算**
   - terminal public view 不再返回 stale progress；
   - changed-file preview 单路径 UTF-8 <=128B；
   - 完整路径仍保留在冷证据。
6. **Minor — 整文件 GitHub 写入带入一个无语义空格 diff**
   - 已单独清理；最终候选代码不保留该无关 Browser 格式变化。
7. **计划示例与既有错误合同不一致**
   - PLAN 曾用 `structuredContent["code"]` 举例；仓库既有 server 公开错误体实际是 `error/message/...`；
   - 本次只做表示去重，不做无关 breaking rename，因此实现与测试保留 `error` 键；最终 SPEC 已明确该决定。

当前 review 结束后没有开放 Critical / Important finding；这表示**代码审查层面没有已知阻断项**，不表示可执行测试已通过。

## T1 — Runtime compact public view

状态：`awaiting_local_acceptance`

- [x] RED 合同测试已写：same revision + `wait_ms=0` minimal unchanged。
- [x] RED 合同测试已写：changed running 不含 timestamps/result，预算 <=512B。
- [x] RED 合同测试已写：20 long warnings + 20 long errors + 多 artifacts 的 terminal compact payload。
- [x] RED 合同测试已写：terminal 优先于 same `after_revision`。
- [x] RED 合同测试已写：changed-files 完整 count 不被 preview 截断破坏。
- [x] RED 合同测试已写：多字节 public runtime error <=2048B 且 persisted error 保留原文。
- [x] RED 合同测试已写：terminal 不带 stale progress；超长 changed path preview 单项 <=128B。
- [x] 实现 `_truncate_utf8`、`_public_result`、`_public_task`。
- [x] `Runtime.public()` 委托 compact renderer。
- [x] `Runtime.status()` same revision deadline 返回 unchanged envelope。
- [x] public renderer 不删除 result/errors/operation-log artifact，也未新增 stdout-based auto-cancel。
- [ ] **本地执行** `python -m pytest -q tests/test_runtime.py` 并记录真实数量。

> TDD 证据边界：远端 Web/GitHub 环境能证明测试 commit 先于对应生产修正、且旧代码按断言逻辑应失败；但没有 Windows runner/CI，因此没有声称实际 RED/GREEN 命令已运行。

## T2 — MCP response representation 去重

状态：`awaiting_local_acceptance`

- [x] 测试已写：status TextContent 不等于完整 structured JSON。
- [x] 测试已写：unchanged / terminal hot text <=256B 且人类可读。
- [x] 测试已写：text artifact 只有一份 payload、`structuredContent is None`。
- [x] 测试已写：WorkerError 不再双份完整 JSON，同时保留既有 `error` structured key。
- [x] 实现 `_compact_tool_text()` / UTF-8 截断。
- [x] 普通 JSON 工具 short TextContent + canonical structuredContent。
- [x] artifact text/metadata 单份 TextContent；image 行为保持 ImageContent。
- [x] `scripts/run-task.py` 同步为 structured-first + legacy fallback。
- [ ] **本地执行** `python -m pytest -q tests/test_server.py tests/test_run_task.py`。
- [ ] **本地执行** `python -m pytest -q tests/test_controller_reconnect.py`，确认 reconnect 第二次 status 仍 `wait_ms=0`。

## T3 — v0.3.2 public contract

状态：`awaiting_local_acceptance`

- [x] server/package metadata test 目标改为 `0.3.2`。
- [x] `pyproject.toml` version = `0.3.2`，依赖未改。
- [x] README 记录 unchanged envelope、terminal compact result、artifact drill-down、无 stdout ≠ hung、structuredContent canonical。
- [x] `docs/实施设计.md` 同步 hot/cold split、byte budgets、protocol v2 理由。
- [x] `scripts/verify-controller.py` 版本目标同步到 0.3.2。
- [x] GitHub compare 确认 `src/agy_worker/models.py` 与 `schemas/*.json` 均无 diff；输入合同未改。
- [x] GitHub 当前 `controller_protocol.py` 仍为 `PROTOCOL_VERSION = 2`。
- [x] 当前 `server.py` `TOOLS` 仍为 6 项。
- [ ] **本地执行** version/server/full regression。

## T4 — 完成门禁与本地 AI 验收

状态：`awaiting_local_acceptance`

### Remote review — 已完成

- [x] 重新读取 `AGENTS.md` 与当前 Superpowers `verification-before-completion` / Web Adapter / code-review 方法。
- [x] 规格复核：hot/cold split、unchanged、terminal decision fields、artifact drill-down、no auto-cancel、protocol/tool/schema 边界逐项核对。
- [x] 代码质量复核：renderer purity、terminal/after_revision 优先级、UTF-8 budgets、WorkerError、artifact ID、TextContent-only compatibility、official run-task compatibility、无 scope creep。
- [x] Review 发现的 5 个 Important 问题已补测试并修复；一个 accidental whitespace diff 已清理。
- [x] `SPEC §9.1` 已明确纳入 review 发现的 `run-task` / verifier 最小兼容范围。
- [x] GitHub compare 从固定 base 到 `TARGET_CODE_HEAD`：仅当前规格范围与 planning/docs 文件；无 Controller/Broker/Browser/permission/database/schema 行为修改。

### Remote executable verification — 无可用 runner

- [x] 检查 GitHub Actions：候选 commit 无 workflow runs。
- [x] 检查 commit status：仓库无实际 status checks 可作为测试证据。
- [x] 尝试远端容器 checkout：失败，环境 DNS `Could not resolve host: github.com`，因此没有可执行仓库副本。
- [ ] `pwsh.exe -NoProfile -File scripts/check.ps1` — **只能本地 Windows 运行，尚未运行**。
- [ ] `git diff --check b51d817...HEAD` — **尚无本地可执行证据**。

### Real Windows + AGY acceptance — 等待本地 AI

详细协议：`LOCAL-ACCEPTANCE.md`，绑定：

```text
TARGET_CODE_HEAD=2b9ef842e4eb52bed7c00e6e57505a0c09a64852
```

- [ ] 工作区 clean / branch HEAD / post-target only-planning-docs 检查。
- [ ] 安装 metadata = `0.3.2`。
- [ ] `scripts/check.ps1` exit 0 + 真实 pytest 数字。
- [ ] `git diff --check` exit 0。
- [ ] `verify-controller.py --fresh --stop-after` 验证 0.3.2、protocol 2、6 tools、双 Bridge 常驻 Controller。
- [ ] 真实 `ai_skill_roundtable / jianyu_lint_assemble`（或 ChatGPT 重新批准的其他已登记 warning-producing build/test）。
- [ ] 记录 submit/status/terminal structured/TextContent 字节。
- [ ] 若自然出现 unchanged 窗口，验证 minimal <=256B；若未出现，记录 `not_observed`，不得伪造。
- [ ] terminal build/test <=1536B，保留 exit/counts/evidence/result ID，无 stale progress/diagnostic arrays/manifest。
- [ ] `errors` / `operation-log` artifact 单载荷可按需读取。
- [ ] 若可访问 Codex transcript，证明同一完整 JSON 不再 text+structured 双份；不可访问则明确 `not_available`。
- [ ] 不因 unchanged 自动 cancel；等待实际终态或用户显式取消。

### Evidence review and merge gate

- [ ] 本地 AI 把 `LOCAL-ACCEPTANCE.md §9` 格式报告回 ChatGPT。
- [ ] ChatGPT 按 `receiving-code-review` 对每条 PASS/FAIL/证据做技术复核，不未经判断照改。
- [ ] 回填 validated HEAD、真实测试数字、payload bytes、open findings。
- [ ] 所有完成定义满足后才可把任务状态改为 `accepted`。
- [ ] PR #2 保持 Draft；用户未授权前不 merge、不删 branch、不 auto-merge。

## Byte Budget Gate

使用：

```python
json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
```

| Payload | Gate |
|---|---:|
| status unchanged structured | `<=256` bytes |
| changed nonterminal structured | `<=512` bytes |
| build/test terminal structured | `<=1536` bytes |
| other terminal structured | `<=2048` bytes |
| hot-path TextContent | `<=256` bytes |
| changed-file preview 单路径 | `<=128` bytes |
| public runtime error message | `<=1024` bytes |

任何超过预算的实现不得靠提高预算绕过；先找是哪一个不必要字段重新进入热路径。完整冷证据不受 public preview 截断替代。

## 明确不做

- progress revision throttle；
- push/webhook；
- 更长 status timeout；
- `verbose=true` / `detail=full`；
- 删除完整 result/errors/operation-log；
- 修改权限、Broker、Controller lifecycle、并发槽或数据库 schema。

如果真实 v0.3.2 数据证明 progress revision 本身仍是主要 token/调用放大器，再单独建下一个 spec/plan，不在本 PR 偷带。

## 后续新对话恢复规则

新对话继续前按顺序读取：

1. 仓库根 `AGENTS.md`；
2. 本目录 `README.md`；
3. `SPEC.md`；
4. `TASKS.md` 获取唯一当前状态；
5. 若执行本地验收，读取 `LOCAL-ACCEPTANCE.md`；
6. 只读取当前 Task 所需的 `PLAN.md` 段落及相关源码/测试；
7. 重新读取适用 Superpowers Skill；
8. 以 GitHub 当前 branch HEAD 为事实，并以 `target_code_head` 判断是否出现新的可执行代码变更。
