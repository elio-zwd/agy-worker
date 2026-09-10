# AGY Worker Controller v0.3.1 加固规格

> 状态：**已批准；实现完成后等待最终 Windows 验收**
> 规划分支：`fix/controller-hardening-v031`
> Base：`904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066` (`main`)
> 日期：2026-09-09；2026-09-10 根据真实 Windows remediation 证据同步生命周期细节

## 1. 背景

v0.3 已完成核心架构拆分：

```text
Codex
  ↓
一次性 stdio Bridge（可多个）
  ↓
常驻 Controller（唯一 Runtime）
  ↓
AGY CLI
  ↓
私有 Broker / 受控执行器
```

该结构解决了多个 Codex 对话各自启动 stdio MCP 时争抢 `runtime.lock`、导致第二个 MCP 在握手前退出的问题。现阶段不重做这条架构，而是针对 v0.3 审查中发现的生命周期、升级、诊断、安全与并发边界进行加固。

当前事实以本规格 Base SHA 的仓库内容为设计起点；当前执行状态以同目录 `TASKS.md` 为准。`docs/部署验收.md` 中的历史本机通过记录只作为历史证据，不等同于本分支修改后的最终验证结果。

## 2. 目标

将 v0.3 收敛为可长期维护的 v0.3.1 Controller 基线，满足：

1. Bridge 不会把“旧代码 / 旧配置但仍存活”的 Controller 当成当前实例继续使用；
2. 即使 Bridge 与旧 Controller 协议版本不同，也有可靠的显式停止路径；
3. `scripts/run-task.py --config <独立配置>` 默认不会遗留隐藏常驻 Controller；
4. 启动锁拥有者异常退出后，其他 Bridge 能接管启动；旧 Controller 正在退出时也能最终拉起新实例；
5. Controller 元数据只能指向严格的本机 loopback HTTP endpoint，并对承载 Bearer 凭据的数据目录提供 ACL 风险诊断；
6. `agy_status` 在 Controller 断线重连后不会重复执行最长 25 秒 long-poll，从而降低超过外层 MCP tool timeout 的风险；
7. 单 AGY 执行槽保持不变，但待执行任务数量有硬上限，排队任务可立即取消；
8. `request_id` 的全局幂等语义、维护者辅助清洗的真实边界、包依赖与版本来源在代码和文档中一致；
9. 所有变更均有行为级回归测试，并由本地 AI 在 Windows 环境执行最终验收。

## 3. 不在本次范围

本次**不做**以下事情：

- 不开放 `code_write`；
- 不开放任意 `shell`；
- 不启用 Android / ADB 操作；
- 不新增 Windows 系统级安全沙箱；
- 不把 AGY 并行度从 1 提高到大于 1；
- 不切换为远程 / Streamable HTTP MCP；
- 不引入 Windows Service、计划任务或常驻 GUI；
- 不在 Controller 重启后自动重做 `queued/running` 任务；
- 不把“维护者辅助清洗”包装成一个尚未有代码级约束的正式 Runtime mode；
- 不迁移或清理历史任务数据库和 artifact；
- 不做与本目标无关的全库重构、格式化或依赖升级。

## 4. 设计原则

### 4.1 单一权威控制面不变

`Runtime` 继续只存在于唯一 Controller 内。`runtime.lock` 保留。Bridge 永不拥有 SQLite、任务状态、执行池、任务 token、AGY 子进程或 artifact 生命周期。

### 4.2 失效实例 fail-closed，不自动强停

新 Bridge 发现已运行 Controller 与当前配置或当前 Controller 实现不一致时：

- 不继续向旧 Controller 提交新任务；
- 不偷偷停止旧 Controller；
- 不自动重放旧任务；
- 返回明确错误，要求维护者使用显式停止入口；
- 停止完成后下一次 Bridge 调用再拉起当前版本。

这样避免为了“自动升级”而中断正在运行的 build / browser / 外部宿主操作。

### 4.3 管理停止与普通业务调用解耦

普通 Bridge 调用必须严格匹配当前 `PROTOCOL_VERSION`、当前配置摘要和当前 Controller 实现摘要。

