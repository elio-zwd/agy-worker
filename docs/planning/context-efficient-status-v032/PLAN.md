# AGY Worker v0.3.2 低上下文状态与结果 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. ChatGPT Web 没有真实 subagent 时，按项目 Web Adapter 顺序执行 implementation → spec review → code-quality review，不得虚构子代理。步骤使用 checkbox (`- [ ]`) 跟踪。

**Goal:** 将 AGY Worker 的默认 Codex-facing 状态/结果热路径压缩为决策摘要，把 warning/error 正文和 artifact manifest 留在显式证据读取通道，消除 long-poll 重复状态与 MCP 双份 JSON。

**Architecture:** 保持 Controller/Runtime 的任务记录、完整 result artifact 和现有权限边界不变，在 Runtime 增加“持久 record → compact public envelope”的纯视图层；`agy_status` 在 after_revision 无变化 timeout 时返回最小 unchanged envelope。stdio Bridge 使用 `structuredContent` 承载普通 JSON 工具的 canonical value，`TextContent` 只给短摘要；显式 `agy_artifact_read` 只发送一份实际证据。

**Tech Stack:** Python 3.13–3.14、mcp 2.2.0、Pydantic 2.13.5、pytest、Windows PowerShell 7。

**Spec:** `docs/planning/context-efficient-status-v032/SPEC.md`

## Global Constraints

- Base 固定为 `b51d81701f3cfe3859c485f87e42a03b22b4e3d7`；开发分支 `perf/context-efficient-status-v032`。
- 目标 package version 为 `0.3.2`；Controller `PROTOCOL_VERSION` 保持 `2`。
- MCP 对外工具仍为 6 个，不新增工具。
- `StatusRequest` 仍只有 `task_id / after_revision / wait_ms`，不增加 `verbose` / `detail` 开关。
- `summary_max_bytes` 输入范围仍为 2048～16384；compact public summary 另设 `PUBLIC_SUMMARY_MAX_BYTES=768`。
- `code_write=false`、任意 shell 关闭、单执行槽、16 inflight、Controller stale/stop、request_id 幂等等现有边界不变。
- 无 stdout/progress 更新不能作为 hung detector 或自动 cancel 条件。
- 完整 `result`、`errors`、`operation-log` 等 artifact 必须保留；token 优化不能删除证据。
- 不在本阶段引入 progress revision 节流；先验证已证实的三个放大器。
- 每个生产代码任务必须按 RED → GREEN → REFACTOR；没有实际运行证据不得把测试写成 PASS。

---

## File Map

| File | Responsibility in v0.3.2 |
|---|---|
| `src/agy_worker/runtime.py` | compact task/result renderer；unchanged long-poll 语义；UTF-8 summary 截断 |
| `src/agy_worker/server.py` | MCP 单载荷策略；普通工具短 TextContent + structured canonical；artifact 单份返回 |
| `tests/test_runtime.py` | public envelope、byte budget、artifact drill-down、terminal/no-change regression |
| `tests/test_server.py` | CallToolResult 双通道去重、artifact 单份、错误单份与 text budget |
| `tests/test_controller_reconnect.py` | 保持断线后第二次 status `wait_ms=0`；仅必要时调整返回断言 |
| `pyproject.toml` | package version 0.3.2 |
| `README.md` | 用户合同、迁移路径、低 token 使用方式 |
| `docs/实施设计.md` | v0.3.2 公开 status/result 语义与验收门禁 |
| `docs/planning/context-efficient-status-v032/*` | 跨对话规格、计划、任务进度与最终证据 |

---

### Task 1: Runtime compact public view + unchanged long-poll

**Files:**
- Modify: `src/agy_worker/runtime.py`
- Modify: `tests/test_runtime.py`

