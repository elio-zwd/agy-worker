# AGY Worker v0.3.2 低上下文状态与结果规格

> 本规格记录 2026-09-10 真实使用数据暴露出的 Codex 上下文放大问题，并定义实现必须遵守的公开返回合同。
> 本文件最初在规划阶段创建；用户随后已明确授权实施。当前实现仍必须继续遵守 `AGENTS.md`、TDD、最终 Windows/真实 AGY 验收，以及“未经用户授权不合并 main”的边界。

## 1. 背景与问题

AGY Worker 的初衷是让 AGY 处理编译、日志、浏览器、图片等高噪声工作，Codex 只接收足以做判断的摘要与证据引用。v0.3.1 已经把原始 stdout/stderr、AGY stream 和完整 artifact 留在任务目录，但公开 MCP 热路径仍把过多诊断数据直接送进 Codex 上下文。

2026-09-10 的真实 `jianyu_lint_assemble` 使用记录显示：

1. `agy_status(task_id, after_revision=5, wait_ms=25000)` 在 revision 没变化时连续多次返回同一份完整 running record；
2. 同一次 MCP 调用的返回对象同时出现在 TextContent JSON 和 `structuredContent` 中，宿主记录因此出现两份等价 JSON；
3. 终态 result 直接展开最多 20 条 warnings/errors 和整份 artifact metadata；Android/Kotlin warning 单条就可能很长；
4. `after_revision` 当前只控制“等多久”，没有表达“本轮等待结束但没有新 revision”的紧凑语义；
5. 长时间没有 stdout 变化并不代表构建卡死。真实记录中任务已经进入 `generateDebugLintReportModel`，却因为一段时间没有新增日志被误判为疑似卡住并主动取消。

后续真实 Codex 复验又暴露出第二层问题：即使单次 MCP status 已能合并 progress revision，公开策略仍固定要求 25 秒，因此长编译会迫使 Codex 周期性重新发起 status 调用。用户最终确认把公开等待改为默认 50 秒，并允许 Codex 根据预计任务耗时自主选择 50～600 秒；MCP 内部继续使用最多 25 秒的 Controller long-poll 分片。

这不是单纯的“summary_max_bytes 太大”。根因是 **热路径状态、冷路径证据和 MCP 表示层没有彻底分层，同时上层等待预算与内部 Controller 单段等待没有分层**。

## 2. 根因

### 2.1 MCP 表示层重复

v0.3.1 的 `src/agy_worker/server.py` 对普通 JSON 工具返回：

```python
types.CallToolResult(
    content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
    structuredContent=result,
)
```

同一个对象被完整编码两次。即使 Runtime 已经控制了 result 大小，Codex 仍可能为同一信息付出接近两倍上下文成本。

### 2.2 long-poll 无变化仍返回完整 record

v0.3.1 的 `Runtime.status()` 在 `wait_ms` deadline 到达时无条件 `return self.public(record)`。因此 `after_revision` 没有产生 delta/unchanged 返回；调用者每 25 秒可能再次收到 session、turn、时间戳、progress 等完全相同的数据。

### 2.3 终态把“判断信息”和“取证信息”混在一起

v0.3.1 的 `Runtime._run()` result 同时包含：

- Codex 立即需要的 `status`、summary、退出码、错误/警告计数；
- 仅在排错时才需要的完整 warning/error 条目；
- workspace path、snapshot、AGY PID、enforcement；
- 所有 artifact 的 size/hash/media-type/created-at/sensitive metadata。

但同一任务已经存在 `result`、`errors`、`operation-log` 等 artifact，可通过 `agy_artifact_read` 显式读取。把这些冷数据默认展开到 status 是职责重叠。

### 2.4 固定 25 秒公开等待放大 Codex tool round-trip

Runtime 的 progress revision 需要继续保存用于审计，本轮不应靠删除或节流这些事实来省 token。真正应该收缩的是 Codex 可见的 status 调用次数。若 MCP 公开等待也被限制为 25 秒，即使 server 能在一次调用内吞掉中间 revision，持续几十秒或数分钟的 build/test 仍会周期性返回 Codex，再由模型重新发起下一次 status。