显式停止属于管理操作。它必须能够读取旧 `controller.json` 的最小连接信息并尝试停止旧协议实例，不能先通过“当前协议兼容性检查”把自己挡住。

### 4.4 所有并发问题按状态机设计

Controller 启动、停止、重连、启动锁接管、排队取消都必须以可观察状态为依据，不使用固定 sleep 作为成功判定。允许短退避，但最终条件必须是 health / state / lock / Future 的真实变化。

## 5. Controller 身份与状态契约

### 5.1 新状态字段

v0.3.1 的 `controller.json` 在现有字段基础上增加：

```json
{
  "protocol_version": 2,
  "implementation_version": "0.3.1",
  "implementation_sha256": "<64 hex>",
  "config_sha256": "<64 hex>",
  "instance_id": "<uuid hex>",
  "pid": 12345,
  "endpoint": "http://127.0.0.1:54321",
  "token": "<random bearer token>",
  "config_path": "D:\\...\\runtime.toml",
  "started_at": "<UTC ISO-8601>"
}
```

本次协议号从 `1` 升为 `2`，因为 Controller state / health 身份契约发生了不兼容扩展。

### 5.2 `config_sha256`

Controller 启动前读取实际 `config_path` 原始字节并计算 SHA-256。Bridge 对同一路径重新计算当前摘要。

如果 health 身份与 Bridge 当前配置摘要不同，返回：

```text
controller_stale_config
```

错误信息必须说明：当前后台 Controller 仍使用旧配置；先显式停止，再重试。

### 5.3 `implementation_version` 与 `implementation_sha256`

`implementation_version` 统一取已安装包 `elio-agy-worker` 的 metadata version，不再在 `server.py` 另写一份版本字符串。

`implementation_sha256` 对**常驻 Controller 进程实际会加载且其行为会跨 Bridge 生命周期持续存在的 Worker Python 模块**做稳定摘要。最小集合：

```text
controller.py
controller_protocol.py
runtime.py
common.py
models.py
artifacts.py
logs.py
processes.py
browser.py
```

实现使用相对路径排序后依次哈希：相对路径 UTF-8、NUL 分隔、文件原始字节。Bridge 与 Controller 使用同一个 helper，避免两套算法漂移。

如果摘要不同，返回：

```text
controller_stale_implementation
```

`server.py` / `controller_client.py` 属于一次性 Bridge 一侧，不纳入常驻实现摘要；它们本身每次由 Codex 新启动。

### 5.4 `instance_id`

每个 Controller 启动时创建新的 `uuid.uuid4().hex`。停止等待、custom-config 所有权与防止误停替代实例都使用 `instance_id`，不能只靠 PID。

### 5.5 状态解析

新增明确的 Pydantic 状态模型：

- `LegacyControllerState`：读取管理停止所需的 v1 最小字段；允许新字段存在；
- `ControllerState`：当前 v2 严格字段；拒绝缺失、类型错误和未知字段。

普通 Bridge 只接受 `ControllerState`。管理停止可以接受 `LegacyControllerState`。

### 5.6 Endpoint 限制

从 `controller.json` 读取的 endpoint 必须同时满足：

- scheme 精确为 `http`；
- hostname 精确为 `127.0.0.1`；
- 有效 TCP port 为 `1..65535`；
- 无 username/password；
- 无 query/fragment；
- path 只能为空或 `/`。

不接受 `localhost`、`0.0.0.0`、IPv6、外部地址或任意文件提供的其他 URL。

## 6. Health 与普通调用

`GET /control/health` 继续要求 Bearer token，并返回：

```json
{
  "status": "ready",
  "protocol_version": 2,
  "implementation_version": "0.3.1",
  "implementation_sha256": "...",
  "config_sha256": "...",
  "instance_id": "...",
  "pid": 12345
}
```

Bridge 的当前实例验证顺序：

1. state 文件可解析；
2. `config_path` 与调用方配置路径一致；
3. endpoint 为严格 loopback；
4. health 可连接且 token 正确；
5. authenticated health 必须是符合模型的 JSON object；
6. protocol 匹配；
7. config hash 匹配；
8. implementation hash 匹配；
9. state 与 health 的 `instance_id/pid/hash/version` 一致。

