# Controller v0.3.1 Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. In ChatGPT Web, true subagents are unavailable, so use the Web Adapter: execute sequentially on the dedicated GitHub branch, perform separate specification-review and code-quality-review passes, and use the user's local AI for executable RED/GREEN verification.

**Goal:** 在不改变六个公开 MCP 工具名称、不开放新权限、不提高 AGY 并行度的前提下，把 v0.3 Controller/Bridge 架构加固为可升级、可停止、可诊断、可背压且可由本地 AI 严格验收的 v0.3.1 基线。

**Architecture:** 保留 `Codex → disposable stdio Bridge → persistent Controller → single Runtime → AGY`。新增 Controller 冻结身份（协议、配置摘要、实现摘要、实例 ID）、跨协议管理停止、可接管启动循环、custom-config Controller 所有权、重连预算控制和单槽背压。所有失效升级场景 fail-closed，不自动重放任务或静默强停后台 Controller。

**Tech Stack:** Python 3.13–3.14、official MCP Python SDK 2.2.0、Pydantic 2.13.5、stdlib HTTP/SQLite/threading/concurrent.futures、pywin32 312、PowerShell 7、pytest 9.1.1、Windows 10 x64。

**Spec:** `docs/planning/controller-hardening-v031/SPEC.md`

## Global Constraints

- Base commit 固定记录为 `904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066`；执行前若 `main` 前进，只比较新提交，不回退 Base。
- 开发分支：`fix/controller-hardening-v031`；不得直接修改 `main`。
- 六个公开工具名保持：`agy_capabilities`、`agy_worker`、`agy_continue`、`agy_status`、`agy_cancel`、`agy_artifact_read`。
- `runtime.lock` 保留；Controller 仍是唯一 Runtime owner。
- `max_concurrent_tasks` 保持 `1`；本计划只增加 inflight 上限，不增加 AGY 并行。
- Controller 重启后非终态任务仍变为 `interrupted`，不得自动重做。
- `code_write`、任意 `shell`、Android 操作继续关闭；`os_isolation` 继续为 false。
- 当前安全边界仍是 hook + private Broker；不得把 ACL advisory 描述成安全沙箱。
- 不新增数据库 migration，不删除历史任务和 artifact。
- 注释和维护文档使用简体中文；PowerShell 使用 `pwsh.exe`。
- 每个行为变更必须先提交能捕获该 break 的测试。ChatGPT Web 无本地 test runner：生产代码实现前必须由本地 AI 在对应测试提交上执行 RED；实现后再执行 GREEN。
- 本地 AI 的执行结果是审查证据，不自动等于正确结论；收到反馈后按 receiving-code-review 技术复核。
- 未经用户授权，不合并 `main`、不删除分支、不自动合并。

---

## File Map

### 新建

- `src/agy_worker/controller_state.py`：Controller state 模型、loopback endpoint 校验、配置/实现摘要、package version 单一来源。
- `src/agy_worker/security.py`：Windows data_dir ACL 诊断，只产 advisory。
- `tests/test_controller_security.py`：endpoint/state/ACL 的行为测试。
- `tests/test_run_task.py`：custom config Controller ownership 与清理测试。
- `docs/planning/controller-hardening-v031/LOCAL-ACCEPTANCE.md`：本地 AI 最终验收协议。

### 修改

- `src/agy_worker/controller_protocol.py`：协议号升级到 2；只保留共享协议常量。
- `src/agy_worker/controller.py`：冻结 Controller identity，发布 v2 state，将身份传入 Runtime。
- `src/agy_worker/controller_client.py`：严格 state/health 校验、跨协议 stop、启动锁接管、启动 ownership、重连参数调整。
- `src/agy_worker/runtime.py`：health identity、stop 语义、inflight 背压、queued Future 取消、capabilities。
- `src/agy_worker/server.py`：MCP 版本单一来源、request_id 说明、status 重连预算配合。
- `src/agy_worker/manage.py`：`stop --config`、tool timeout 60、doctor ACL advisory。
- `scripts/stop.ps1`：可选 `-Config`。
- `scripts/run-task.py`：显式 custom config 默认 ephemeral owner cleanup、`--keep-controller`。
- `scripts/verify-controller.py`：fresh/stop-after 自包含生命周期验收。
- `tests/test_controller.py`：Controller 身份、停止、接管、重连、backpressure 回归。
- `pyproject.toml`：版本 0.3.1、正式声明 jsonschema。
- `README.md`、`docs/实施设计.md`、`docs/部署验收.md`：同步真实行为与边界。

