# Controller v0.3.1 Hardening Task Tracker

> 本文件是跨对话持续状态源。后续 ChatGPT / 本地 AI 不应仅凭聊天记忆判断进度。  
> 规格：`SPEC.md`  
> 施工计划：`PLAN.md`  
> 本地验收：`LOCAL-ACCEPTANCE.md`  
> 分支：`fix/controller-hardening-v031`  
> Base：`904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066`

## 状态定义

| 状态 | 含义 |
|---|---|
| `planned` | 已进入计划，尚未写对应失败测试 |
| `red_written` | 失败测试已提交，但尚缺本地执行 RED 证据 |
| `red_verified` | 本地 AI 已真实执行并确认按预期失败 |
| `implementing` | ChatGPT 正在写最小生产实现 |
| `green_written` | 实现与测试已在分支，等待本地执行 |
| `green_verified` | 本地 AI 已真实执行目标测试并通过 |
| `reviewed` | 已完成独立规格复核和代码质量复核 |
| `awaiting_acceptance` | 单任务完成，等待最终集成验收 |
| `accepted` | 最终本地验收证据已通过 |
| `blocked` | 有明确阻断问题，必须记录原因和证据 |

## 当前总状态

```text
phase: planning
production_code_changed: false
user_plan_approval: pending
local_test_evidence_for_this_branch: none
open_pr: none
merge_authorized: false
```

## 任务总览

| ID | Priority | 任务 | ChatGPT | 本地 AI | 当前状态 |
|---|---|---|---|---|---|
| T1 | P0 | Controller v2 身份 / stale config & implementation | 实现、审查 | RED/GREEN | `planned` |
| T2 | P0 | 跨协议显式 stop + `--config` stop | 实现、审查 | RED/GREEN + Windows stop | `planned` |
| T3 | P0 | 启动锁 takeover / launch retry | 实现、审查 | RED/GREEN + WMI lifecycle | `planned` |
| T4 | P0 | custom `run-task --config` ownership / cleanup | 实现、审查 | RED/GREEN + no-leak | `planned` |
| T5 | P1 | status reconnect / MCP timeout budget | 实现、审查 | RED/GREEN | `planned` |
| T6 | P1 | inflight backpressure / queued cancel | 实现、审查 | RED/GREEN | `planned` |
| T7 | P1 | Controller data_dir ACL advisory | 实现、审查 | RED/GREEN + doctor evidence | `planned` |
| T8 | P2 | package/version/request_id/cleaning docs sync | 实现、审查 | targeted test | `planned` |
| T9 | Gate | fresh lifecycle + full verification + Draft PR | 远端 diff/review | Windows full acceptance | `planned` |

## T1 — Controller v2 身份 / stale 检测

**Status:** `planned`

**必须交付：**

- `controller_state.py`；
- protocol v2；
- `config_sha256`；
- `implementation_version` 单一来源；
- `implementation_sha256`；
- `instance_id`；
- 严格 `http://127.0.0.1:<port>` endpoint；
- state / health / 当前磁盘一致性检查；
- `controller_stale_config`；
- `controller_stale_implementation`。

**RED evidence:**

```text
not run
```

**GREEN evidence:**

```text
not run
```

**Commit:**

```text
not created
```

**Review findings:**

```text
none yet
```

## T2 — 跨协议显式 stop / custom config stop

**Status:** `planned`

**必须交付：**

- legacy state 可读；
- 普通业务 call 仍严格 protocol；
- management stop 可停旧 protocol；
- `python -m agy_worker.manage stop --config PATH`；
- `scripts/stop.ps1 -Config PATH`；
- stop 等待目标实例真实消失；
- replacement instance 防误停。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T3 — 启动锁 takeover / launch retry

**Status:** `planned`

**必须交付：**

- waiter 在 launch owner 退出后可重新抢锁；
-旧 Runtime stopping / `runtime_busy` 窗口后可 retry；
- launch cooldown ≥ 0.5s；
- WMI Create PID 可诊断；
- readiness 仍只信 authenticated health；
- 现有 simultaneous-two-client 单 Controller 行为保持。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T4 — custom run-task Controller ownership

**Status:** `planned`

**必须交付：**

- 未显式 `--config`：正式 Controller 保持 persistent；
- 显式 `--config`：只清理由本次脚本真正启动的 instance；
- pre-existing Controller 不被脚本停止；
- `--keep-controller`；
- error / exception / Ctrl+C cleanup；
- replacement instance 防误停。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T5 — reconnect / timeout budget

**Status:** `planned`

**必须交付：**