因此公开等待预算必须与 Controller 内部单段等待分离：Codex 决定“一次愿意等多久”，MCP Server 负责在该总预算内多次调用现有短 long-poll。

## 3. 目标

v0.3.2 的目标是：**让 Codex 默认只接收“下一步决策所需信息”，完整事实与证据继续可靠保存在 artifact 中，需要时再按证据 ID 读取；同时让长任务的一次 status 等待尽量停留在 MCP 内部，不要求 GPT 每 25 秒参与。**

必须达到：

- 同一逻辑 JSON 不再在 MCP `content` 与 `structuredContent` 中完整重复；
- `after_revision` long-poll 超时且无变化时返回极小的 `unchanged` envelope；
- build/test 终态默认不展开 warning/error 正文和 artifact manifest；
- 失败仍必须保留错误数量、命令退出码、termination reason 和可追溯 evidence ID，不能为了省 token 丢失可诊断性；
- `agy_artifact_read` 继续作为显式高信息量/高 token 成本的冷路径读取入口；
- 不把“无 stdout 更新”定义为 hung/stalled；任务终态仍只由 Runtime 的进程、取消、超时和业务验证规则决定；
- `agy_status` 公开默认总等待 50 秒，Codex 可自主选择 50～600 秒；AGY 提前进入 terminal 时立即返回，不能把预算当固定 sleep；
- Controller/Runtime 内部单段 status 继续最多 25 秒，MCP 在一个公开 deadline 内分片，不因 progress revision 重置总预算；
- 不改变单 Runtime、单执行槽、权限、快照、Controller stale/stop、request_id 幂等语义。

## 4. 非目标

本阶段不做：

- 不增加 webhook、push notification、MCP Tasks subscription 或后台主动向 Codex 发消息；本轮的“完成即继续”来自一个仍挂起的 MCP tool call 在 terminal 时返回；
- 不把 `agy_worker` 改回同步阻塞直到任务完成；
- 不改变 `MAX_CONCURRENT_TASKS=1` 或 `MAX_INFLIGHT_TASKS=16`；
- 不扩大 shell、code_write、浏览器或 Android 权限；
- 不改变 `summary_max_bytes` 的内部安全预算；
- 不在 v0.3.2 首轮引入 Runtime progress 节流；完整 progress/revision 继续保存，MCP 层负责 coalesce；
- 不因为状态压缩而删除本地 artifact、hash、审计或完整 result 证据；
- 不把 Controller HTTP timeout 或内部 `StatusRequest.wait_ms` 扩大到 600 秒。

## 5. 设计决定

### 5.1 热路径与冷路径分层

公开数据分为两类：

**热路径：** `agy_worker`、`agy_continue`、`agy_status`、`agy_cancel` 的任务 envelope，以及 `agy_capabilities` 的能力结构。目标是让 Codex 快速判断“是否完成、是否失败、下一步是否需要读证据”。

**冷路径：** `agy_artifact_read`。只有 Codex 明确需要日志、错误正文、完整 result 或图片时才读取，允许返回较大内容，但仍受现有行数、字节和敏感证据规则限制。

### 5.2 统一紧凑任务 envelope

Runtime 使用 `_public_task(record, *, unchanged=False)` 生成视图，不改变 SQLite record 本身。

普通 queued/running/cancelling 的公开形状：

```json
{
  "task_id": "task-...",
  "session_id": "session-...",
  "turn": 1,
  "status": "running",
  "revision": 5,
  "progress": {
    "agy_pid": 6120,
    "captured_bytes": 2081
  }
}
```

删除默认热路径中的 `created_at`、`updated_at`。这些不是 Codex 决策必需数据，完整 record 仍在本地状态库和 result 证据中保留。

`progress` 只属于非终态观察信息。任务进入 `succeeded/failed/cancelled/timed_out/interrupted` 后，即使持久 record 中仍保留最后一次 progress，公开终态 envelope 也不得再返回该字段。

