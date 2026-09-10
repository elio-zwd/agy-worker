# AGY Worker v0.3.2 低上下文状态与结果规格

> 本规格记录 2026-09-10 真实使用数据暴露出的 Codex 上下文放大问题，并定义后续实现必须遵守的公开返回合同。
> 本轮仅创建规划与审查入口，不修改生产代码；后续实现必须继续遵守 `AGENTS.md`、TDD 与最终 Windows/真实 AGY 验收边界。

## 1. 背景与问题

AGY Worker 的初衷是让 AGY 处理编译、日志、浏览器、图片等高噪声工作，Codex 只接收足以做判断的摘要与证据引用。当前 v0.3.1 已经把原始 stdout/stderr、AGY stream 和完整 artifact 留在任务目录，但公开 MCP 热路径仍把过多诊断数据直接送进 Codex 上下文。

2026-09-10 的真实 `jianyu_lint_assemble` 使用记录显示：

1. `agy_status(task_id, after_revision=5, wait_ms=25000)` 在 revision 没变化时连续多次返回同一份完整 running record；
2. 同一次 MCP 调用的返回对象同时出现在 TextContent JSON 和 `structuredContent` 中，宿主记录因此出现两份等价 JSON；
3. 终态 result 直接展开最多 20 条 warnings/errors 和整份 artifact metadata；Android/Kotlin warning 单条就可能很长；
4. `after_revision` 当前只控制“等多久”，没有表达“本轮等待结束但没有新 revision”的紧凑语义；
5. 长时间没有 stdout 变化并不代表构建卡死。真实记录中任务已经进入 `generateDebugLintReportModel`，却因为一段时间没有新增日志被误判为疑似卡住并主动取消。

这不是单纯的“summary_max_bytes 太大”。根因是 **热路径状态、冷路径证据和 MCP 表示层没有彻底分层**。

## 2. 根因

### 2.1 MCP 表示层重复

`src/agy_worker/server.py` 当前对普通 JSON 工具返回：

```python
types.CallToolResult(
    content=[types.TextContent(type="text", text=json.dumps(result, ensure_ascii=False))],
    structuredContent=result,
)
```

同一个对象被完整编码两次。即使 Runtime 已经控制了 result 大小，Codex 仍可能为同一信息付出接近两倍上下文成本。

### 2.2 long-poll 无变化仍返回完整 record

`Runtime.status()` 在 `wait_ms` deadline 到达时无条件 `return self.public(record)`。因此 `after_revision` 没有产生 delta/unchanged 返回；调用者每 25 秒可能再次收到 session、turn、时间戳、progress 等完全相同的数据。

### 2.3 终态把“判断信息”和“取证信息”混在一起

`Runtime._run()` 的 result 同时包含：

- Codex 立即需要的 `status`、summary、退出码、错误/警告计数；
- 仅在排错时才需要的完整 warning/error 条目；
- workspace path、snapshot、AGY PID、enforcement；
- 所有 artifact 的 size/hash/media-type/created-at/sensitive metadata。

但同一任务已经存在 `result`、`errors`、`operation-log` 等 artifact，可通过 `agy_artifact_read` 显式读取。把这些冷数据默认展开到 status 是职责重叠。

## 3. 目标

v0.3.2 的目标是：**让 Codex 默认只接收“下一步决策所需信息”，完整事实与证据继续可靠保存在 artifact 中，需要时再按证据 ID 读取。**

必须达到：

- 同一逻辑 JSON 不再在 MCP `content` 与 `structuredContent` 中完整重复；
- `after_revision` long-poll 超时且无变化时返回极小的 `unchanged` envelope；
- build/test 终态默认不展开 warning/error 正文和 artifact manifest；
- 失败仍必须保留错误数量、命令退出码、termination reason 和可追溯 evidence ID，不能为了省 token 丢失可诊断性；
- `agy_artifact_read` 继续作为显式高信息量/高 token 成本的冷路径读取入口；
- 不把“无 stdout 更新”定义为 hung/stalled；任务终态仍只由 Runtime 的进程、取消、超时和业务验证规则决定；
- 不改变单 Runtime、单执行槽、权限、快照、Controller stale/stop、request_id 幂等语义。