**Interfaces:**
- Consumes: 现有 SQLite task `record`、现有 terminal `record["result"]`、现有 artifact IDs。
- Produces: `Runtime._public_task(record, *, unchanged=False) -> dict`。
- Produces: `Runtime._public_result(result) -> dict`。
- Produces: module helper `_truncate_utf8(value: str, max_bytes: int) -> str`。
- Preserves: `Runtime.public(record)` 作为现有内部调用入口，改为委托 `_public_task(record)`，避免无关 call-site 重写。

- [ ] **Step 1: 写 RED — 无变化 status 必须是最小 envelope**

在 `tests/test_runtime.py` 增加：

```python
def test_status_after_revision_timeout_returns_compact_unchanged(runtime):
    state = runtime.submit(request(request_id="req-status-unchanged"))

    result = runtime.status(
        state["task_id"],
        after_revision=state["revision"],
        wait_ms=0,
    )

    assert result == {
        "task_id": state["task_id"],
        "status": "queued",
        "revision": state["revision"],
        "unchanged": True,
    }
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= 256
```

Run:

```text
python -m pytest -q tests/test_runtime.py::test_status_after_revision_timeout_returns_compact_unchanged
```

Expected RED: 当前实现会返回 `session_id`、`turn`、`created_at`、`updated_at` 等字段，断言失败。

- [ ] **Step 2: 写 RED — changed running 状态不得带时间戳/result**

增加：

```python
def test_public_running_state_is_compact(runtime):
    state = runtime.submit(request(request_id="req-running-public"))
    context = runtime.active[state["task_id"]]
    context["record"]["status"] = "running"
    context["record"]["progress"] = {"agy_pid": 1234, "captured_bytes": 2048}
    runtime._save(context["record"])

    result = runtime.status(state["task_id"], wait_ms=0)

    assert set(result) == {"task_id", "session_id", "turn", "status", "revision", "progress"}
    assert result["progress"] == {"agy_pid": 1234, "captured_bytes": 2048}
    encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    assert len(encoded) <= 512
```

Run:

```text
python -m pytest -q tests/test_runtime.py::test_public_running_state_is_compact
```

Expected RED: 当前 `public()` 含 timestamps。

- [ ] **Step 3: 写 RED — 大型 terminal diagnostics 不能进入 public status，但 artifact 仍存在**

测试构造 terminal result 时使用真实字段名，至少生成 20 条长 warning、20 条长 error 和 12 个 artifact metadata。测试不需要启动 AGY：直接在 fixture task directory 写 `errors.json`、`result.json` 并通过 `context["artifacts"].add(...)` 登记，然后把完整 result 放入 `record["result"]`。

核心断言：

```python
public = runtime.status(state["task_id"], wait_ms=0)
compact = public["result"]

assert public["status"] == "failed"
assert compact["schema_version"] == 2
assert compact["operation"]["exit_code"] == 1
assert compact["operation"]["total_errors"] == 20
assert compact["operation"]["total_warnings"] == 20
assert compact["diagnostics_artifact_id"] == "errors"
assert compact["result_artifact_id"] == "result"
assert "errors" not in compact
assert "warnings" not in compact
assert "artifacts" not in compact
assert "workspace_path" not in compact
assert "input_snapshot" not in compact
assert "agy" not in compact
assert "enforcement" not in compact
encoded = json.dumps(public, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
assert len(encoded) <= 1536
```

并验证冷路径：

```python
diagnostics = runtime.read_artifact(state["task_id"], "errors", view="text", start_line=1, line_count=20)
assert diagnostics["artifact_id"] == "errors"
assert diagnostics["text"]
```

Run:

```text
python -m pytest -q tests/test_runtime.py -k "terminal and compact"
```

Expected RED: 当前 status 展开 diagnostics/artifact metadata，payload 超预算。

- [ ] **Step 4: 写 RED — terminal 不能被 unchanged 掩盖**

增加：