---

### Task 1: 建立 Controller v2 身份与 stale 检测

**Files:**
- Create: `src/agy_worker/controller_state.py`
- Modify: `src/agy_worker/controller_protocol.py`
- Modify: `src/agy_worker/controller.py`
- Modify: `src/agy_worker/runtime.py`
- Modify: `src/agy_worker/controller_client.py`
- Modify: `pyproject.toml`
- Test: `tests/test_controller.py`
- Test: `tests/test_controller_security.py`

**Interfaces:**
- Produces: `ControllerState`, `LegacyControllerState`, `config_sha256(path)`, `controller_implementation_sha256()`, `implementation_version()`, `validate_controller_endpoint(url)`。
- Produces errors: `controller_stale_config`、`controller_stale_implementation`、`protocol_mismatch`、`controller_state_invalid`。
- Consumed by Tasks 2–5, 7–9。

- [ ] **Step 1: 先写 endpoint / state 失败测试**

新增行为测试，至少包含：

```python
def test_controller_state_rejects_non_loopback_endpoint(tmp_path):
    state = valid_state(endpoint="http://example.com:9000")
    write_state(tmp_path, state)
    with pytest.raises(WorkerError, match="127.0.0.1"):
        ControllerClient(config_for(tmp_path), autostart=False)
```

以及 `localhost`、`0.0.0.0`、带 userinfo、query、fragment、缺 port 的表驱动用例。断言目标是“客户端在发网络请求之前拒绝 state”，不要 grep 源码文本。

- [ ] **Step 2: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py
```

Expected: 新测试 FAIL，原因是当前客户端没有严格 state 模型 / endpoint 校验，而不是测试语法错误。

- [ ] **Step 3: 写 config / implementation stale 失败测试**

测试使用真实 `ControllerService` + temp config：

```python
def test_config_change_rejects_running_controller(tmp_path):
    config = make_config(tmp_path)
    service = ControllerService(config)
    try:
        client = ControllerClient(config, autostart=False)
        rewrite_same_config_with_changed_enabled_kinds(config)
        with pytest.raises(WorkerError) as caught:
            ControllerClient(config, autostart=False)
        assert caught.value.code == "controller_stale_config"
    finally:
        service.close()
```

实现摘要测试通过 monkeypatch `controller_state.controller_implementation_sha256` 在 Bridge 侧返回另一个 64 hex 摘要，断言 `controller_stale_implementation`。不要断言私有字段文本；断言公开错误码。

- [ ] **Step 4: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "stale or identity"
```

Expected: FAIL，因为 v0.3 health 只有 protocol/pid，没有配置/实现身份。

- [ ] **Step 5: 实现 `controller_state.py`**

实现精确接口：

```python
PACKAGE_NAME = "elio-agy-worker"
CONTROLLER_IMPLEMENTATION_FILES = (
    "controller.py", "controller_protocol.py", "runtime.py", "common.py",
    "models.py", "artifacts.py", "logs.py", "processes.py", "browser.py",
)

class LegacyControllerState(BaseModel):
    model_config = ConfigDict(extra="allow")
    protocol_version: int = Field(ge=1)
    pid: int = Field(gt=0)
    endpoint: str
    token: str = Field(min_length=32)
    config_path: str
    started_at: str

class ControllerState(LegacyControllerState):
    model_config = ConfigDict(extra="forbid")
    implementation_version: str
    implementation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    instance_id: str = Field(pattern=r"^[0-9a-f]{32}$")
```

`validate_controller_endpoint()` 使用 `urllib.parse.urlsplit`，严格只接受 `http://127.0.0.1:<1..65535>`，并拒绝额外 URL 成分。