### 5.3 无变化 long-poll envelope

当且仅当满足以下全部条件时：

- 调用传入 `after_revision`；
- 当前任务不是 terminal；
- deadline 到达；
- `record.revision <= after_revision`；

返回：

```json
{
  "task_id": "task-...",
  "status": "running",
  "revision": 5,
  "unchanged": true
}
```

不重复 session、turn、progress、时间戳或 result。

如果任务已进入 terminal，即使 terminal revision 等于调用者传入的 `after_revision`，也仍返回终态紧凑结果，避免调用者错过完成信息。

### 5.4 终态默认只返回决策摘要

终态任务 envelope 保留 `task_id`、`session_id`、`turn`、`status`、`revision`，不返回 stale `progress`；`result` 使用紧凑视图。

build/test 的目标形状：

```json
{
  "task_id": "task-...",
  "session_id": "session-...",
  "turn": 1,
  "status": "succeeded",
  "revision": 35,
  "result": {
    "schema_version": 2,
    "summary": "操作成功，日志采集完成。",
    "operation": {
      "command_id": "jianyu_compile_test",
      "exit_code": 0,
      "duration_ms": 199401,
      "termination_reason": null,
      "total_errors": 0,
      "total_warnings": 26,
      "evidence": {"artifact_id": "operation-log"}
    },
    "source_changed": false,
    "termination_reason": null,
    "diagnostics_artifact_id": "errors",
    "result_artifact_id": "result",
    "artifact_count": 7,
    "truncated": true
  }
}
```

默认不返回：

- `errors[]` / `warnings[]` 正文；
- `artifacts[]` metadata manifest；
- `workspace_id` / `workspace_path`；
- `input_snapshot`；
- `agy.pid` / `agy.error` / `agy.result_status`；
- `enforcement`；
- `changed_files` 全量列表；
- terminal record 中残留的 `progress`。

如果 `source_changed=true`，紧凑 result 额外返回 `changed_files_preview`，最多 5 个路径，以及 `changed_files_count`。每个 preview 路径单独按 UTF-8 最多 128 bytes 截断；完整数量和完整路径仍由本地 record / `result` artifact 提供，不能为热路径预算修改持久证据。

对 log/browser/vision/android-ui 等非 build/test 任务，紧凑 result 至少保留：`schema_version=2`、UTF-8 有界 `summary`、`source_changed`、`termination_reason`、`result_artifact_id`、`artifact_count`、`truncated`；已有的类型特定证据仍从 result artifact 或对应 artifact 读取。

### 5.5 热路径字符串硬预算

公开紧凑视图使用以下内部预算：

```python
PUBLIC_SUMMARY_MAX_BYTES = 768
PUBLIC_ERROR_MESSAGE_MAX_BYTES = 1024
PUBLIC_CHANGED_FILES_PREVIEW = 5
PUBLIC_CHANGED_FILE_MAX_BYTES = 128
```

截断统一按 UTF-8 bytes 完成，使用 `errors="ignore"` 避免生成非法字符。只有公开视图受这些上限；本地 `result.json`、SQLite record 和 artifact 的现有完整证据规则保持不变。

### 5.6 MCP 双通道不再复制完整 JSON

对普通 JSON 工具，`structuredContent` 继续作为机器可读的 canonical value；`content` 只返回一个稳定、短小的人类可读摘要，不再 `json.dumps(result)`。

目标例：

```text
agy_status: running rev=5；继续轮询，无需用户消息
agy_status: succeeded rev=35；操作成功，日志采集完成。
agy_worker: queued rev=1；task=task-...
```

热路径 `TextContent.text` UTF-8 长度必须 `<= 256 bytes`。

`agy_artifact_read` 是例外：它是显式冷路径。为了避免同一大段证据再次双份出现，同时保持只消费 TextContent 的客户端可读，文本 artifact 的内容只放在 `content`，`structuredContent` 不再附同一份完整对象；图片路径继续使用 `ImageContent`。artifact metadata-only 读取也走单载荷，不做双份 JSON。

