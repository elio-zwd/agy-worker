# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。后续 ChatGPT / 本地 AI / 新对话不要只凭聊天记录判断进度。
> 规格：`SPEC.md`
> 实施计划：`PLAN.md`
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 状态定义

| 状态 | 含义 |
|---|---|
| `planned` | 已完成规格/计划，尚未写对应 RED 测试 |
| `implementing` | 正在按 PLAN 做 RED/GREEN/REFACTOR |
| `remote_review` | 生产实现已写，正在做规格/代码质量复核 |
| `awaiting_local_acceptance` | 远端实现和可用检查完成，等待 Windows + 真实 AGY 证据 |
| `accepted` | 本地证据已由 ChatGPT 技术复核，满足 SPEC 完成定义 |
| `blocked` | 有明确阻断问题；必须记录原因与证据 |

## 当前总状态

```text
phase: planning_pr_preparation
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
planning_spec_commit: 98f6171359088b8bb90e424ef93a2b33361cf4a5
planning_plan_commit: bae7ff5fb1e231e62701eebfb291a41a1bb10c3a
production_code_changed: false
package_target: 0.3.2
controller_protocol_target: 2
user_request: analyze_and_create_pr_plan_tasks_2026-09-10
implementation_authorized: false
real_implementation_tests_run: false
real_agy_v032_acceptance: not_run
merge_authorized: false
open_pr: pending_creation
```

`implementation_authorized=false` 的含义是：用户本轮明确要求分析并创建 PR/PLAN/TASKS，因此规划文档可以提交；但本轮没有要求立即修改生产代码。后续只有在用户明确说开始开发/实施后，才按 `PLAN.md` 进入 T1。

## 真实问题证据摘要

2026-09-10 实践记录已经证明三个独立放大器：

1. **MCP 双份表示**：普通 JSON 工具同时返回完整 JSON TextContent 和同值 `structuredContent`，宿主记录中同一结果出现两份。
2. **unchanged long-poll 重复**：`after_revision=5, wait_ms=25000` 多次得到相同 revision 5 的完整 running record。
3. **terminal 热/冷混合**：build/test 终态 status 直接携带 10～20 条长 warning/error 和整份 artifact metadata，尽管 `errors` / `operation-log` / `result` 已经提供显式证据入口。

另外，实践中“captured_bytes 一段时间不增长”曾被当成疑似卡死而主动取消；随后读取 operation log 才确认 Gradle 已进入 `generateDebugLintReportModel`。因此本规格明确禁止把 stdout 静默直接解释成 hung。

## 任务总览

| ID | Priority | 任务 | 当前状态 | 关键验收 |
|---|---|---|---|---|
| T1 | P0 | Runtime compact public view + unchanged long-poll | `planned` | unchanged ≤256B；running ≤512B；build/test terminal ≤1536B；artifact 仍可读 |
| T2 | P0 | MCP response representation 去重 | `planned` | 普通工具不再 text+structured 双份 JSON；hot text ≤256B；artifact 只发一份 |
| T3 | P1 | version / README / 实施设计 / schema contract | `planned` | package=0.3.2；protocol=2；6 tools；输入 schema 无意外变化 |
| T4 | Gate | spec/code review + full check + real AGY payload acceptance | `planned` | `scripts/check.ps1`、diff-check、真实 warnings build/test、字节与 Codex transcript 证据 |

## T1 — Runtime compact public view

状态：`planned`

必须完成：

- [ ] RED：same revision + `wait_ms=0` 返回 minimal `unchanged=true`。
- [ ] RED：changed running public envelope 不含 timestamps/result。
- [ ] RED：20 long warnings + 20 long errors + 多 artifacts 的 terminal public payload 仍在 1536 bytes 内。
- [ ] RED：terminal 优先于 same `after_revision`，不能被 unchanged 掩盖。
- [ ] GREEN：实现 `_truncate_utf8`、`_public_result`、`_public_task`。
- [ ] GREEN：`Runtime.public()` 委托 compact renderer。
- [ ] GREEN：`Runtime.status()` deadline 无变化分支返回 unchanged envelope。
- [ ] 回归：`python -m pytest -q tests/test_runtime.py`。
- [ ] 规格审查：不 mutate persisted result、不删除 artifact、不加入 stdout-based auto-cancel。
- [ ] Commit：`perf: 压缩任务状态与终态结果`。

证据：尚未执行。不得写 PASS。

## T2 — MCP response representation 去重

状态：`planned`

必须完成：