## 4. 非目标

本阶段不做：

- 不增加 webhook、push notification 或后台主动向 Codex 发消息；
- 不把 `agy_worker` 改回同步阻塞直到任务完成；
- 不改变 `MAX_CONCURRENT_TASKS=1` 或 `MAX_INFLIGHT_TASKS=16`；
- 不扩大 shell、code_write、浏览器或 Android 权限；
- 不改变 `summary_max_bytes` 的 2048～16384 现有输入范围；
- 不在 v0.3.2 首轮引入 progress 节流。先解决已证实的重复表示、无变化返回和终态热/冷数据混合，再根据真实 token 数据决定是否需要减少 progress revision 频率；
- 不因为状态压缩而删除本地 artifact、hash、审计或完整 result 证据。

## 5. 设计决定

### 5.1 热路径与冷路径分层

公开数据分为两类：

**热路径：** `agy_worker`、`agy_continue`、`agy_status`、`agy_cancel` 的任务 envelope，以及 `agy_capabilities` 的能力结构。目标是让 Codex快速判断“是否完成、是否失败、下一步是否需要读证据”。

**冷路径：** `agy_artifact_read`。只有 Codex 明确需要日志、错误正文、完整 result 或图片时才读取，允许返回较大内容，但仍受现有 200 行/64 KiB/图片大小和敏感证据规则限制。

### 5.2 统一紧凑任务 envelope

新增 Runtime 内部渲染逻辑（函数名在实施计划中锁定为 `_public_task(record, *, unchanged=False)`），不改变 SQLite record 本身。

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

终态任务 envelope 保留 `task_id`、`session_id`、`turn`、`status`、`revision`，`result` 使用紧凑视图。

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
- `changed_files` 全量列表。

如果 `source_changed=true`，紧凑 result 额外返回 `changed_files_preview`，最多 5 个路径，以及 `changed_files_count`。完整列表仍由 `result` artifact 提供。

对 log/browser/vision/android-ui 等非 build/test 任务，紧凑 result 至少保留：`schema_version=2`、UTF-8 有界 `summary`、`source_changed`、`termination_reason`、`result_artifact_id`、`artifact_count`、`truncated`；已有的类型特定证据仍从 result artifact 或对应 artifact 读取。

### 5.5 summary 的热路径硬预算

新增内部常量：

```python
PUBLIC_SUMMARY_MAX_BYTES = 768
```

新增 helper：

```python
def _truncate_utf8(value: str, max_bytes: int) -> str:
    raw = value.encode("utf-8")
    if len(raw) <= max_bytes:
        return value
    return raw[:max_bytes].decode("utf-8", errors="ignore")
```

只有公开紧凑 result 使用该上限；本地 `result.json` 的现有 `summary_max_bytes` 规则保持不变。

### 5.6 MCP 双通道不再复制完整 JSON

对普通 JSON 工具，`structuredContent` 继续作为机器可读的 canonical value；`content` 只返回一个稳定、短小的人类可读摘要，不再 `json.dumps(result)`。

目标例：

```text
agy_status: running rev=5；无变化
agy_status: succeeded rev=35；操作成功，日志采集完成。
agy_worker: queued rev=1；task=task-...
```

热路径 `TextContent.text` UTF-8 长度必须 `<= 256 bytes`。

`agy_artifact_read` 是例外：它是显式冷路径。为了避免同一大段证据再次双份出现，同时保持只消费 TextContent 的客户端可读，文本 artifact 的内容只放在 `content`，`structuredContent` 不再附同一份完整对象；图片路径继续使用 `ImageContent`。artifact metadata-only 读取也走单载荷，不做双份 JSON。

错误返回同样使用短 `TextContent` + structured error body，禁止把完整 error JSON复制两遍。

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

## 6. 协议与版本