只有全部满足才视为 healthy。合法 JSON 但非 object 的 health（例如数组）必须转换为受控 `controller_state_invalid`，不得泄漏 `AttributeError` 等内部异常。

## 7. 跨协议显式停止

新增管理入口语义：

```text
ControllerClient.stop_existing(config_path, timeout=...)
```

行为：

1. 以 legacy 方式读取 `controller.json`；
2. 校验 config_path 与严格 loopback endpoint；
3. 使用 state 中保存的 token；
4. 对 v1 Controller，向 `/control/stop` 发送 state 自己的 `protocol_version`；
5. 对 v2 及以后，`/control/stop` 只要鉴权成功即可接受停止，不要求与 Bridge 当前协议一致；
6. 记录本次准备停止的 `instance_id`（v1 没有时使用 `pid + token` 作为 legacy 身份）；
7. 发送 stop 后继续轮询目标 state，只有目标 state 已删除时才返回 `stopped`；health/listener 先不可达**不能单独证明完整退出**；
8. 如果 state 已被另一个新实例替换，停止流程不得继续攻击新实例，应返回可识别的 `replaced` 结果；
9. deadline 到期而目标 state 仍存在时返回 `controller_stop_timeout`。

`manage stop` 增加：

```text
python -m agy_worker.manage stop --config <path>
```

`scripts/stop.ps1` 增加可选 `-Config` 并转发。默认仍是正式 `config/runtime.toml`。

## 8. Controller 启动接管

`ControllerClient._ensure()` 使用 deadline 驱动循环，而不是只抢一次启动锁。

伪流程：

```text
while before deadline:
    如果当前 Controller healthy -> return

    尝试非阻塞获得 controller-launch.lock
    如果获得：
        再次 health（double check）
        读取共享 pending launch PID
        如果已有 pending PID 且仍存活 -> 等待，不重复 launch
        否则按冷却间隔尝试 launch，并把新 PID 写回共享 pending 元数据
        释放锁

    短退避

超时 -> controller_start_failed
```

要求：

- 等待者在原 lock owner 崩溃后必须能重新尝试拿锁；
- 正在退出的旧 Runtime 暂时持有 `runtime.lock` 时，第一台新 Controller 即便以 `runtime_busy` 退出，Bridge 仍可在 deadline 内重新尝试；
- 单个 Bridge 不得高频创建进程，launch attempt 使用至少 0.5 秒冷却；
- pending launch 信息需要跨 Bridge 共享，不能只用 client 内存 cooldown；若 pending launcher 仍存活，其他 Bridge 不得重复创建 Controller；
- WMI 启动解析 `Win32_Process.Create` 返回的 `ProcessId`，用于启动归属与诊断；Controller 是否 ready 仍只由带 token 的 authenticated health 决定；
- Windows venv 的 `pythonw.exe` 是 redirector launcher：WMI 返回的 launcher PID 可以与 health/state 中真实 Python Controller PID 不同，不能把数值相等当成正确性条件；
- 同一数据目录最终仍只允许一个 Runtime。

## 9. `run-task.py --config` 的 Controller 所有权

### 9.1 默认行为

正式配置（未显式传 `--config`）保持现状：Controller 是持久服务，脚本退出不停止。

显式传入 `--config <path>` 时：

- 如果该 data_dir 在脚本开始前已有 healthy Controller，脚本复用且**不负责停止**；
- 如果是本次脚本首次拉起的 Controller，脚本记录其 `instance_id` 为 owned instance；
- 请求完成、失败、异常或 Ctrl+C 时，在 `finally` 中停止自己拥有的同一实例；
- 如果 Controller 已被另一个实例替换，不得误停替代实例。

新增选项：

```text
--keep-controller
```

仅在显式 `--config` 时有效，用于维护者有意保留 custom Controller。

### 9.2 ControllerClient 启动结果

`ControllerClient` 记录：

```text
started_controller: bool
started_instance_id: str | None
```

