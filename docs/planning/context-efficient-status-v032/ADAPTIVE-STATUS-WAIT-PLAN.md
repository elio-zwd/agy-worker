# AGY Worker 自适应状态等待 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. ChatGPT Web 当前无真实 subagent；按 `01-CHATGPT-WEB-ADAPTER.md` 顺序执行 implementation -> spec review -> code quality review -> local acceptance handoff。步骤使用 checkbox 跟踪。

**Goal:** 让 Codex 在 `agy_status` 中默认等待 50 秒，并可按任务预计耗时自主选择 50～600 秒；MCP Server 在一次调用内部按最多 25 秒的 Controller long-poll 分片吞掉 progress revision，AGY 一旦进入终态立即返回给 Codex。

**Architecture:** 新增 MCP 外部 `McpStatusRequest`，公开 `wait_ms` 默认 50000、范围 50000..600000；内部 `StatusRequest` 保持 0..25000，不改变 Controller/Runtime 协议。`server._coalesced_status()` 只把公开总预算切成内部 <=25000ms 调用；没有 `after_revision` 时只取一次即时快照，已有 revision 时才进入长等待。Codex MCP 注册的宿主 `tool_timeout_sec` 必须高于 600 秒，因此设为 660 秒，仅作为 MCP 工具调用上限而不改变任务或 status 自身预算。真正的 server-initiated push/webhook 不在本轮实现，避免依赖当前 Codex 宿主未验证的主动唤醒能力。

**Tech Stack:** Python 3.13、Pydantic v2、官方 MCP Python SDK、pytest、GitHub 分支 `perf/context-efficient-status-v032`。

**Spec:** `docs/planning/context-efficient-status-v032/SPEC.md`

## Global Constraints

- 继续使用 PR #2 与现有分支；不新建 PR。
- 本轮不修改任何 `AGENTS.md`。
- MCP 工具数量保持 6；Controller protocol 保持 2。
- Runtime/Controller 的内部 status 最大等待保持 25000ms；ControllerClient 单次 HTTP timeout 不扩大。
- 公开 `agy_status.wait_ms` 默认 50000ms，显式可选范围 50000..600000ms。
- Codex MCP 注册 `tool_timeout_sec=660`，确保 600 秒公开等待不会被宿主原 60 秒上限提前截断；本地部署需重新执行注册入口使配置生效。
- `after_revision` 缺失时 `agy_status` 作为即时快照读取，不把 50～600 秒预算直接透传给 Controller。
- `after_revision` 存在时，MCP 总等待预算由公开 `wait_ms` 决定；每个内部 long-poll <=25000ms；terminal 提前返回。
- 不实现 webhook、server-initiated push、MCP Tasks subscription，也不把 `agy_worker` 改成同步等待终态。
- ChatGPT Web 无本地测试执行环境：严格测试先写；只能声明“测试已写/代码已审查”，不能声明 pytest 或 Windows 验收已通过，最终交由本地 AI 执行 `scripts/check.ps1` 与真实 Codex 复验。

---

### Task 1: 锁定 MCP 外部等待合同（RED）