```python
def test_terminal_status_wins_over_same_after_revision(runtime):
    state = runtime.submit(request(request_id="req-terminal-same-rev"))
    context = runtime.active[state["task_id"]]
    context["record"].update(
        status="succeeded",
        result={
            "schema_version": 1,
            "status": "succeeded",
            "summary": "操作成功，日志采集完成。",
            "source_changed": False,
            "termination_reason": None,
            "artifacts": [],
            "artifact_count": 0,
            "result_artifact_id": "result",
            "truncated": False,
        },
    )
    runtime._save(context["record"])
    terminal_revision = context["record"]["revision"]

    result = runtime.status(
        state["task_id"],
        after_revision=terminal_revision,
        wait_ms=0,
    )

    assert result["status"] == "succeeded"
    assert "result" in result
    assert "unchanged" not in result
```

Expected RED only if implementation naively applies `revision <= after_revision` before terminal check；该测试先锁死正确优先级。

- [ ] **Step 5: 实现 UTF-8 有界 helper 与 compact result renderer**

在 `runtime.py` 的常量区增加：

```python
PUBLIC_SUMMARY_MAX_BYTES = 768
PUBLIC_CHANGED_FILES_PREVIEW = 5


def _truncate_utf8(value, max_bytes):
    raw = (value or "").encode("utf-8")
    if len(raw) <= max_bytes:
        return value or ""
    return raw[:max_bytes].decode("utf-8", errors="ignore")
```

在 `Runtime` 内增加 `_public_result`，只复制允许字段，不修改原 result：

```python
def _public_result(self, result):
    compact = {
        "schema_version": 2,
        "summary": _truncate_utf8(result.get("summary", ""), PUBLIC_SUMMARY_MAX_BYTES),
        "source_changed": bool(result.get("source_changed", False)),
        "termination_reason": result.get("termination_reason"),
        "result_artifact_id": result.get("result_artifact_id", "result"),
        "artifact_count": int(result.get("artifact_count", len(result.get("artifacts", [])))),
        "truncated": bool(result.get("truncated", False)),
    }
    operation = result.get("operation")
    if operation:
        compact["operation"] = {
            key: operation.get(key)
            for key in (
                "command_id", "exit_code", "duration_ms", "termination_reason",
                "total_errors", "total_warnings", "evidence",
            )
            if key in operation
        }
    else:
        for key in ("total_errors", "total_warnings"):
            if key in result:
                compact[key] = result[key]
    if result.get("errors") is not None or result.get("warnings") is not None:
        compact["diagnostics_artifact_id"] = "errors"
    if compact["source_changed"]:
        changed = list(result.get("changed_files", []))
        compact["changed_files_count"] = len(changed)
        compact["changed_files_preview"] = changed[:PUBLIC_CHANGED_FILES_PREVIEW]
    return compact
```

实现时允许把 `diagnostics_artifact_id` 的判断改成“manifest 中实际存在 errors artifact”这一更严格条件，但不得出现不存在的 artifact ID。测试 fixture 应据此登记 `errors`。

- [ ] **Step 6: 实现 `_public_task` / `public` 委托**

目标逻辑：

```python
def _public_task(self, record, *, unchanged=False):
    if unchanged:
        return {
            "task_id": record["task_id"],
            "status": record["status"],
            "revision": record["revision"],
            "unchanged": True,
        }
    keys = ("task_id", "session_id", "turn", "status", "revision", "progress", "error")
    result = {key: record[key] for key in keys if key in record}
    if "result" in record:
        result["result"] = self._public_result(record["result"])
    return result


def public(self, record):
    return self._public_task(record)
```

`error` 只用于 Runtime 自身异常状态，保留现有受控错误信息；正常 terminal detail 走 compact result。

- [ ] **Step 7: 修改 `status()` timeout 分支**

保持现有 condition-based wait；只区分返回形状：

```python
if after_revision is None or record["revision"] > after_revision or record["status"] in TERMINAL:
    return self._public_task(record)
if time.monotonic() >= deadline:
    return self._public_task(record, unchanged=True)
```

不要新增“静默 N 秒就取消”或 stdout-based hang detection。

- [ ] **Step 8: GREEN — 运行 Runtime 定向测试**

Run:

```text
python -m pytest -q tests/test_runtime.py
```