错误返回同样使用短 `TextContent` + structured error body，禁止把完整 error JSON 复制两遍。既有公开错误 body 的字段名仍保持 `error/message/...`，本次不为了去重顺带改成新的 `code` 合同。

### 5.7 artifact 是完整事实来源

v0.3.2 不删除以下 artifact：

- `operation-log`
- `errors`
- `command-stdout` / `command-stderr`（仍敏感、默认不可通过公开 read 直接取）
- `agy-stream` / `agy-stderr`（仍敏感）
- `agy-response`
- `result`
- 浏览器、Android、图片任务已有的其他 evidence

`result_artifact_id="result"` 是默认 drill-down 入口。build/test 若只需错误/警告结构，优先读 `diagnostics_artifact_id="errors"`；若需原始定位上下文，再读 `operation-log` 指定行。

### 5.8 自适应 MCP status 总等待

公开模型与内部模型分离：

```python
class McpStatusRequest(Strict):
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(50000, ge=50000, le=600000)

class StatusRequest(Strict):
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(0, ge=0, le=25000)
```

无 `after_revision` 时，MCP 不存在“等待下一 revision”的基线，因此只调用一次内部 `wait_ms=0` 快照。已有 revision 时，公开预算以单一 monotonic deadline 计算，每次 Controller 调用只取剩余时间与 25000ms 的较小值。任何 progress revision、unchanged 都不得把 deadline 重新设置为新的 50～600 秒；terminal 一出现就立即结束本次 MCP 调用。

Codex 可以省略 `wait_ms` 走 50 秒默认，也可以根据构建预计耗时选择更长值；不要求用固定档位。总预算结束仍非终态时直接下一次 `agy_status`，不得在两次 tool call 之间添加面向用户的等待叙述。

为了让 600 秒合法等待不被 Codex MCP 宿主的旧 60 秒工具超时截断，`manage.register()` 写入 `tool_timeout_sec=660`。这个值只扩大宿主允许工具调用存活的上限，不扩大 `agy_status` 公开最大值，也不修改 Controller HTTP timeout。

## 6. 协议与版本

- 目标包版本：`0.3.2`；
- MCP 工具数量保持 6，不新增工具；
- `agy_status` 对外仍只有 `task_id / after_revision / wait_ms` 三个字段，但模型由内部 `StatusRequest` 分离为公开 `McpStatusRequest`；
- `schemas/agy_status.json` 必须反映公开合同：`wait_ms` default 50000、minimum 50000、maximum 600000；Controller/Runtime 内部 `StatusRequest` 继续 0..25000；
- `manage.schemas()` 必须从 `McpStatusRequest` 生成公开 status schema，避免 regeneration 把内部 25 秒模型泄回外部；
- Codex 注册的 `tool_timeout_sec` 为 660；升级后需要重新执行注册入口才会写入现有本机配置；
- Controller `/control/call` 内部协议继续 `PROTOCOL_VERSION=2`。本次没有改变 IPC request framing、鉴权或方法集合；Runtime 实现摘要与 package version 已能让旧/新实现 fail-closed，不为只改变 MCP 外部等待策略机械升级 protocol v3；
- README 与 `docs/实施设计.md` 必须明确 v0.3.2 的 compact status 与自适应等待语义；
- 不将挂起 tool call 的 terminal 返回描述为 webhook/push notification。

## 7. 可量化验收标准

使用紧凑 JSON 编码 `json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")` 计量：

| 场景 | 上限 |
|---|---:|
| `agy_status` long-poll 无变化 structured payload | 256 bytes |
| queued/running/cancelling changed status（含当前 progress） | 512 bytes |
| build/test terminal compact status | 1536 bytes |
| 其他 terminal compact status | 2048 bytes |
| 热路径 `TextContent.text` | 256 bytes |

同时必须满足：