`config_sha256()` 哈希文件原始 bytes。`controller_implementation_sha256()` 对固定相对路径排序，用“路径 UTF-8 + `\0` + bytes + `\0`”喂给 SHA-256。`implementation_version()` 用 `importlib.metadata.version(PACKAGE_NAME)`。

- [ ] **Step 6: 升级协议与冻结 Controller identity**

`controller_protocol.py`：

```python
PROTOCOL_VERSION = 2
CONTROLLER_STATE_FILE = "controller.json"
CONTROLLER_LAUNCH_LOCK = "controller-launch.lock"
```

`ControllerService.__init__` 在构造 Runtime 前生成：

```python
identity = {
    "protocol_version": PROTOCOL_VERSION,
    "implementation_version": implementation_version(),
    "implementation_sha256": controller_implementation_sha256(),
    "config_sha256": config_sha256(self.config_path),
    "instance_id": uuid.uuid4().hex,
}
```

Runtime 接收该冻结 identity；state 发布同一份值。health 从 Runtime 的冻结 identity 返回，不在请求时重新读取代码/配置。

- [ ] **Step 7: Bridge 严格比较 state / health / 当前磁盘**

`ControllerClient` 普通路径只接受 `ControllerState`。验证顺序按 SPEC 第 6 节执行。配置 hash 或实现 hash不同分别抛明确 WorkerError；不自动 stop。

- [ ] **Step 8: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "identity or stale or two_stdio"
```

Expected: PASS。

- [ ] **Step 9: 独立规格复核 + 代码质量复核**

规格复核重点：没有改变六个公开工具，没有自动重启 stale Controller。代码复核重点：hash 算法单一来源、endpoint 在任何请求前校验、state/health 同一实例。

- [ ] **Step 10: Commit**

Commit message:

```text
fix: 增加Controller身份与失效检测
```

---

### Task 2: 实现跨协议显式停止与 `--config` 停止

**Files:**
- Modify: `src/agy_worker/controller_client.py`
- Modify: `src/agy_worker/runtime.py`
- Modify: `src/agy_worker/manage.py`
- Modify: `scripts/stop.ps1`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: `LegacyControllerState`, `ControllerState.instance_id`。
- Produces: `ControllerClient.stop_existing(config_path, timeout=10)`；`manage stop --config PATH`；`stop.ps1 -Config PATH`。

- [ ] **Step 1: 写跨协议停止 RED 测试**

构造真实 Controller，然后让“Bridge 当前协议”与 state 协议不同。测试必须断言管理停止仍能成功，而普通 `ControllerClient(..., autostart=False)` 仍因 `protocol_mismatch` 拒绝业务使用。

```python
def test_management_stop_can_stop_older_protocol_controller(...):
    # 普通 client: protocol_mismatch
    # stop_existing: 返回 stopping/stopped，最终 state 消失
```

- [ ] **Step 2: 写 custom config stop RED 测试**

通过 `manage.main` 可测试的 parser/helper 验证：传入 `--config <temp/runtime.toml>` 时只停止该 data_dir Controller，不读取正式配置。

- [ ] **Step 3: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "stop or protocol"
```

Expected: FAIL；当前 `autostart=False` 会在 stop 前被协议健康检查挡住，且 manage stop 不接受 config。

- [ ] **Step 4: 实现 legacy-aware stop**

`stop_existing()` 直接读取 legacy state、校验 config path 与 loopback endpoint、使用 state token。对 legacy v1 发送：

```json
{"protocol_version": 1}
```

新 v2 `/control/stop` 改为“Bearer 鉴权成功即可请求停止”，不再与 `/control/call` 共用严格当前协议 gate。业务 `/control/call` 仍必须严格匹配 v2。

- [ ] **Step 5: 停止等待真实终态**

`stop_existing()` 保存目标 instance identity，poll 到以下任一条件：

- 原 state 删除；
- 原 instance health 不可达；
- state 已替换为另一个 instance（此时视为原目标已退出，不向新实例再次发送 stop）。