Expected GREEN: 本文件全部通过；记录确切 passed 数，不预填数量。

- [ ] **Step 9: REFACTOR — 检查 compact renderer 只做 view transformation**

检查：

- `_public_result()` 不修改输入 dict；
- `result.json`/manifest 的生成代码不因 public renderer 被删除；
- no-change response 不影响 terminal detection；
- 无时间驱动 auto-cancel；
- byte budget 测试使用 compact separators，避免测试被空格格式影响。

- [ ] **Step 10: Commit**

```text
git add src/agy_worker/runtime.py tests/test_runtime.py
git commit -m "perf: 压缩任务状态与终态结果"
```

---

### Task 2: MCP response representation 去重

**Files:**
- Modify: `src/agy_worker/server.py`
- Modify: `tests/test_server.py`

**Interfaces:**
- Consumes: Task 1 的 compact task/result dict；其他 Controller JSON response 保持 dict。
- Produces: `_compact_tool_text(tool_name: str, result: dict) -> str`，UTF-8 `<=256 bytes`。
- Produces: 普通工具 `CallToolResult(content=[short TextContent], structuredContent=result)`。
- Produces: `agy_artifact_read` 文本/metadata 单份 `TextContent`，不再附同一 structured payload；图片保持 ImageContent。

- [ ] **Step 1: 写 RED — status 不得在 text 和 structured 中复制同一 JSON**

在 `tests/test_server.py` 增加可捕获 `on_call_tool` 的 FakeServer，并使用 FakeClient：

```python
class FakeClient:
    def __init__(self, result):
        self.result = result

    def call(self, method, params, timeout=None):
        return self.result
```

测试通过 `SimpleNamespace(name="agy_status", arguments={...})` 调用 `build_server()` 捕获的 callback：

```python
result = asyncio.run(on_call_tool(None, params))
assert result.structuredContent == compact_status
assert len(result.content) == 1
assert result.content[0].type == "text"
assert result.content[0].text != json.dumps(compact_status, ensure_ascii=False)
assert len(result.content[0].text.encode("utf-8")) <= 256
```

Run:

```text
python -m pytest -q tests/test_server.py -k "duplicate or compact_text"
```

Expected RED: 当前 `TextContent.text` 正是完整 JSON。

- [ ] **Step 2: 写 RED — unchanged 与 terminal 文本必须直接可读**

锁定至少：

```python
assert _compact_tool_text("agy_status", {
    "task_id": "task-1", "status": "running", "revision": 5, "unchanged": True,
}) == "agy_status: running rev=5；无变化"
```

terminal 只要求包含 `status`、`rev` 和 nested `result.summary`，不包含 warnings/errors/artifacts JSON。

- [ ] **Step 3: 写 RED — artifact text 只能出现一份**

FakeClient 对 `artifact_read` 返回：

```python
{
    "content_type": "json",
    "value": {
        "artifact_id": "operation-log",
        "text": "line 1\nline 2",
        "truncated": False,
    },
}
```

断言：

```python
assert result.structuredContent is None
assert len(result.content) == 1
assert result.content[0].type == "text"
payload = json.loads(result.content[0].text)
assert payload["artifact_id"] == "operation-log"
assert payload["text"] == "line 1\nline 2"
```

图片 artifact 的既有 `ImageContent` 测试/行为保持不变。

- [ ] **Step 4: 写 RED — error 不能双份 JSON**

让 FakeClient 抛 `WorkerError("worker_busy", "busy")`，断言：

- `isError is True`；
- `structuredContent["code"] == "worker_busy"`；
- TextContent 只包含短 message/hint，不等于完整 `json.dumps(structuredContent)`；
- UTF-8 长度 `<=256 bytes`。

- [ ] **Step 5: 实现 server 侧 UTF-8 short text helper**

在 `server.py` 增加局部常量/helper，避免从 Runtime 导入私有实现：