1. server 单元测试证明普通 JSON 工具不再出现 `TextContent.text == json.dumps(structuredContent, ...)`；
2. Runtime 单元测试证明相同 revision long-poll timeout 返回 `unchanged=true` 且不含 `progress/result/session_id/turn`；
3. Runtime 单元测试构造 20 条超长 warning + 20 条超长 error + 多个 artifacts，终态公开 result 仍在上表预算内，且 `result`/`errors` artifact 仍可读；
4. terminal status 保留 exit code、error/warning counts、termination reason、source-changed flag 和 evidence/result artifact ID，并且不返回 stale `progress`；
5. source-changed 终态在超长多字节路径下仍满足预算；preview 最多 5 个、每个最多 128 UTF-8 bytes，完整路径不从持久证据删除；
6. Runtime 自身异常的公开 `error.message` 按 UTF-8 有界，不能突破其他 terminal 2048B 上限，持久 error 仍保留原文；
7. status reconnect 第二次内部 `wait_ms=0` 的 v0.3.1 合同继续通过；
8. cancellation、request_id 幂等、16 inflight、Controller stale/stop 等既有测试不得因本次返回视图改变而失效；
9. `scripts/run-task.py` 必须优先消费 canonical `structured_content`，同时兼容旧 server 的 JSON TextContent；
10. 公开 `agy_status` list_tools/schema 必须显示 wait_ms default 50000 / min 50000 / max 600000；49999 与 600001 在进入 Controller 前被拒绝；
11. 省略 `wait_ms` 且已有 `after_revision` 时使用 50 秒总预算；内部每段 Controller status <=25000ms；progress revision 不能重置总 deadline；
12. 公开选择 600000ms 时，内部仍 <=25000ms；如果第二个内部观察点已 terminal，则不得继续内部轮询或等待满 600 秒；
13. 无 `after_revision` 时必须只取一次内部 `wait_ms=0` 当前快照；
14. `manage.schemas()` 再生成后的 `agy_status.json` 与 tracked 公开 schema 一致；
15. `manage.register()` 生成的 `mcp_servers.agy_worker.tool_timeout_sec` 必须大于 600 秒，目标值 660；
16. `scripts/check.ps1` 最终必须 exit 0；
17. 本地 AI 必须用真实 AGY 至少执行一次 build/test，记录 Codex 可见 `agy_status` 调用与公开 wait 参数，并验证中间 progress 不再逐 revision 回到 Codex；
18. 真实任务期间若出现无 revision 增长的 long-poll 窗口，只能得到 compact `unchanged`，不能因此自动 cancel；最终状态由实际进程终态决定。若目标构建持续输出导致自然窗口未出现，应记录 `not_observed`，不得伪造；
19. 对一个选用较长等待预算的真实 status，必须确认 terminal 到达后调用提前返回，而不是等待满配置预算；
20. 真实复验前重新执行 `scripts/register.ps1`，核对 `tool_timeout_sec=660` 且用户既有 developer instructions 没有被覆盖。

## 8. 兼容与风险

### 8.1 TextContent-only 客户端

风险：某些客户端只读取 `content` 而忽略 `structuredContent`。

处理：普通热路径仍保留短 TextContent，不返回空 content；artifact 文本读取继续把实际证据放进 TextContent。这样既不重复大 JSON，也不把旧式文本消费者完全断开。

仓库自带的 `scripts/run-task.py` 属于机器消费者，不能继续把短 TextContent 当完整 JSON。v0.3.2 将其迁移为优先读取 `structured_content`，并保留旧 JSON TextContent fallback，避免官方验收入口被新返回合同反向破坏。

### 8.2 依赖旧终态字段的调用方

风险：调用方若直接依赖 status 中的 `warnings[]`、`artifacts[]` 或 workspace path，会看不到这些字段。

处理：这是本次有意的公开行为收缩。README 明确迁移方式：先根据 totals/evidence 判断，再使用 `agy_artifact_read` 读取 `errors`、`operation-log` 或 `result`。不添加 `verbose=true` 兼容开关，避免调用者继续把冷数据默认塞回模型上下文。

### 8.3 不能把“少日志”或长等待当停滞

Runtime 不新增基于 captured_bytes 静默时长的自动取消。内部 25 秒 long-poll 或公开 50～600 秒总等待预算到期都只表示一次观察窗口结束，不是 hang detector。