只有“当前 client 发起 launch，且最终 healthy state 的实例就是该 launch 所产生实例”才能把 `started_controller` 置 true。仅仅等待另一个 Bridge 启动成功不算 ownership。

归属证明规则：

- 非 redirector 情况下，healthy state PID 与本 client launch PID 相同可直接证明；
- Windows venv 情况下，若 PID 不同，必须同时证明 WMI launcher PID 仍存活，并由 `Win32_Process` 父链确认 healthy Controller PID 是该 launcher 的后代；
- 进程关系查询失败、launcher 已退出或无法证明后代关系时，一律保持 `started_controller=false`，不能冒认 ownership。

最终 cleanup 仍以 `started_instance_id` 做 replacement-safe stop，不以 launcher PID 直接停止进程。

## 10. 重连与 MCP timeout

`ControllerClient.call()` 仍只对连接级 `controller_unavailable` 自动重连一次。

重连后的参数规则：

- `submit/continue`：保留相同 `request_id`，利用现有幂等约束；
- `cancel`：保持幂等取消；
- `artifact_read/capabilities`：只读重试；
- `status`：保留 `task_id/after_revision`，但强制将第二次请求的 `wait_ms` 改为 `0`，立即返回当前状态。

Codex 注册的 `tool_timeout_sec` 从 30 调整为 60，给 Controller 重连留出外层预算。`status.wait_ms` 公共上限仍为 25000，不修改公开请求 Schema。

## 11. 单执行槽背压与排队取消

保持：

```text
max_concurrent_tasks = 1
```

新增：

```text
max_inflight_tasks = 16
```

其中 inflight 包含 `queued + running + cancelling`。

提交顺序必须先做 `request_id` 幂等查找，再做容量判断：

- 已存在同 request_id / 同 fingerprint：仍返回原任务，不占新容量；
- 已存在同 request_id / 不同 fingerprint：仍返回 `idempotency_conflict`；
- 新请求且 inflight 已到 16：返回 `worker_busy`，不创建 task 目录、不写 session、不排队。

Runtime 保存 executor 返回的 `Future` 到任务 context。

取消 queued task：

- `future.cancel()` 成功时立即标记 `cancelled`；
- 写 audit / state；
- 从 `active` 移除；
- 不等待前面的任务结束后才执行 `_run()`。

取消 running task 继续沿用已有 cancel event + Job Object 终止逻辑。

`agy_capabilities.controller` 增加 `max_inflight_tasks: 16`。

## 12. 本机凭据 ACL 诊断

Bearer token 继续只写入 data_dir 下的 `controller.json`，且 endpoint 只监听 `127.0.0.1`。

本次不宣称实现 Windows 安全沙箱，也不自动重写用户 ACL。新增**诊断性**检查：

```text
controller_data_acl.checked
controller_data_acl.broad_read_principals
controller_data_acl.token_confidentiality_advisory
```

检查目标是发现 `Everyone`、`BUILTIN\Users`、`Authenticated Users` 等宽泛主体对 data_dir 明显拥有读取权限。若检查 API 失败：

- `checked=false`；
- doctor 给出可操作警告；
- 不伪装为 secure；
- 不阻断普通 Controller 启动，以免把启发式 ACL 检查误当成系统安全证明。

该字段只表达诊断建议，不得命名为 `os_isolation=true` 或 `secure=true`。

## 13. `request_id` 合同

保持数据库全局 UNIQUE 语义，不做 migration：

```text
一个 data_dir / 一个 Controller 历史范围内全局唯一
```

规则：

- 每个新的逻辑操作使用全局唯一 request_id；
- 推荐 `req-<uuid4 hex>`；
- 只有“同一个逻辑请求的传输 / Controller 重连重试”才能复用相同 ID；
- 多个 Codex 对话不能各自把 `build-001` 当成本地命名空间。

更新工具描述、README 和示例，不改变现有幂等数据库结构。

## 14. 维护者辅助清洗命名

v0.3 的“维护者辅助清洗”当前是**工作流约束**：由调用方把 objective 限定为事实、定位、证据行号，AGY 摘要由 Codex 回看证据后使用。

本次文档统一称：

```text
维护者辅助清洗流程
```

