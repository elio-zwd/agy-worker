# AGY Worker v0.3.2 已知后续问题

> 状态：仅记录，暂不修复。
>
> 基线：`main@b88e750496b341ff54ac959114302cfb58fad1a0`（PR #2 合并后的 v0.3.2）。
>
> 2026-09-11 用户决定当前项目暂停继续开发；以下问题不阻塞现有个人使用，也不授权在本 PR 中修改生产代码、测试、配置或协议。

## 当前可用基线

v0.3.2 已获得以下新鲜证据：

```text
scripts/check.ps1: exit 0
pytest: 114 passed / 0 failed / 0 skipped / 0 warnings
compileall: PASS
git diff --check: exit 0
schema regeneration: exit 0 / git diff -- schemas 为空
Codex MCP tool_timeout_sec: 660
用户 developer instructions 与其他 MCP 配置保留
```

真实业务项目中，`jianyu_compile_test` 至少两次完整成功：

```text
run 1: succeeded / exit 0 / 225406 ms / errors 0 / warnings 25
run 2: succeeded / exit 0 / 201451 ms / errors 0 / warnings 25
```

两次长任务都只经过一个 Codex 可见的 `agy_status` 调用即返回 terminal，说明 v0.3.2 的长等待与 progress coalescing 已达到当前使用目标。

## Follow-up 1：默认 300 秒任务总预算可能不足以覆盖较慢的编译/测试

### 已观察事实

第三次真实 `jianyu_compile_test`：

```text
status: failed
operation.exit_code: 130
operation.duration_ms: 267096
operation.termination_reason: timed_out
total_errors: 0
total_warnings: 9
source_changed: false
```

操作日志最后可见阶段位于：

```text
:app:kspDebugUnitTestKotlin
```

此前已经出现：

```text
:app:compileDebugKotlin
:app:compileDebugJavaWithJavac
:app:processDebugJavaRes
:app:bundleDebugClassesToCompileJar
:app:bundleDebugClassesToRuntimeJar
```

当前证据**不能证明 KSP 自身死锁或发生故障**；它只说明命令在该阶段附近尚未完成时被 Worker 的任务预算终止。没有观察到编译错误或单元测试断言失败。

### 已确认的 Worker 语义

公开 `total_timeout_sec` 默认值为 300 秒。Runtime 在真正启动已登记 build/test 命令时使用剩余预算：

```text
remaining = total_timeout_sec - 从任务开始到命令启动前已经消耗的时间
```

因此，AGY、快照、调度等前置步骤会消耗同一个 300 秒总预算。第三次命令进程约 267 秒后 `timed_out`，与这一语义相符。

这与公开 `agy_status.wait_ms` 最大 600 秒无关：status 的 50～600 秒是一次 MCP 等待调用的预算，不是任务执行总超时。

### 当前影响

- 常见的约 200～225 秒 `jianyu_compile_test` 已两次成功。
- 更慢的一次执行在默认总预算下被终止。
- 对明显较长的任务，当前调用方可以显式设置更大的 `limits.total_timeout_sec`（公开范围 10～1800 秒）；但本记录不改变任何默认值或路由策略。

### 未来调查方向（未批准实施）

后续若恢复开发，可独立验证：

1. 相同项目显式设置更大的 `total_timeout_sec` 后是否稳定完成；
2. 是否需要按已登记 command 提供任务时长提示或策略；
3. Codex 是否应根据构建类型更稳定地选择任务总预算；
4. 如扩大预算后仍停在同一 Gradle/KSP 阶段，再单独调查 Gradle、KSP、Daemon、资源占用或业务项目本身。

在获得新证据前，不把 `kspDebugUnitTestKotlin` 当作已确认根因。

## Follow-up 2：terminal follow-up 时 Codex 偶发选择非法的短 `agy_status.wait_ms`

### 已观察事实

在一个已经 terminal 的任务 follow-up 查询中，Codex 首次发送了低于公开最小值的 `agy_status.wait_ms`，MCP 正确返回：

```text
invalid_request: wait_ms 最小为 50000
```

随后 Codex 重试，并取得既有 terminal `failed rev=15` 状态。

### 当前合同

公开 `McpStatusRequest.wait_ms`：

```text
default: 50000 ms
minimum: 50000 ms
maximum: 600000 ms
```

没有 `after_revision` 时，调用方可以省略 `wait_ms`；MCP 内部会转换为即时 `wait_ms=0` 快照。内部 0～25000ms 合同不会暴露给普通 Codex 调用。

### 当前影响

- MCP 参数校验按设计 fail-closed，没有把非法值传入 Controller。
- 一次无效请求会产生额外 tool round-trip，但不会破坏已有任务或结果。
- 重试后可以正常读取 terminal。

### 未来调查方向（未批准实施）

后续若恢复开发，可独立评估：

1. terminal/follow-up 查询是否应更明确引导 Codex 省略 `after_revision` / `wait_ms` 获取即时快照；
2. tool description / managed routing instruction 是否还需要降低模型选择内部短等待值的概率；
3. 是否存在其他 Codex 场景会把内部 `<=25000ms` 语义误用于公开 MCP 参数。

当前不放宽公开校验，也不加入兼容 fallback；现有拒绝行为视为正确安全边界。

## 暂停状态

```text
project_development: paused
current_version: usable_for_personal_use
followups_block_merge: false
production_fix_in_this_pr: none
```

本文件及对应 Draft PR 只用于保存后续上下文。恢复开发时应重新读取最新 `main`、`AGENTS.md`、README、相关源码/测试，并按当时事实重新调查，不应直接把本文件中的未来调查方向当作既定修复方案。