- 第一次 `status(wait_ms=25000)` 连接失败后，重连第二次 `wait_ms=0`；
- task_id / after_revision 保留；
- submit/continue request_id 不变；
- Codex MCP `tool_timeout_sec=60`；
- 不扩大 public status wait schema。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T6 — inflight backpressure / queued cancel

**Status:** `planned`

**必须交付：**

- `max_concurrent_tasks=1`；
- `max_inflight_tasks=16`；
- 第 17 个**新**请求 `worker_busy`；
- 幂等重试在容量已满时仍返回原 task；
- rejected request 不创建 task/session/artifact 副作用；
- executor Future 保存；
- queued cancel 立即 `cancelled`，不等执行槽；
- running cancel 行为不回归。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T7 — data_dir ACL advisory

**Status:** `planned`

**必须交付：**

- pure principal/access 分类 helper；
- Windows DACL inspection；
- `checked`；
- `broad_read_principals`；
- `token_confidentiality_advisory`；
- OS API 失败时 fail-unknown，不宣称安全；
- doctor/capabilities advisory；
- 不自动修改 ACL；
- 不改变 `os_isolation=false`。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Doctor evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T8 — package / docs / contracts

**Status:** `planned`

**必须交付：**

- package `0.3.1`；
- `jsonschema==4.26.0` 正式 dependency；
- MCP server version 取 package metadata；
- request_id 全 data_dir 历史唯一语义；
- 新请求推荐 UUID；
- “维护者辅助清洗模式”改为“维护者辅助清洗流程”；
- 不新增虚假的 runtime analysis mode；
- README / 实施设计 / 部署验收与代码同步；
- 部署验收只写真实证据。

**RED evidence:** `not run`  
**GREEN evidence:** `not run`  
**Commit:** `not created`  
**Review findings:** `none yet`

## T9 — Final verification / handoff

**Status:** `planned`

**必须交付：**

- `verify-controller.py --fresh --stop-after`；
- isolated acceptance config；
- `scripts/check.ps1` 真实结果；
- fresh two-Bridge WMI lifecycle；
- Bridge 全退后同 PID/instance 仍活；
- explicit stop 后 state / health 消失；
- custom run-task no-leak；
- `git diff --check`；
- GitHub `main...branch` compare；
- 独立 spec review；
- 独立 code-quality review；
- local AI findings 技术复核；
- Draft PR；
- 未验证项明确列出。

**Full test evidence:** `not run`  
**Lifecycle evidence:** `not run`  
**Git diff evidence:** `not checked`  
**Draft PR:** `not created`

## 本地 AI 反馈登记表

收到本地验收反馈后追加，不覆盖历史记录：

| Date | Task | Evidence | Finding | ChatGPT 技术判断 | Action |
|---|---|---|---|---|---|
| — | — | — | — | — | — |

## 决策日志

### 2026-09-09 / D1 — 保留 Controller + Bridge 架构

决定：不回退到每 stdio 一个 Runtime，也不删除 `runtime.lock`。

原因：任务 SQLite、active、cancel、token、session、artifact 与单执行槽需要唯一权威控制面。

### 2026-09-09 / D2 — stale Controller 不自动重启

决定：config / implementation 不一致时 fail-closed + 明确 stop 指引。

原因：后台 build/browser 可能有副作用，自动强停和自动 replay 风险高于一次显式维护操作。

### 2026-09-09 / D3 — protocol v2

决定：v0.3.1 将 Controller state/health 协议提升到 2。

原因：新增 config hash、implementation hash、instance_id 是跨进程身份契约变化；用同一 protocol number 容易让旧 Bridge/Controller 误判兼容。

### 2026-09-09 / D4 — custom `--config` 默认 ephemeral ownership

决定：只有显式 custom config 且由本次 run-task 真正启动的 Controller 默认随脚本清理；正式默认 config 继续 persistent。

原因：保留生产使用体验，同时消除维护清洗遗留隐藏 Controller。

### 2026-09-09 / D5 — 单槽不扩并行，只做背压

决定：`max_concurrent_tasks=1`，`max_inflight_tasks=16`。

原因：当前浏览器、构建、未来设备资源没有并发资源锁设计；本问题只需要防止多客户端无限排队。

### 2026-09-09 / D6 — ACL 只做 advisory

决定：本次检查 ACL 风险但不自动改 ACL，不据此宣称系统隔离。

原因：Windows effective access 复杂；项目当前真实边界仍是 hook + Broker + 本机用户权限。

## 下一动作

```text
等待用户审核 SPEC.md / PLAN.md
→ 用户确认
→ T1 写失败测试
→ 提交 red test
→ 本地 AI 执行 RED
→ ChatGPT 开始生产实现
```