**Files:**
- Modify: `tests/test_mcp_hot_path.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: 当前 `build_server()` 暴露的 `agy_status` JSON Schema 与 `_coalesced_status()` 行为。
- Produces: 对公开默认/上下界、内部 25 秒分片、terminal 提前返回、无 revision 即时快照的回归约束。

- [ ] **Step 1: 添加公开 schema 行为测试**

新增 `test_status_schema_defaults_to_50s_and_allows_50_to_600s()`，通过真实 `list_tools` 输出断言 `wait_ms.default == 50000`、`minimum == 50000`、`maximum == 600000`。这能捕获错误默认值、错误下限或错误上限。

- [ ] **Step 2: 添加边界拒绝测试**

新增 `test_status_rejects_wait_outside_public_range_before_controller()`，分别提交 `49999` 与 `600001`，要求 MCP 返回 `invalid_request` 且 Controller client 没有收到 status 调用。

- [ ] **Step 3: 更新现有 coalescing 测试到公开最小 50 秒**

把原先调用 `wait_ms=25000` 的 MCP 测试改为 `wait_ms=50000`，同时继续断言实际传给 Controller 的每一段 `wait_ms <= 25000`。

- [ ] **Step 4: 添加 600 秒预算仍按 25 秒分片且 terminal 提前返回测试**

使用 `StatusSequenceClient` 返回 running revision 后紧接 terminal；公开调用传 `wait_ms=600000`，断言实际内部调用仍为 `25000` 分片，且 terminal 后没有额外 status 调用。

- [ ] **Step 5: 添加无 after_revision 的即时快照测试**

公开调用只传 `task_id`，断言 Controller 收到 `wait_ms=0` 而不是默认 50000；结果直接返回当前快照，不进入重复 long-poll。

- [ ] **Step 6: 调整 `tests/test_server.py` 的旧 `wait_ms=0` MCP 调用**

公开 MCP 不再允许 0；测试改为省略 `wait_ms`/`after_revision`，由即时快照语义覆盖 TextContent 与错误路径。

- [ ] **Step 7: RED 说明**

ChatGPT Web 无法运行仓库 pytest；提交本 Task 后记录 `red_execution: not_run_in_chatgpt_web`。这些测试针对修改前代码的预期失败点为：公开 schema 仍是 0..25000/default 0，且没有外部/内部 StatusRequest 分层。

### Task 2: 实现 MCP 外部/内部 StatusRequest 分层（GREEN）

**Files:**
- Modify: `src/agy_worker/models.py`
- Modify: `src/agy_worker/server.py`

**Interfaces:**
- Produces: `McpStatusRequest(task_id, after_revision=None, wait_ms=50000)`，其中 `wait_ms` 为 50000..600000；内部 `StatusRequest` 继续 0..25000。
- Consumes: `ControllerClient.call("status", params, timeout=30)`，内部 params 继续符合原 Controller contract。

- [ ] **Step 1: 新增 `McpStatusRequest`**

在 `models.py` 中把公开模型定义为：

```python
class McpStatusRequest(Strict):
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(50000, ge=50000, le=600000)
```

保留现有内部：

```python
class StatusRequest(Strict):
    task_id: str
    after_revision: int | None = None
    wait_ms: int = Field(0, ge=0, le=25000)