```python
TOOL_TEXT_MAX_BYTES = 256


def _truncate_tool_text(value):
    raw = value.encode("utf-8")
    if len(raw) <= TOOL_TEXT_MAX_BYTES:
        return value
    return raw[:TOOL_TEXT_MAX_BYTES].decode("utf-8", errors="ignore")


def _compact_tool_text(tool_name, result):
    status = result.get("status") if isinstance(result, dict) else None
    revision = result.get("revision") if isinstance(result, dict) else None
    if tool_name == "agy_status" and result.get("unchanged"):
        return f"agy_status: {status} rev={revision}；无变化"
    if status is not None:
        text = f"{tool_name}: {status} rev={revision}"
        summary = (result.get("result") or {}).get("summary")
        if summary:
            text += f"；{summary}"
        return _truncate_tool_text(text)
    return _truncate_tool_text(f"{tool_name}: ok")
```

实现必须对非 dict 防御，不能因为摘要逻辑让合法 Controller 返回变成 Bridge crash。

- [ ] **Step 6: 修改普通 JSON 工具返回**

普通工具改为：

```python
return types.CallToolResult(
    content=[types.TextContent(type="text", text=_compact_tool_text(params.name, result))],
    structuredContent=result,
)
```

不得再对普通 result 做 `json.dumps(result)` 填进 TextContent。

- [ ] **Step 7: 修改 `agy_artifact_read` 单载荷分支**

`content_type == "image"` 保持现有 ImageContent。

`content_type == "json"` 时：

```python
value = result["value"]
return types.CallToolResult(
    content=[types.TextContent(type="text", text=json.dumps(value, ensure_ascii=False))],
)
```

不要同时设置 `structuredContent=value`。这是显式冷路径，允许 TextContent 较大，但只允许一份。

- [ ] **Step 8: 修改 error 返回去重**

错误 body 继续放 `structuredContent`；TextContent 改为受 256-byte 限制的人类短消息，例如：

```text
worker_busy: Worker 当前已有 16 个待执行或运行任务，请稍后重试
```

保留 `hint` 在 structured body，不要求完整 hint 再复制进 TextContent。

- [ ] **Step 9: GREEN — 运行 server tests**

Run:

```text
python -m pytest -q tests/test_server.py
```

Expected GREEN: 全部通过；记录真实数量。

- [ ] **Step 10: 回归 reconnect timeout contract**

Run:

```text
python -m pytest -q tests/test_controller_reconnect.py
```

Expected GREEN: 断线后第二次 status 仍 `wait_ms=0`；如果无需修改测试文件，不产生无关 diff。

- [ ] **Step 11: Commit**

```text
git add src/agy_worker/server.py tests/test_server.py tests/test_controller_reconnect.py
git commit -m "perf: 去除 MCP 结果重复载荷"
```

如果 `tests/test_controller_reconnect.py` 无实际修改，不要把它加入 commit。

---

### Task 3: Version / public contract / migration docs

**Files:**
- Modify: `pyproject.toml`
- Modify: `tests/test_server.py`
- Modify: `README.md`
- Modify: `docs/实施设计.md`
- Review only: `schemas/agy_status.json`
- Review only: other `schemas/*.json`

**Interfaces:**
- Produces: package metadata `0.3.2`。
- Preserves: Controller protocol v2、6 个 MCP tools、StatusRequest input schema。

- [ ] **Step 1: 写 RED — package/server version 期望 0.3.2**

将现有：

```python
assert captured['version'] == implementation_version() == '0.3.1'
```

更新为：

```python
assert captured['version'] == implementation_version() == '0.3.2'
```

Run:

```text
python -m pytest -q tests/test_server.py::test_server_uses_package_metadata_version
```

Expected RED: 当前 package metadata 仍为 0.3.1。

- [ ] **Step 2: 将 `pyproject.toml` version 改为 0.3.2**

只改：

```toml
version = "0.3.2"
```

不修改依赖版本。

- [ ] **Step 3: 更新 README public contract**

README 必须明确写出：