- 目标包版本：`0.3.2`；
- MCP 工具数量保持 6，不新增工具；
- `StatusRequest` 输入字段保持 `task_id / after_revision / wait_ms`，因此不需要新增公开输入字段；
- `schemas/agy_status.json` 等输入 schema 不因本规格新增字段；生成 schema 仍需在实现完成时跑一次并确认无意外差异；
- Controller `/control/call` 内部协议继续 `PROTOCOL_VERSION=2`。本次没有改变 IPC request framing、鉴权或方法集合；Runtime 实现摘要与 package version 已能让旧/新实现 fail-closed，不为只改变公开结果视图机械升级 protocol v3；
- README 与 `docs/实施设计.md` 必须明确 v0.3.2 的 compact status 语义。

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
4. terminal status 保留 exit code、error/warning counts、termination reason、source-changed flag 和 evidence/result artifact ID；
5. status reconnect 第二次 `wait_ms=0` 的 v0.3.1 合同继续通过；
6. cancellation、request_id 幂等、16 inflight、Controller stale/stop 等既有测试不得因本次返回视图改变而失效；
7. `scripts/check.ps1` 最终必须 exit 0；
8. 本地 AI 必须用真实 AGY 至少执行一次会产生 warnings 的 build/test，记录各次 `agy_status` 的实际返回字节数，并验证 Codex 侧不再出现同一完整 JSON 双份；
9. 真实任务期间连续两次在无 stdout 增长条件下 long-poll，必须只得到 compact `unchanged`，不能因此自动 cancel；最终状态由实际进程终态决定。

## 8. 兼容与风险

### 8.1 TextContent-only 客户端

风险：某些客户端只读取 `content` 而忽略 `structuredContent`。

处理：普通热路径仍保留短 TextContent，不返回空 content；artifact 文本读取继续把实际证据放进 TextContent。这样既不重复大 JSON，也不把旧式文本消费者完全断开。

### 8.2 依赖旧终态字段的调用方

风险：调用方若直接依赖 status 中的 `warnings[]`、`artifacts[]` 或 workspace path，会看不到这些字段。

处理：这是本次有意的公开行为收缩。README 明确迁移方式：先根据 totals/evidence 判断，再使用 `agy_artifact_read` 读取 `errors`、`operation-log` 或 `result`。不添加 `verbose=true` 兼容开关，避免调用者继续把冷数据默认塞回模型上下文。

### 8.3 不能把“少日志”当停滞

Runtime 不新增基于 captured_bytes 静默时长的自动取消。`wait_ms` 到期只表示“观察窗口内状态 revision 未改变”，不是 hang detector。

## 9. 实施文件边界

计划中的生产修改限制在：

- `src/agy_worker/runtime.py`：compact task/result view + unchanged long-poll；
- `src/agy_worker/server.py`：MCP 表示层去重与短文本摘要；
- `pyproject.toml`：版本 `0.3.2`；
- `tests/test_runtime.py`：status/terminal payload/证据回归；
- `tests/test_server.py`：CallToolResult 双通道去重测试；
- `tests/test_controller_reconnect.py`：只在既有断线语义因返回形状需要断言调整时最小修改；
- `README.md`、`docs/实施设计.md`：公开合同与迁移说明；
- `schemas/*.json`：只允许由模型重新生成后产生的必要差异；若输入模型没变，预期无 schema diff。

不借机重构 Controller、Broker、Browser、Artifacts、权限或数据库 schema。

## 10. 完成定义

只有以下条件全部满足才能把 v0.3.2 描述为完成：

- 计划中的 RED/GREEN 回归真实执行；
- 最终 `scripts/check.ps1` 与 `git diff --check` 有新鲜证据；
- PR diff 只包含本规格范围；
- 规格审查与代码质量审查无开放 Critical / Important finding；
- 本地 AI 的真实 Windows + AGY token/字节验收完成，并由 ChatGPT 按 `receiving-code-review` 复核证据；
- `TASKS.md` 回填精确 validated HEAD 与各项证据；
- 未经用户明确授权，不 merge `main`、不删除分支、不启用自动合并。