- [ ] RED：`TextContent.text != json.dumps(structuredContent)`。
- [ ] RED：unchanged/terminal hot text ≤256 bytes 且人类可读。
- [ ] RED：text artifact read 只有一份 payload，`structuredContent is None`。
- [ ] RED：WorkerError 不再双份完整 JSON。
- [ ] GREEN：实现 `_compact_tool_text()`。
- [ ] GREEN：普通 JSON 工具 short TextContent + canonical structuredContent。
- [ ] GREEN：artifact text/metadata 只保留单份 TextContent；image 保持现有 ImageContent。
- [ ] 回归：`python -m pytest -q tests/test_server.py`。
- [ ] 回归：`python -m pytest -q tests/test_controller_reconnect.py`，保持第二次 status `wait_ms=0`。
- [ ] Commit：`perf: 去除 MCP 结果重复载荷`。

证据：尚未执行。不得写 PASS。

## T3 — v0.3.2 public contract

状态：`planned`

必须完成：

- [ ] RED：server/package metadata test 期望 `0.3.2`。
- [ ] GREEN：`pyproject.toml` version = `0.3.2`，依赖不变。
- [ ] README：记录 unchanged envelope、terminal compact result、artifact drill-down、无 stdout ≠ hung。
- [ ] `docs/实施设计.md`：同步 hot/cold split、byte budgets、protocol v2 理由。
- [ ] 核对 `models.py` 未改变 StatusRequest。
- [ ] 核对 `schemas/*.json` 无意外输入合同变化；如果没有现成 schema 生成入口，不自造脚本。
- [ ] 回归：`python -m pytest -q tests/test_server.py`。
- [ ] Commit：`docs: 发布 v0.3.2 紧凑结果合同`。

证据：尚未执行。不得写 PASS。

## T4 — 完成门禁与本地 AI 验收

状态：`planned`

### Remote review

- [ ] 规格复核：逐条覆盖 SPEC §§3–9。
- [ ] 代码质量复核：renderer purity、terminal/after_revision 优先级、UTF-8、WorkerError、artifact ID、TextContent-only client、image behavior、无 scope creep。
- [ ] 最终 diff 检查：生产修改只能落在 SPEC §9 文件边界或有明确解释。

### Fresh executable verification

- [ ] `pwsh.exe -NoProfile -File scripts/check.ps1`。
- [ ] `git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD`。
- [ ] 记录精确 tested HEAD 和真实 passed/failed/skipped/warnings。

### Real Windows + AGY acceptance

- [ ] 确认安装 package metadata = `0.3.2`。
- [ ] stop 旧 stale Controller，再由新 Bridge 启动 v0.3.2 Controller。
- [ ] 真实执行一个至少产生 1 条 warning 的已登记 build/test。
- [ ] 记录 submit payload bytes。
- [ ] 记录每次 status 的 `(after_revision, wait_ms, revision, status, bytes)`。
- [ ] 捕获至少一个真实 unchanged 窗口；若目标任务持续输出无法自然出现，记录 `not_observed`，不能伪造。
- [ ] 记录 terminal compact JSON 与 bytes。
- [ ] 证明 terminal 仍保留 exit code / error+warning counts / evidence ID。
- [ ] 通过 `agy_artifact_read` 证明 diagnostics 正文仍可按需读取。
- [ ] 检查 Codex transcript 不再出现同一完整 JSON 两份。
- [ ] 不因 unchanged 自动 cancel；等待实际终态或用户明确取消。

### Evidence review and handoff

- [ ] ChatGPT 按 `receiving-code-review` 逐条复核本地 AI 证据。
- [ ] 回填 validated HEAD、测试数字、payload bytes、open findings。
- [ ] 如有 `LOCAL-ACCEPTANCE.md`，只记录针对精确 HEAD 的实际证据。
- [ ] PR 保持 Draft 直到实现和验收满足完成定义。
- [ ] 用户未授权前不 merge、不删 branch、不 auto-merge。

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

任何超过预算的实现不得靠提高预算绕过；先找是哪一个不必要字段重新进入热路径。

## 明确不做

- progress revision throttle；
- push/webhook；
- 更长 status timeout；
- `verbose=true` / `detail=full`；
- 删除完整 result/errors/operation-log；
- 修改权限、Broker、Controller lifecycle、并发槽或数据库 schema。

如果后续真实 v0.3.2 数据证明 progress revision 本身仍是主要 token/调用放大器，再单独建下一个 spec/plan，不在本 PR 偷带。

## 后续新对话恢复规则

新对话开始开发前按顺序读取：

1. 仓库根 `AGENTS.md`；
2. 本目录 `README.md`；
3. `SPEC.md`；
4. `TASKS.md` 获取唯一当前状态；
5. 只读取当前要执行 Task 对应的 `PLAN.md` 段落及相关源码/测试；
6. 重新读取适用 Superpowers Skill；
7. 以 GitHub 当前 branch HEAD 为事实，不使用聊天中的旧 SHA。