1. `agy_status(after_revision=R)` 25 秒内没有更高 revision 时返回 `{task_id,status,revision,unchanged:true}`；
2. terminal status 默认只返回 summary、退出/计数、evidence/result artifact ID，不展开 diagnostics/manifest；
3. 需要错误正文时读 `errors`，需要上下文读 `operation-log`，需要完整任务 result 读 `result`；
4. “无 stdout 更新”不是 hang 判定；不要因为单次/多次 unchanged 自动 cancel；
5. 普通 MCP JSON 以 structuredContent 为 canonical，TextContent 只是短摘要，不再双份 JSON；
6. `agy_artifact_read` 是显式高 token 成本冷路径，应按需、按行读取。

- [ ] **Step 4: 更新 `docs/实施设计.md`**

新增 v0.3.2 小节，记录：

- hot/cold data split；
- compact public envelope；
- long-poll unchanged semantics；
- `PUBLIC_SUMMARY_MAX_BYTES=768`；
- byte budget 表；
- protocol v2 不升级的理由；
- real AGY token/字节验收要求。

不要把尚未执行的本地验收写成 PASS。

- [ ] **Step 5: 核对输入 schema 无意外变化**

因为 `StatusRequest` 和其他请求模型没有改变，`schemas/*.json` 预期无 diff。使用项目现有 schema 生成/校验入口重新生成；如果仓库当前没有独立生成命令，则对照 `models.py` 与已跟踪 schema 人工检查，并在 TASKS 记录“无模型变化，因此未生成 schema diff”，不得自造脚本。

- [ ] **Step 6: GREEN — version/server tests**

Run:

```text
python -m pytest -q tests/test_server.py
```

Expected GREEN: server version 与 package metadata 均为 0.3.2。

- [ ] **Step 7: Commit**

```text
git add pyproject.toml tests/test_server.py README.md docs/实施设计.md
git commit -m "docs: 发布 v0.3.2 紧凑结果合同"
```

只有 schema 实际发生合理、解释得通的输入合同变化时才 add `schemas/`；按本规格正常实现预期不应有 schema diff。

---

### Task 4: Final review, repository verification, real AGY acceptance, handoff

**Files:**
- Modify: `docs/planning/context-efficient-status-v032/TASKS.md`
- Modify: `docs/planning/context-efficient-status-v032/README.md`
- Optional create after implementation begins: `docs/planning/context-efficient-status-v032/LOCAL-ACCEPTANCE.md`，仅用于保存本地 AI 的最终一次性验收协议/证据；若创建，内容必须绑定精确 HEAD。

**Interfaces:**
- Consumes: Tasks 1–3 implementation HEAD。
- Produces: reviewable Draft PR、验证证据、明确的已验证/待本地验证状态。

- [ ] **Step 1: Specification review pass**

逐项对照 `SPEC.md`：

- duplicate MCP JSON removed；
- unchanged envelope；
- terminal compact result；
- artifact drill-down preserved；
- no stdout-based cancel；
- budgets；
- protocol/tool count/permission unchanged；
- no progress throttle scope creep。

任何偏离先修复，再进入 code-quality review。

- [ ] **Step 2: Code-quality review pass**

独立检查：

- renderer 是否纯函数式视图、是否意外 mutate persisted result；
- terminal 与 after_revision 优先级；
- WorkerError/error response；
- UTF-8 截断是否可能产生 invalid Unicode；
- artifact ID 是否只指向真实存在证据；
- TextContent-only 客户端兼容；
- image artifact behavior；
- idempotent submit/cancel 是否仍返回可用 task envelope；
- 是否有无关 refactor/权限变化。

- [ ] **Step 3: Full repository verification on Windows**

Run fresh:

```text
pwsh.exe -NoProfile -File scripts/check.ps1
```

然后：

```text
git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD
```

记录 exit code、pytest passed/failed/skipped/warnings 和精确 HEAD。没有执行时保持 `awaiting_acceptance`，不能写 PASS。

- [ ] **Step 4: Real AGY end-to-end payload acceptance**