公开长等待不是 sleep：如果 AGY 在所选预算内提前 terminal，MCP 必须马上返回。相反，如果预算到期仍非终态，Codex 应直接发起下一次 status，不向用户插入“我再等一轮”等消息。

### 8.4 Codex 宿主工具超时

风险：合法 `wait_ms=600000` 大于旧注册 `tool_timeout_sec=60`，宿主会先于 Worker 结束调用。

处理：`manage.register()` 把该 MCP 的 `tool_timeout_sec` 提高到 660 秒，并要求升级后重新注册。该改变只影响宿主工具调用上限，不改变 Controller/Runtime 任务超时、安全边界或单段 long-poll。

## 9. 实施文件边界

原 v0.3.2 compact result 核心生产修改包括：

- `src/agy_worker/runtime.py`：compact task/result view + unchanged long-poll；
- `src/agy_worker/server.py`：MCP 表示层去重、短文本摘要与外部总等待 coalescing；
- `src/agy_worker/models.py`：MCP 外部 `McpStatusRequest` 与内部 `StatusRequest` 分层；
- `src/agy_worker/manage.py`：公开 schema 生成模型与 Codex MCP tool timeout 注册；
- `pyproject.toml`：版本 `0.3.2`；
- `tests/test_runtime.py`：status/terminal payload/证据回归；
- `tests/test_server.py`、`tests/test_mcp_hot_path.py`：CallToolResult、公开 status schema/边界、内部分片、deadline 与 terminal 提前返回；
- `tests/test_manage.py`：status schema regeneration 与 Codex host timeout；
- `tests/test_controller_reconnect.py`：只在既有断线语义因返回形状需要断言调整时最小修改；
- `README.md`、`docs/实施设计.md`：公开合同与迁移说明；
- `schemas/agy_status.json`：由 `McpStatusRequest` 生成的必要公开 schema 差异。

### 9.1 实施中代码质量审查发现的必要配套范围

为满足本规格已经锁定的兼容性与版本合同，实施 review 发现下列最小配套也必须纳入本 PR：

- `scripts/run-task.py`：从“假定 TextContent 是完整 JSON”迁移到优先读取 canonical `structured_content`，并保留旧 JSON TextContent fallback；否则 v0.3.2 会直接破坏仓库自己的官方任务验收入口；
- `tests/test_run_task.py`：锁定上述新/旧 server 兼容行为；
- `scripts/verify-controller.py`：把既有 package/server 验收目标从 `0.3.1` 同步到 `0.3.2`；
- `tests/test_controller_hardening_quality.py`：锁定 verifier 的 0.3.2 版本目标。

这四个文件是实现中发现的**兼容/版本维护必要项**，不是功能扩张。它们不改变 Controller lifecycle、协议、权限、Broker、Browser、数据库或执行槽语义。

本轮自适应 status 等待不借机修改 Runtime progress 记录、Controller lifecycle、Broker、Browser、Artifacts、权限或数据库 schema，也不修改任何 `AGENTS.md`。

## 10. 完成定义

只有以下条件全部满足才能把 v0.3.2 描述为完成：

- 计划中的 RED/GREEN 回归有真实执行证据；ChatGPT Web 只负责先写测试，不能把未执行测试描述为 PASS；
- 最终 `scripts/check.ps1` 与 `git diff --check` 有新鲜 Windows 证据；
- 公开 status schema、schema regeneration、内部 <=25 秒分片、660 秒 Codex host timeout 都有本地验证；
- PR diff 只包含本规格 §9 / §9.1 范围及 planning/acceptance 文档；
- 规格审查与代码质量审查无开放 Critical / Important finding；
- 本地 AI 的真实 Windows + AGY/Codex 复验完成，并由 ChatGPT 按 `receiving-code-review` 复核证据；
- `TASKS.md` 回填精确 validated HEAD 与各项证据；
- 未经用户明确授权，不 merge `main`、不删除分支、不启用自动合并。