```

- [ ] **Step 2: `agy_status` 对外改用 `McpStatusRequest`**

`server.py` 导入 `McpStatusRequest`，`TOOLS["agy_status"]` 使用该模型；tool description 明确：省略时 50 秒，Codex 可按任务预计耗时选择 50～600 秒，AGY 提前完成立即返回。

- [ ] **Step 3: 保持无 revision 为即时快照**

`_coalesced_status()` 在 `after_revision is None` 时调用 Controller：

```python
{**params, "wait_ms": 0}
```

只读取当前状态，不把 50000..600000 直接交给内部模型。

- [ ] **Step 4: 总预算分片**

`after_revision` 存在时，以公开 `wait_ms` 建立单一 monotonic deadline；每次 Controller 参数继续：

```python
"wait_ms": max(1, min(25000, int(remaining * 1000)))
```

中间 revision/unchanged 继续被 MCP 吞掉；terminal 立即返回；deadline 到达后只做 `wait_ms=0` 的即时快照。

- [ ] **Step 5: 更新 Server instructions**

删除固定 `wait_ms=25000` 指令，改为：默认 50 秒；预计较久的 build/test 可自主选择 50～600 秒较长预算；一次 status 内部自动 coalesce；非终态后直接再次调用且不向用户输出等待说明。

### Task 3: 同步公开 Schema、宿主超时与说明

**Files:**
- Modify: `src/agy_worker/manage.py`
- Modify: `tests/test_manage.py`
- Modify: `schemas/agy_status.json`
- Modify: `README.md`
- Modify: `docs/实施设计.md`
- Modify: `docs/planning/context-efficient-status-v032/SPEC.md`
- Modify: `docs/planning/context-efficient-status-v032/LOCAL-ROUTING-RECHECK.md`
- Modify: `docs/planning/context-efficient-status-v032/TASKS.md`

**Interfaces:**
- Produces: 与 `McpStatusRequest` 一致的公开 schema、可覆盖 600 秒等待的 Codex MCP 宿主配置和本地验收合同。

- [ ] **Step 1: 先锁定 schema generator 与宿主 timeout 测试**

`manage.schemas()` 生成的 `agy_status.json` 必须来自 `McpStatusRequest`；`manage.register()` 写出的 `mcp_servers.agy_worker.tool_timeout_sec` 必须大于 600 秒，避免宿主先于合法 `wait_ms=600000` 截断调用。

- [ ] **Step 2: 更新 `manage.py`**

schema generator 使用 `McpStatusRequest`；Codex MCP 注册 `tool_timeout_sec=660`。这个 660 秒只是宿主调用上限，不改变 `agy_status` 最大 600 秒，也不改变 Controller HTTP timeout。

- [ ] **Step 3: 同步 `schemas/agy_status.json`**

`wait_ms` 固定为 default 50000 / minimum 50000 / maximum 600000；`task_id` 仍唯一 required 字段。

- [ ] **Step 4: 更新 README 与实施设计**

明确公开等待预算 50～600 秒、默认 50 秒；内部 Controller 仍 <=25 秒分片；terminal 提前返回；无 `after_revision` 为即时快照；`register.ps1` 应用 660 秒宿主上限；不宣称实现主动 push。

- [ ] **Step 5: 更新规格**

把旧“StatusRequest schema 不变/最多 25 秒”的描述替换为 MCP 外部/内部模型分层；非目标继续保留“本轮不增加 webhook/push notification”。

- [ ] **Step 6: 更新本地复验**

删除 `status_wait_25000_seen` 作为 Codex 外部硬条件，改为记录 Codex 选择的 `wait_ms`；要求省略时 schema 默认 50000，显式值必须 50000..600000；Controller/internal probe 若可见则确认各分片 <=25000；真实复验前重新执行 `scripts/register.ps1` 并核对 `tool_timeout_sec=660`。

- [ ] **Step 7: 更新 Task Tracker**

新增 adaptive wait 的测试/实现/schema/host-timeout/docs/本地复验状态；新生产代码 target 在代码提交后回填。

### Task 4: 独立规格与代码质量审查

**Files:**
- Review all files changed after `094445f4c57663375a725ecae74d236ddaa24567`

- [ ] **Step 1: 规格审查 pass**

逐条核对：50 秒默认；50～600 秒公开范围；terminal 提前返回；内部 <=25 秒；Codex tool timeout 660 秒；无 unsolicited push；6 tools/protocol 2/权限不变；不触碰 `AGENTS.md`。

- [ ] **Step 2: 代码质量 pass**

重点检查 deadline 不被 progress revision 重置、无 tight loop、无 >25 秒透传 Controller、`after_revision=None` 不阻塞、validation 在 MCP 边界失败、宿主 timeout 不小于合法最大等待、测试不只 grep 文本。

- [ ] **Step 3: 检查最终 diff**

通过 GitHub compare 查看从 adaptive wait 开始到当前 HEAD 的实际文件范围；确认没有意外 Runtime/Controller/权限/AGENTS 改动。

### Task 5: Windows + 真实 Codex 本地验收交接

**Files:**
- Modify: `docs/planning/context-efficient-status-v032/LOCAL-ROUTING-RECHECK.md`
- Modify: `docs/planning/context-efficient-status-v032/TASKS.md`

- [ ] **Step 1: 本地自动化与重新注册**

本地 AI 执行 `scripts/check.ps1`、`git diff --check`、schema regeneration；随后运行 `scripts/register.ps1` 使 Codex MCP 的 `tool_timeout_sec=660` 生效，并核对原有用户 developer instructions 仍被保留。返回真实 passed/failed 数量与 exit code。

- [ ] **Step 2: 真实 Codex 热路径**

新会话只发“使用AGY跑编译测试”，记录 `agy_worker` 与 `agy_status` 参数。重点验证默认/自选长等待减少 GPT 可见 status round-trip，AGY terminal 后当前 status 调用立即返回，同一 Codex 会话继续处理结果。

- [ ] **Step 3: 不把长预算理解成固定 sleep**

若选择例如 120000ms，但 AGY 20 秒完成，必须约在终态出现时立即返回；不得等满 120 秒。

- [ ] **Step 4: 完成门禁**

只有本地 Windows 回归、schema、注册配置、真实 Codex 行为均有新证据后，才能把 Task Tracker 从 awaiting local recheck 改为 accepted；PR #2 继续 Draft，未经用户明确授权不 merge。
