# Controller v0.3.1 Planning Hub

本目录是 `fix/controller-hardening-v031` 的跨对话持久上下文。后续 ChatGPT、本地 AI 或新的开发对话应先读这里，不要只依赖聊天记录。

## 阅读顺序

1. `SPEC.md` — 目标、架构决定、安全边界、验收标准；冲突时它高于施工计划。
2. `PLAN.md` — T1～T9 的逐任务 TDD 实施步骤、文件、接口、提交和审查 gate。
3. `TASKS.md` — 唯一进度追踪表；每次 RED/GREEN/Review/Acceptance 后更新状态和证据。
4. `LOCAL-ACCEPTANCE.md` — 用户本地 AI 的 Windows 执行与报告格式。

## 当前状态

```text
base: 904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066
branch: fix/controller-hardening-v031
phase: planning
production code changed: no
local tests for this branch executed: no
user approval to start production implementation: pending
```

## 计划自审结论

按 Superpowers `writing-plans` / plan reviewer 的 Completeness、Spec Alignment、Task Decomposition、Buildability 四项做过一次自审。

### 已确认覆盖

- stale config / stale implementation；
- protocol upgrade 与旧 Controller stop；
- custom `run-task --config` Controller 泄漏；
- launch lock owner 崩溃后的 takeover；
- stopping / runtime-lock 窗口重试；
- state endpoint fail-closed；
- data_dir ACL advisory；
- status reconnect timeout budget；
- 单执行槽 inflight backpressure；
- queued task immediate cancel；
- request_id 全局幂等命名约束；
- `jsonschema` 正式依赖；
- “维护者辅助清洗”真实边界；
- fresh 双 Bridge Windows 生命周期验收；
- 完成前 spec review / code-quality review / local acceptance / Git diff review。

### 执行时必须采用的两项自审修正

#### R1 — v0.3.1 版本测试不能用旧 editable metadata 自证

`PLAN.md` Task 8 中“server version 一致性”的 RED 期望必须由测试**独立写死预期发布版本 `0.3.1`**，不能只写：

```python
assert server_version == implementation_version()
```

因为当前 Windows venv 是 editable install，修改 `pyproject.toml` 后，既有 `.dist-info` 的 `importlib.metadata.version()` 可能仍是安装时的 `0.3.0`；如果测试两边都读这个旧值，会产生镜像断言。

正确 TDD 行为：

```python
assert initialized.server_info.version == "0.3.1"
```

RED：旧 server 返回 `0.3.0`。

实现 Task 8 package metadata 后，本地 AI 在 GREEN 前额外执行：

```powershell
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
```

这是本任务显式修改 package metadata 后的必要刷新，不代表日常初始化要重装依赖。随后再跑 `tests/test_server.py`。

#### R2 — custom run-task no-leak 验收不能依赖真实 AGY 成功

`LOCAL-ACCEPTANCE.md` 第 9 节在最终 Task 9 更新时，应将 lifecycle no-leak 主断言改成**可预期的业务拒绝也必须 cleanup**：

- 使用 isolated custom config；
- 让 Bridge/Controller 确实启动；
- 提交一个能在 Runtime 业务校验阶段快速失败、不会调用 AGY 的请求，例如不存在的 `workspace_id`；
- `run-task` 返回非 0 是该探针的预期业务结果；
- 生命周期通过条件只看“本次 owned Controller state/health 最终消失”；
- `--keep-controller` 对同类探针应保留 owned Controller，随后 `stop.ps1 -Config` 清理。

真实 AGY 任务可以作为额外验收，但不得成为证明 custom Controller cleanup 的必要条件。

## 其他实现解释

- 普通 Bridge 对 legacy state 可以做**诊断性解析**以返回 `protocol_mismatch`，但只有当前 v2 `ControllerState` 才能成为 healthy business Controller；这不算接受旧协议业务调用。
- WMI 返回的 `ProcessId` 用于判断本次 launch 是否对应最终 state PID，并结合最终 `instance_id` 记录 ownership；readiness 仍必须通过 Bearer health，不以 PID 单独判活。
- ACL 检查是 advisory，不得产生 `secure=true` / `os_isolation=true` 一类结论。

## 进入实施的 Gate

用户确认本目录规格/计划后：

```text
T1 写失败测试
→ 提交测试
→ 本地 AI 真实执行 RED
→ ChatGPT 才写 T1 生产实现
→ 本地 AI 执行 GREEN
→ ChatGPT 做规格复核 + 代码质量复核
→ 更新 TASKS.md
→ 下一任务
```

当前没有任何生产代码修改，也没有本分支测试通过声明。