超时返回 `controller_stop_timeout`，不能把只收到 `"stopping"` 当成完全停止。

- [ ] **Step 6: 扩展管理 CLI / PowerShell**

`manage.py` parser 改为 subcommand-aware，`stop` 接受可选 `--config`；其他命令仍保持原行为。`scripts/stop.ps1`：

```powershell
param([string]$Config)
$arguments = @('-m','agy_worker.manage','stop')
if ($Config) { $arguments += @('--config', $Config) }
& (Join-Path $workerRoot '.venv/Scripts/python.exe') @arguments
```

- [ ] **Step 7: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "stop or protocol"
```

Expected: PASS。

- [ ] **Step 8: Review + Commit**

重点复核“跨协议 stop 只能扩大停止兼容性，不能扩大 `/control/call` 业务兼容性”。

Commit:

```text
fix: 支持跨协议和指定配置停止Controller
```

---

### Task 3: 让启动锁支持 owner 失败后的接管与重试

**Files:**
- Modify: `src/agy_worker/controller_client.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Consumes: Task 1 healthy identity。
- Produces: deadline-driven `_ensure()`；诊断字段 `last_launch_pid`；稳定的 launch cooldown。

- [ ] **Step 1: 写 lock owner 崩溃 RED 测试**

测试两个 client：第一个持有 launch lock 但不发布 Controller，然后释放/退出；第二个起初获取失败，必须在 deadline 内重新获取并启动，而不是等满 15 秒失败。

测试应使用真实文件锁与 temp data_dir，只 mock WMI/进程创建这一外部慢边界。

- [ ] **Step 2: 写 stopping/runtime_busy RED 测试**

让第一次 `_launch()` 不产生 healthy state（模拟旧 Runtime 尚持锁导致子进程失败），第二次 launch 后发布真实 Controller state。断言 `_ensure()` 在同一 deadline 内成功，而不是只 launch 一次。

- [ ] **Step 3: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "takeover or launch_retry"
```

Expected: FAIL，证明当前单次抢锁 / 单次 launch 行为被测试捕获。

- [ ] **Step 4: 改写 `_ensure()` 为循环接管**

核心形状：

```python
deadline = time.monotonic() + startup_timeout
next_launch_at = 0.0
while time.monotonic() < deadline:
    state = self._read_current_state()
    if self._healthy_current(state):
        return state
    with self._try_launch_lock() as acquired:
        if acquired:
            state = self._read_current_state()
            if self._healthy_current(state):
                return state
            if time.monotonic() >= next_launch_at:
                self.last_launch_pid = self._launch()
                next_launch_at = time.monotonic() + 0.5
    time.sleep(0.1)
```

不要在等待期间一直持有 launch lock；每次 launch 前 double-check health。

- [ ] **Step 5: WMI 返回创建 PID**

PowerShell WMI 脚本将 `ProcessId` 写到 stdout JSON 或单行数字；Python 解析并返回 PID。PID 只用于 ownership/诊断，不替代 health。

- [ ] **Step 6: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "simultaneous or takeover or launch_retry"
```

Expected: PASS；原“两个客户端只产生一个 Controller”测试也必须继续通过。

- [ ] **Step 7: Review + Commit**

Commit:

```text
fix: 支持Controller启动锁接管与重试
```

---

### Task 4: 修复 custom `run-task --config` 遗留常驻 Controller

**Files:**
- Modify: `src/agy_worker/controller_client.py`
- Modify: `scripts/run-task.py`
- Create: `tests/test_run_task.py`

**Interfaces:**
- Produces: `ControllerClient.started_controller: bool`、`started_instance_id: str | None`。
- Produces CLI: `scripts/run-task.py ... --config PATH [--keep-controller]`。

- [ ] **Step 1: 写 owned custom Controller cleanup RED 测试**

用 temp config/data_dir 和一个不需要真实 AGY 的失败前置请求，或把 stdio client 外部边界替换为可控 fake；测试必须观察真实 `controller.json` 生命周期，而不是断言 mock 被调用。

