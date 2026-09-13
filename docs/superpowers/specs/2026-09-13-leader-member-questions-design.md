# Leader–Member AI Questions Design

## 背景

AGY Worker 当前是单向的“领导 → 成员”结构：Codex/GPT 通过公开 MCP 提交任务，Controller/Runtime 启动 AGY，AGY 只能经私有 Broker 使用已授权动作。AGY 在执行过程中如果缺少业务判断、上下文或需要上级选择，目前只能失败或自行猜测，不能向总控 AI 反问。

本功能新增一条受控的反向协作路径，让正在执行任务的成员 AI 可以向领导 AI 发起问题，并在收到答复后继续同一轮任务。

## 目标

1. 成员 AI（当前实现中的 AGY）可在当前任务内调用私有 `worker_action` 的 `ask_leader` 动作。
2. 领导 AI 可通过现有 `agy_status` 观察到待回答问题，无需新增 webhook、外部聊天服务或 server push。
3. 领导 AI 使用新增公开 MCP 工具 `agy_answer` 回复；成员收到答复后从原 `ask_leader` 调用继续执行。
4. 所有协作仍经过 Controller/Runtime；不能借此调用任意 shell、其他 MCP、外部模型 API或扩大原任务权限。
5. 问答具有边界、审计和幂等语义，取消、超时和 Controller 重启时 fail closed。

## 非目标

- 不实现多级组织树、成员注册中心、群聊、广播或成员间直接通信。
- 不让成员 AI 直接访问领导 AI 的工具、聊天线程或账号。
- 不接入 OpenAI/Anthropic/Google 等外部模型 API，也不在 Worker 中管理模型密钥。
- 不改变源码写入、任意 shell、浏览器 origin、Android 等现有权限边界。
- 不把 `agy_status` 改造成 webhook 或主动推送协议。

## 方案比较

### 方案 A：Runtime 内的受控问答交换（采用）

成员经私有 Broker 调用 `ask_leader`，Runtime 把问题写入当前 task record 并增加 revision；领导原本就在轮询 `agy_status`，因此可立即看到 `leader_question`。领导调用 `agy_answer` 后，Runtime 原子记录答复并唤醒阻塞中的成员调用。

优点：复用现有身份、任务令牌、Controller、SQLite task record 和 status long-poll；没有新端口/服务/凭据；安全边界最清晰。缺点：每个问题会占用当前 AGY 任务时间预算，这也是预期的 fail-closed 行为。

### 方案 B：独立聊天/消息服务（不采用）

增加新的常驻消息队列或 HTTP 服务，把成员与领导都接入消息通道。扩展性更强，但引入第二事实源、生命周期、鉴权、持久化和恢复问题，对当前单 Worker 架构过重。

### 方案 C：成员直接调用外部大模型（不采用）

AGY 自己调用另一个模型 API。实现表面简单，但会引入供应商耦合、密钥管理、额外网络权限，并绕过“Codex/GPT 为总控”的现有责任边界。

## 公共合同

### `agy_status`

非终态 task 可能额外返回：

```json
{
  "leader_question": {
    "question_id": "question-<uuid4hex>",
    "question": "需要领导判断的问题",
    "created_at": "ISO-8601"
  }
}
```

当一次 status long-poll 观察到 `leader_question` 时，Server 必须立即把该状态返回给领导 AI，不能像普通 progress revision 一样继续合并掉。

### `agy_answer`

新增第 7 个公开 MCP 工具：

```json
{
  "task_id": "task-...",
  "question_id": "question-...",
  "answer": "领导给成员的答复"
}
```

成功返回：

```json
{
  "task_id": "task-...",
  "question_id": "question-...",
  "status": "answered",
  "revision": 12
}
```

同一个 `question_id` + 完全相同 answer 的重试是幂等成功；同 ID 不同 answer 返回 `idempotency_conflict`。回答不存在、已过期或不属于当前 pending question 的 ID 时 fail closed。

公开请求使用严格 Pydantic 模型，拒绝未知字段。回答不能为空，长度受限。

## 私有成员合同

`agy-worker-broker` 的 `worker_action` 增加：