不得称作“Runtime 已实现的 analysis mode”。本次不新增 `analysis_level` / `purpose` 公共字段，避免为了命名问题扩大协议。

## 15. 包版本与依赖

- 项目版本升级到 `0.3.1`；
- `server.py` 的 MCP server version 从 package metadata 读取，不再硬编码；
- `pyproject.toml` 正式 dependencies 补充 `jsonschema==4.26.0`，与现有 `requirements.lock` 一致；
- 不做其他依赖升级。

## 16. 验收标准

### 16.1 代码级行为

至少覆盖以下行为测试：

1. config 改变后，新 Bridge 拒绝旧 Controller；
2. Controller 实现摘要改变后，新 Bridge 拒绝旧 Controller；
3. 非 `http://127.0.0.1:<port>` state 被拒绝且不发网络请求；
4. authenticated health 若不是 object，受控返回 `controller_state_invalid`；
5. v2 Bridge 可通过管理停止路径停止模拟的 v1 Controller；
6. `stop --config` 作用于目标 custom data_dir，并等待目标 state 真正消失；
7. health listener 先关闭但目标 state 尚存时，stop 不能提前返回成功；
8. 启动锁 owner 退出后 waiter 可接管；
9. 旧 Controller stopping / runtime lock 短暂占用后可最终启动新 Controller；
10. launch 后共享 pending PID 被发布，存活 pending PID 能阻止重复 launch；
11. Windows venv launcher PID 与 Controller PID 不同时，能基于后代关系建立 owned instance；
12. custom `run-task --config` 停止自己启动的 Controller；
13. custom `run-task --config` 不停止原本已存在的 Controller；
14. `--keep-controller` 明确保留 owned custom Controller；
15. status 重连第二次 `wait_ms=0`；
16. 同 request_id 重试不被背压拒绝；
17. 第 17 个新 inflight 请求返回 `worker_busy`；
18. queued task cancel 后无需等执行槽即可终态 `cancelled`；
19. ACL 检查失败时只报告 advisory，不虚构安全；
20. 两个 stdio Bridge 仍能共享一个 Controller；
21. Controller 重启仍把未完成任务标为 `interrupted`，历史 artifact 可读；
22. 六个公开 MCP 工具名称保持不变。

### 16.2 Windows 本地验收

本地 AI 必须真实执行：

- `scripts/check.ps1`；
- Controller 相关定向 pytest；
- 从“无 Controller”状态启动两个 stdio Bridge 的 fresh lifecycle 验收；
- Bridge 全部退出后验证同一 Controller PID/instance 仍存活；
- 显式 stop 后验证 state 消失且 health 不再可达；
- custom config 运行结束后验证没有遗留它自己启动的隐藏 Controller；
- `git status --short` / `git diff --check`，确认验收过程没有修改受版本控制的生产文件，且当前分支无 whitespace error。

正式 AGY / HBuilderX / Android 不属于这次 Controller hardening 的必要通过条件，除非实现改动实际触及对应执行链路；若未执行不得声称通过。

## 17. 开发与审查流程

按项目指令与 Superpowers Web Adapter：

```text
规格确认
→ 详细 PLAN / TASKS
→ 行为测试与根因验证
→ ChatGPT 在独立 GitHub 分支持续实现
→ 远端规格复核 pass
→ 远端代码质量复核 pass
→ 锁定精确 final HEAD
→ 本地 AI 在 Windows 上一次性完整执行 LOCAL-ACCEPTANCE.md
→ ChatGPT 按 receiving-code-review 技术核对本地证据
→ verification-before-completion
→ Draft PR 交付
```

用户已明确选择“远端开发全部完成后，再由本地 AI 做最终一次完整验收”。Remediation 期间只有在真实 Windows 行为无法由远端静态证据判断时才做聚焦 RED/GREEN，不恢复逐 Task 打断模式。

当前仓库没有 GitHub Actions workflow，因此不能用不存在的 CI 替代本地测试证据。

未经用户明确授权：

- 不合并 `main`；
- 不标记自动合并；
- 不删除开发分支；
- 不强制推送；
- 不把本地 AI 的意见未经技术复核直接照改。