行为：显式 `--config` 启动脚本之前没有 Controller；脚本退出后，它启动的 instance state 消失。

- [ ] **Step 2: 写 pre-existing preservation RED 测试**

预先启动 `ControllerService(config)`，再运行 custom run-task；脚本结束后原 `instance_id` 仍 healthy。

- [ ] **Step 3: 写 `--keep-controller` RED 测试**

显式 `--config --keep-controller` 且本次确实启动 Controller，脚本结束后同一 instance 仍 healthy，测试结束时用管理 stop 清理。

- [ ] **Step 4: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_run_task.py
```

Expected: FAIL；当前 run-task 没有 ownership/cleanup。

- [ ] **Step 5: 实现启动 ownership**

`ControllerClient` 只有在自己 `_launch()` 得到 PID，且随后 healthy state 的 `pid`（v2 再加 instance identity）对应本次启动结果时，设置：

```python
self.started_controller = True
self.started_instance_id = state["instance_id"]
```

只是等待另一个 Bridge 启动成功时保持 false。

- [ ] **Step 6: run-task 生命周期**

未传 `--config`：保持正式 Controller 常驻。

显式 `--config`：在进入 MCP stdio Bridge 前建立 ownership-aware client；`finally` 中若 `started_controller` 且没有 `--keep-controller`，调用 `stop_existing(..., expected_instance_id=...)`。任何异常路径都走 finally。

- [ ] **Step 7: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_run_task.py
```

Expected: PASS，且测试 cleanup 后 temp data_dir 没有存活 Controller state。

- [ ] **Step 8: Review + Commit**

Commit:

```text
fix: 清理run-task临时Controller生命周期
```

---

### Task 5: 收敛重连与 MCP timeout 预算

**Files:**
- Modify: `src/agy_worker/controller_client.py`
- Modify: `src/agy_worker/manage.py`
- Modify: `src/agy_worker/server.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- `status` 重连第二次参数强制 `wait_ms=0`。
- Codex MCP `tool_timeout_sec=60`。

- [ ] **Step 1: 写 status reconnect RED 测试**

建立可控 HTTP boundary：第一次 request 抛 `controller_unavailable`，`_ensure()` 返回可用 state，第二次 request 捕获 payload。断言：

```python
assert first_payload["params"]["wait_ms"] == 25000
assert second_payload["params"]["wait_ms"] == 0
assert second_payload["params"]["task_id"] == "task-1"
assert second_payload["params"]["after_revision"] == 7
```

同时确认 submit/continue 重连不改变 request_id。

- [ ] **Step 2: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "reconnect"
```

Expected: FAIL；当前第二次 status 原样重复 long-poll。

- [ ] **Step 3: 实现 retry 参数规则**

仅当第一轮失败码是 `controller_unavailable` 时 `_ensure()` 一次。`method == "status"` 时复制 params 并把 `wait_ms=0`；其他方法保持参数。

- [ ] **Step 4: MCP tool timeout 调到 60**

`manage.register()` 设置：

```python
"startup_timeout_sec": 20,
"tool_timeout_sec": 60,
```

`server.py` 对 Controller status 单次 HTTP timeout 仍可维持 30，因为第二次不再 long-poll；不要把内层 timeout 无限制扩大。

- [ ] **Step 5: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller.py -k "reconnect"
```

Expected: PASS。

- [ ] **Step 6: Review + Commit**

Commit:

```text
fix: 收敛Controller重连等待预算
```

---

### Task 6: 为单执行槽增加 inflight 背压和 queued 立即取消

**Files:**
- Modify: `src/agy_worker/runtime.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_controller.py`

**Interfaces:**
- Produces constant: `MAX_CONCURRENT_TASKS = 1`、`MAX_INFLIGHT_TASKS = 16`。
- Capabilities: `controller.max_concurrent_tasks=1`、`controller.max_inflight_tasks=16`。
- New error: `worker_busy`。

- [ ] **Step 1: 写第 17 个新请求被拒 RED 测试**

使用现有 runtime fixture，保持 executor 不真正执行；提交 16 个不同 request_id 后，第 17 个断言：

```python
with pytest.raises(WorkerError) as caught:
    runtime.submit(request(request_id="req-17"))