```json
{
  "action": "ask_leader",
  "arguments": {
    "question": "需要上级判断的问题"
  }
}
```

只允许 `question` 一个参数。问题不能为空；UTF-8 内容有固定上限。每个 task 最多发起 8 个问题，防止循环询问消耗整个执行预算。

`ask_leader` 不授予任何新的环境权限，它只把文本写回当前 task 的协作状态，因此不新增 permission 开关。

## Runtime 状态与数据流

为降低与现有 `runtime.py` 和并行 PR 的耦合，新增 `CollaborativeRuntime(Runtime)`，由 Controller 实例化该子类。基础 Runtime 的执行、授权和 artifact 逻辑不重写。

流程：

```text
Leader AI
  agy_worker / agy_continue
        ↓
Controller → CollaborativeRuntime → AGY member
                               ↓ worker_action.ask_leader
                         pending question
                               ↓ task revision
Leader AI ← agy_status(leader_question)
    ↓ agy_answer
CollaborativeRuntime records answer + signals waiter
                               ↓
                         AGY member resumes
```

`CollaborativeRuntime` 负责：

- 拦截私有 `ask_leader` action；其他 action 原样委托基础 Runtime。
- 将 pending `leader_question` 纳入公开 task 状态。
- 处理 Controller `answer` 方法。
- 在内存 context 中维护等待 Event 和当前 answer；在持久 task record 中维护 `leader_dialogue` 历史，用于审计和幂等重试。
- 取消或总预算耗尽时关闭 pending question，并让等待中的成员失败返回；不得延长任务总 `total_timeout_sec`。
- Controller 重启后基础 Runtime 会把非终态任务标记为 `interrupted`；旧 pending question 不可继续回答。

每个历史项最多保存本轮受限问题/答案，不公开到默认 terminal status；完整内容仅留在本任务本地状态与审计范围，避免扩大 MCP 热路径上下文。

## 安全与边界

- `ask_leader` 仍只能通过本轮私有 Broker 和 task bearer token 到达 Runtime。
- `agy_answer` 仍只能通过已认证的 Controller IPC 到达 Runtime。
- 成员无法选择目标 leader、Controller endpoint 或任意外部地址。
- 问题/答案不会被解释成 shell、路径或浏览器参数。
- 不修改 `PROTOCOL_VERSION=2`：新 Controller 方法是同一实现版本内的加法；Bridge/Controller 已通过 `implementation_sha256` 做严格同版本检查。新增 `collaboration.py` 必须纳入 implementation hash 文件集合。
- 包版本升级为 `0.4.0`，明确这是公开 MCP 合同新增能力。

## 错误与边界语义

- 空问题/空答案、未知字段、超限文本 → `invalid_request`。
- 超过每 task 8 次问题 → `quota_exceeded`。
- task 不存在或已终态且没有可幂等重放的历史回答 → `invalid_request`。
- question ID 与当前 pending 不一致 → `stale_question`。
- 同 question ID 使用不同 answer 重试 → `idempotency_conflict`。
- task 被取消 → 成员等待返回 `cancelled`；task 最终由现有 Runtime 取消语义收口。
- 等待期间耗尽任务总预算 → 成员等待返回 `timed_out`；不得另设无限咨询超时。

## 测试策略

新增真实 Runtime 行为测试（不调用真实 AGY）：

1. 成员 `ask_leader` 在独立线程阻塞，`status` 能观察到 question。
2. `agy_answer` 唤醒成员，成员收到正确 answer；pending question 从公开状态消失。
3. 同答复重试幂等，不同答复冲突。
4. stale question ID 被拒绝。
5. 取消/超时能终止等待。
6. Server status coalescing 看到 `leader_question` 后立即返回。
7. `agy_answer` MCP schema、Controller 转发和 schema 生成被覆盖。
8. Broker schema 只新增 `ask_leader`，不开放其他 MCP/shell。
9. Controller implementation hash 覆盖新增协作模块。

ChatGPT Web 无 Windows + pywin32 + 真实 AGY 执行环境，因此实现阶段只能提交测试与做仓库级静态审查；最终 `scripts/check.ps1`、schema regeneration、真实 AGY 问答闭环由本地验收执行并回填证据。