本地 AI / 用户环境使用最终 branch HEAD，先确保安装的是 `0.3.2` 并显式 stop 旧 stale Controller，再启动新的 Bridge/Controller。通过实际 Codex→MCP→Controller→AGY 流程执行一个会产生至少 1 条 warning 的已登记 build/test。

必须记录至少以下原始事实：

```text
branch HEAD
package metadata version
Controller protocol_version / implementation_version
submit response UTF-8 bytes
每次 agy_status: after_revision / wait_ms / returned revision / status / UTF-8 bytes
至少一次 unchanged response 的完整 compact JSON
terminal status 的完整 compact JSON 与 UTF-8 bytes
terminal total_errors / total_warnings
result_artifact_id / diagnostics_artifact_id
读取 errors artifact 后 warning/error 正文仍存在的证据
Codex transcript 中是否仍出现同一完整 JSON 两份
任务实际最终 exit/status
```

验收门槛使用 SPEC §7 的 256/512/1536/2048/256-byte 限制。

- [ ] **Step 5: No-progress semantics probe**

在真实任务运行期间，若恰有 25 秒窗口没有 stdout/revision 增长，记录 returned `unchanged=true`。不得仅因 unchanged 自动取消；继续等待实际任务终态或用户明确取消。

如果目标构建天然持续输出，无法获得真实 25 秒 unchanged 窗口，记录 `not_observed`，不要伪造；Runtime 单元测试仍覆盖协议语义。

- [ ] **Step 6: receiving-code-review 本地证据复核**

ChatGPT 对本地 AI 的每条 PASS/FAIL 逐项核对：精确 HEAD、命令、exit code、返回 bytes、JSON shape、artifact 可追溯性。审查意见是证据，不未经判断直接照改。

- [ ] **Step 7: 更新 TASKS/README**

回填：

- 当前 branch HEAD；
- Tasks 1–4 状态；
- full check 证据；
- real AGY payload 证据；
- open findings；
- PR number/state；
- merge_authorized=false（除非用户在后续明确授权）。

- [ ] **Step 8: Final PR diff review**

确认 diff 只包含 SPEC §9 文件边界和 planning docs；如出现 Controller/Broker/Browser/security 无关修改，必须解释并移除或升级规格后重新审批。

- [ ] **Step 9: Commit acceptance records**

```text
git add docs/planning/context-efficient-status-v032
git commit -m "docs: 记录 v0.3.2 最终验收证据"
```

- [ ] **Step 10: Handoff, no merge**

Draft PR 保留供用户/本地 AI 审查。未经用户明确指令，不 merge `main`、不删除 branch、不启用 auto-merge。

---

## Plan Self-Review

### Spec coverage

- Root cause A: MCP dual JSON → Task 2。
- Root cause B: unchanged long-poll returns full record → Task 1。
- Root cause C: terminal hot/cold data mixing → Task 1 + Task 4 real payload acceptance。
- Evidence preservation → Task 1 artifact test + Task 4 real drill-down。
- Compatibility/version/docs → Tasks 2–3。
- No false hang semantics → Task 1 + Task 4 no-progress probe。
- Verification/local AI division → Task 4。

### Placeholder scan

本计划没有 `TBD`、`TODO` 或“稍后实现”占位步骤。progress throttling 被明确列为 v0.3.2 非目标，不是未完成任务。

### Type/name consistency

- Runtime public renderer：`_public_task(record, *, unchanged=False)`。
- Runtime result renderer：`_public_result(result)`。
- Runtime summary constant：`PUBLIC_SUMMARY_MAX_BYTES=768`。
- Server text renderer：`_compact_tool_text(tool_name, result)`。
- diagnostics pointer：`diagnostics_artifact_id="errors"`。
- canonical full pointer：`result_artifact_id="result"`。

以上名称在 SPEC / PLAN 中一致；实现时若必须调整名字，应同步更新 SPEC/PLAN/TASKS，而不是让文档和代码漂移。