assert caught.value.code == "worker_busy"
```

同时断言 data/tasks 不多出第 17 个目录。

- [ ] **Step 2: 写幂等重试不受背压 RED 测试**

填满 16 个 inflight 后，再提交与第 1 个完全相同的 request_id + fingerprint，必须返回第 1 个 task_id，不得 `worker_busy`。

- [ ] **Step 3: 写 queued cancel 立即终态 RED 测试**

占住唯一执行槽，让第二任务保持 queued；调用 cancel 后，不释放第一任务也应在短时间内看到第二任务 `cancelled` 且已从 active 移除。

- [ ] **Step 4: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_runtime.py -k "inflight or queued_cancel or worker_busy"
```

Expected: FAIL；当前无 inflight 上限且 Future 未保存。

- [ ] **Step 5: 实现常量、容量 gate 与 Future 保存**

`submit()` 必须保持顺序：

```text
request_id idempotency lookup
→ request/workspace/permission validation
→ inflight capacity check（仍在创建 session/task 之前）
→ create session/task/context
→ future = pool.submit(...)
→ context["future"] = future
```

为避免 executor 极快启动导致 context race，先把 context 放入 active，再 submit；保存 future 时用 runtime lock。

- [ ] **Step 6: 实现 queued cancel**

如果 `context["future"].cancel()` 返回 true：立即把 record 设为 `cancelled`，保存 audit/state，active pop。若返回 false，沿用 running `cancel_event` 路径。

不要复用 `_run()` finally 来完成从未执行的 Future，因为它不会被调用。

- [ ] **Step 7: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_runtime.py
```

Expected: PASS，原幂等、权限、worktree、snapshot 等测试全部保持通过。

- [ ] **Step 8: Review + Commit**

Commit:

```text
fix: 限制任务积压并支持排队任务立即取消
```

---

### Task 7: 增加 Controller data_dir ACL advisory

**Files:**
- Create: `src/agy_worker/security.py`
- Modify: `src/agy_worker/manage.py`
- Modify: `src/agy_worker/runtime.py`
- Test: `tests/test_controller_security.py`

**Interfaces:**
- Produces: `inspect_data_dir_acl(path) -> dict`。
- Report keys: `checked`、`broad_read_principals`、`token_confidentiality_advisory`，失败时附 `error`。

- [ ] **Step 1: 写纯分类逻辑测试**

将 ACL SID/名称分类拆成纯 helper，手工 fixture 包含：当前用户、SYSTEM、Administrators、Everyone、BUILTIN\\Users、Authenticated Users。断言只有宽泛读取主体进入 `broad_read_principals`。

- [ ] **Step 2: 写 ACL API 失败测试**

只 mock Windows ACL 读取这一 OS 边界，抛异常时断言：

```python
{
  "checked": False,
  "broad_read_principals": [],
  "token_confidentiality_advisory": False,
  "error": "..."
}
```

不得把未知状态当安全。

- [ ] **Step 3: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py -k "acl"
```

Expected: FAIL，因为 security helper 尚不存在。

- [ ] **Step 4: 实现诊断，不自动改 ACL**

使用 pywin32 安全描述符读取 data_dir DACL，识别明显 grant-read/generic-read/generic-all 对宽泛主体的 ACE。该算法是 advisory，不做完整 Windows effective-access 证明。

- [ ] **Step 5: 接入 doctor 与 capabilities**

`doctor()` 将 advisory 写入 `work/doctor.json`。`Runtime.capabilities()` 也可返回当前 data_dir advisory，但不得让 ACL API 失败阻止 capabilities；失败只显示 `checked=false`。

- [ ] **Step 6: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_controller_security.py
pwsh.exe -NoProfile -File scripts/doctor.ps1
```

Expected: pytest PASS；doctor 明确打印实际 advisory。doctor 是否整体成功仍按现有 AGY/browser 必需条件决定，ACL advisory 不单独把系统描述成 sandbox。

- [ ] **Step 7: Review + Commit**

Commit:

```text
security: 增加Controller凭据目录ACL诊断
```

---

### Task 8: 收敛版本、依赖、request_id 和维护者清洗文档

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/agy_worker/server.py`
- Modify: `src/agy_worker/manage.py`
- Modify: `README.md`
- Modify: `docs/实施设计.md`
- Modify: `docs/部署验收.md`
- Modify: examples containing human-style request IDs when relevant
- Test: `tests/test_server.py`

**Interfaces:**
- Package version: `0.3.1`。
- Runtime dependency: `jsonschema==4.26.0`。
- Server version source: `implementation_version()`。

- [ ] **Step 1: 写 server version 行为测试**

通过初始化 MCP Server 或可注入 helper，断言公开 server version 等于 package metadata helper，而不是检查源码字符串。若当前测试结构不便直接观察 Server，可把 server 构造提取为 `build_server(client)` 并测试初始化返回。

- [ ] **Step 2: 本地 AI 执行 RED**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_server.py
```

Expected: 新版本一致性测试在硬编码 v0.3.0 下失败。

- [ ] **Step 3: 更新 package metadata**

`pyproject.toml`：

```toml
version = "0.3.1"
dependencies = [
  "mcp==2.2.0",
  "pydantic==2.13.5",
  "pywin32==312",
  "tomlkit==0.15.1",
  "jsonschema==4.26.0",
]
```

`requirements.lock` 已含同版本 jsonschema；除非本地验证发现 lock 与 metadata 不一致，不做额外升级。

- [ ] **Step 4: Server version 单一来源**

`Server(... version=implementation_version())`。

- [ ] **Step 5: 更新 request_id 合同**

工具描述、README、示例明确：新逻辑请求推荐 `req-<uuid4hex>`，全 data_dir 历史唯一；只在同一个逻辑请求的 transport/reconnect 重试中复用。不要改变数据库 schema。

- [ ] **Step 6: 把“辅助清洗模式”改成“维护者辅助清洗流程”**

文档明确它不是 Runtime-enforced analysis mode，本次不增加公开 schema 字段。保留 Codex 回看原始证据再作判断的边界。

- [ ] **Step 7: 更新 v0.3.1 真实状态文档**

同步：protocol v2、state identity、cross-version stop、custom config lifecycle、backpressure、ACL advisory、status retry、仍未启用的安全能力。

`docs/部署验收.md` 只记录“待本地 AI 验收”或之后实际收到的证据，绝不预写“测试通过”。

- [ ] **Step 8: 本地 AI 执行 GREEN**

Run:

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_server.py
```

Expected: PASS。

- [ ] **Step 9: Review + Commit**

Commit:

```text
docs: 同步v0.3.1接口与维护边界
```

如果 package/code 与 docs 改动较大，可按实际变化拆成 `fix:` / `docs:` 两个原子提交，不制造空 commit。

---

### Task 9: 让 Controller 验收脚本自包含并完成全量验证

**Files:**
- Modify: `scripts/verify-controller.py`
- Modify: `docs/planning/controller-hardening-v031/LOCAL-ACCEPTANCE.md`
- Modify: `docs/planning/controller-hardening-v031/TASKS.md`
- Test: existing full suite

**Interfaces:**
- CLI: `verify-controller.py --config PATH [--fresh] [--stop-after]`。

- [ ] **Step 1: 扩展 verify-controller 生命周期模式**

`--fresh`：先用 `stop_existing(config)` 停止已有目标 Controller并确认消失，再启动两个 Bridge；记录新 `instance_id/pid`。

`--stop-after`：验收完成后停止本次观察到的同一 instance；如果已被替换，不误停替代实例。

输出至少：

```json
{
  "first_server_version": "0.3.1",
  "second_server_version": "0.3.1",
  "tool_count": 6,
  "controller_pid": 12345,
  "controller_instance_id": "...",
  "controller_protocol": 2,
  "controller_alive_after_bridges": true,
  "max_concurrent_tasks": 1,
  "max_inflight_tasks": 16,
  "stopped_after_verification": true
}
```

- [ ] **Step 2: 计划自审**

按 writing-plans / plan reviewer 标准检查：

- SPEC 每个目标都有 Task；
- 无 `TBD` / `TODO` / “类似上面”占位；
- `ControllerState`、错误码、CLI 参数在各任务命名一致；
- 每个行为任务都有能捕获具体 break 的测试；
- 没有为了 v0.3.1 顺带开放权限、并行或自动重放。

- [ ] **Step 3: 本地 AI 运行权威全量检查**

Run:

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
```

Expected: compileall 成功，pytest 全量 0 failed。实际测试数以运行结果为准，不在计划预填数字。

- [ ] **Step 4: 本地 AI 运行 fresh 双 Bridge lifecycle**

使用 `LOCAL-ACCEPTANCE.md` 指定的独立 acceptance config/data_dir，避免无意停止正式正在工作的 Controller：

```powershell
& ./.venv/Scripts/python.exe scripts/verify-controller.py --config <acceptance-config> --fresh --stop-after
```

Expected: 两个 Bridge 同时看到 6 tools；退出后同一 Controller instance 仍活；脚本末尾能停止该 instance；acceptance data_dir 不遗留 healthy Controller。

- [ ] **Step 5: 本地 AI 检查 custom run-task 无泄漏**

按 `LOCAL-ACCEPTANCE.md` 执行 custom config 场景并报告任务前/后的 state、PID/instance 与命令输出。

- [ ] **Step 6: Git/diff 验证**

本地 AI：

```powershell
git status --short
git diff --check origin/main...HEAD
```

ChatGPT Web：使用 GitHub compare 再独立检查 changed files、意外范围和文档一致性。

- [ ] **Step 7: 独立规格审查 pass**

逐条对照 `SPEC.md` 验收标准，区分：代码存在、测试存在、本地实际执行通过、尚未执行。

- [ ] **Step 8: 独立代码质量审查 pass**

重点审查：

- state 文件被篡改是否能造成外联；
- stop 是否可能误停 replacement instance；
- launch retry 是否可能产生 WMI process storm；
- Future/active/SQLite 锁顺序是否可能死锁；
- status reconnect 是否仍可能超出 MCP timeout；
- ACL advisory 是否被误表达为安全证明；
- custom run-task 的所有异常路径是否 cleanup。

- [ ] **Step 9: 处理本地 AI 反馈**

每条反馈先复现/读证据，再决定接受、修正或拒绝。若需要修代码，新增能复现问题的失败测试，重新走 RED→GREEN。

- [ ] **Step 10: 最终文档证据更新**

只把真正执行过的命令、结果、Windows PID/instance、失败与限制写入 `docs/部署验收.md` 和 `TASKS.md`。

- [ ] **Step 11: Draft PR 交付**

在所有已知 blocking findings 关闭、本地验收证据齐全后创建 Draft PR：

```text
fix: 加固AGY Worker Controller生命周期
```

PR 保持 Draft；用户决定是否 Ready / merge。

---

## Planned Commit Sequence

按实际完成范围使用以下原子提交，允许因实现边界调整而合并/拆分，但不制造空提交：

```text
fix: 增加Controller身份与失效检测
fix: 支持跨协议和指定配置停止Controller
fix: 支持Controller启动锁接管与重试
fix: 清理run-task临时Controller生命周期
fix: 收敛Controller重连等待预算
fix: 限制任务积压并支持排队任务立即取消
security: 增加Controller凭据目录ACL诊断
docs: 同步v0.3.1接口与维护边界
test: 完善Controller生命周期验收
```

## Execution Gate

本 `PLAN.md` 与 `SPEC.md` 仅完成设计和实施规划，不代表生产代码已经修改或问题已经修复。

**进入 Task 1 生产代码前需要用户确认本规格/计划。** 确认后由 ChatGPT 在本分支实施；本地 AI 按 `LOCAL-ACCEPTANCE.md` 提供 RED/GREEN 与最终 Windows 验收证据。
