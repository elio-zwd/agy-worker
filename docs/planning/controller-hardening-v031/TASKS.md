# Controller v0.3.1 Hardening Task Tracker

> 本文件是 `fix/controller-hardening-v031` 的**唯一当前进度状态源**。后续 ChatGPT / 本地 AI 不应仅凭聊天记忆判断进度。
> 规格：`SPEC.md`
> 施工计划：`PLAN.md`
> 最终本地验收：`LOCAL-ACCEPTANCE.md`
> Base：`904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066`

## 状态定义

| 状态 | 含义 |
|---|---|
| `planned` | 已进入计划，尚未写对应行为测试 |
| `implementing` | 正在修改测试或生产实现 |
| `awaiting_acceptance` | 远端实现、测试代码和静态审查已准备；当前最终树仍缺 Windows 一次性执行证据 |
| `accepted` | 最终本地验收证据已由 ChatGPT 技术复核通过 |
| `blocked` | 有明确阻断问题，必须记录原因和证据 |

## 当前总状态

```text
phase: final_remote_review_complete_waiting_second_local_acceptance
production_code_changed: true
user_plan_approval: approved_2026-09-09
base: 904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066
previous_acceptance_head: 61af5ae22241667f3b560e1559fdf360769717e6
previous_acceptance_verdict: FAIL
previous_acceptance_full_pytest: 65_passed_6_failed_6_warnings
signal_fix: verified_focused_green
stop_state_race_fix: verified_focused_green
run_task_cleanup_fix: verified_focused_green
health_non_object_fix: verified_focused_green
wmi_venv_ownership_fix: implemented_after_valid_red_final_windows_green_pending
shared_pending_launch_tests: deterministic_replacement_committed_final_windows_green_pending
trailing_whitespace_cleanup: committed_execution_verification_pending
remote_spec_review: completed_no_open_critical_or_important
remote_code_quality_review: completed_no_open_critical_or_important
fresh_windows_verification_for_current_head: pending
final_handoff_head: use_exact_branch_head_from_handoff_prompt
open_pr: none
merge_authorized: false
```

## 证据边界

第一次最终 Windows 验收在精确 HEAD `61af5ae22241667f3b560e1559fdf360769717e6`、clean worktree、Windows 10 Pro 19045 x64、PowerShell 7.6.5、Python 3.13.9 上真实执行。它确认部分 v0.3.1 行为当时通过，同时发现 6 个 pytest failure、6 个 thread warning、custom-config 默认 cleanup 泄漏和 11 处 Markdown trailing whitespace。

该历史证据只用于定位，**不能证明当前最终 HEAD 通过**。当前分支已继续修改生产代码与测试；仓库没有 GitHub Actions workflow 可替代最终 Windows 执行。远端静态审查也不能替代 `scripts/check.ps1`、真实 WMI lifecycle 和 `git diff --check`。

## Remediation 已确认根因与证据

### R1 — test-thread signal registration

第一次验收中 T2/T3/T4 的 6 个失败都伴随：

```text
ValueError: signal only works in main thread of the main interpreter
```

根因是 `controller.run()` 在 background test thread 注册进程级 signal handler，异常发生后正常 `service.close()` 生命周期被破坏。

修复：只有 Python 主线程注册 SIGINT/SIGTERM；生产 `main()` 行为保持。

聚焦 Windows 复验：

```text
tests/test_controller.py -k "stop or protocol or takeover or launch_retry or wmi_launch"
7 passed, 6 deselected
无 PytestUnhandledThreadExceptionWarning
无 signal ValueError
```

结论：focused GREEN。

### R2 — stop/state 删除竞态

真实 `run-task --config` 曾观察到业务请求已经返回，但 `controller.json` 仍存在。确定性 RED 证明 `stop_existing()` 在 health listener 先关闭、state 尚未 unlink 时过早返回：

```text
assert management_reads >= 3
E assert 2 >= 3
```

修复：health 不可达只表示 listener 已停止；显式 stop 必须继续条件轮询目标 state，直到 state 删除、replacement 出现或 deadline 到期。

聚焦 Windows 复验：

```text
test_stop_waits_for_state_disappearance_after_health_disconnect
1 passed

tests/test_run_task.py
3 passed
```

结论：focused GREEN。

### R3 — Windows venv WMI PID 语义与 ownership

真实 Windows 多次观测到：

```text
WMI ProcessId != controller state.pid
```

核对 CPython 3.13 `PC/venvlauncher.c` 后确认：venv `pythonw.exe` 是 redirector launcher，它会 `CreateProcessW()` 启动真实 Python 并等待子进程退出。因此 WMI 返回 launcher PID，而 Controller 的 `os.getpid()` 是其 Python 子进程 PID；二者数值不相等本身不是 bug。

有效 RED：

```text
test_owned_launch_accepts_healthy_descendant_pid
assert client.started_controller is True
E assert False is True
```

真实 Windows 也确认旧实现无法建立 ownership：`started_controller=False`、`started_instance_id=null`，但 cleanup 后无 replacement 残留。

修复：`ControllerClient` 仍保留 WMI launcher PID 作诊断；当 healthy state PID 不与 launcher PID 相等时，只有在 launcher 仍存活且 Win32_Process 父链证明 healthy Controller 是该 launcher 的后代时才建立 `started_controller/started_instance_id`。查询失败一律 fail-closed，不冒认 ownership。

当前状态：生产修复已提交；**该生产修复尚无修改后 Windows GREEN，必须由第二次完整最终验收验证。**

### R4 — shared pending launch

早期并发测试两次在“首个 client 未实际发起 launch”处失败，说明该测试的线程/时序观察方式本身不能可靠证明 shared pending 行为，因此没有继续通过增加 sleep 修测试。

已改成两个确定性行为测试：

- `test_launch_writes_shared_pending_pid`：本 client launch 后必须把 PID 写入共享 `controller-launch.lock` 元数据；
- `test_live_shared_pending_pid_blocks_duplicate_launch`：另一个 Bridge 已发布且 PID 仍存活时，本 client 不得重复 `_launch()`。

生产实现继续使用共享 pending PID + 存活条件判断；失败子进程退出后仍受至少 0.5 秒 cooldown 约束并允许 retry。

当前状态：测试合同已稳定化；**新测试尚无 Windows GREEN，必须由第二次完整最终验收验证。**

### R5 — authenticated health 非 object

静态质量审查补出 `GET /control/health` 返回合法 JSON 但不是 object 的边界。有效 RED：

```text
AttributeError: 'list' object has no attribute 'get'
```

修复：在任何 `.get()` 前要求 authenticated health 是 JSON object，否则统一转换为 `controller_state_invalid`。

聚焦 Windows 复验：

```text
1 passed
AttributeError absent
controller_state_invalid verified
```

结论：focused GREEN。

### R6 — Git whitespace gate

第一次验收：`git diff --check` exit 2，共 11 个 tracked Markdown trailing whitespace finding，涉及：

- `docs/planning/controller-hardening-v031/LOCAL-ACCEPTANCE.md` 3 行；
- `docs/planning/controller-hardening-v031/SPEC.md` 3 行；
- `docs/planning/controller-hardening-v031/TASKS.md` 4 行；
- `docs/实施设计.md` 1 行。

这些位置已机械清理，同时 SPEC / 实施设计同步了真实 Windows remediation 后的 stop 与 venv ownership 语义。远端没有本机 git worktree，因此**尚未声称 `git diff --check` 已通过**；第二次最终本地验收必须对 fixed Base 和 `origin/main...HEAD` 都实际执行并要求 exit 0。

## 任务总览

| ID | Priority | 任务 | 远端状态 | Windows 当前状态 |
|---|---|---|---|---|
| T1 | P0 | Controller v2 身份 / stale config & implementation | `awaiting_acceptance` | 61af 部分 PASS；health 非 object focused GREEN；最终 HEAD 待重跑 |
| T2 | P0 | 跨协议显式 stop + `--config` stop | `awaiting_acceptance` | signal + stop/state focused GREEN；最终 HEAD 待重跑 |
| T3 | P0 | 启动锁 takeover / retry / WMI launch | `awaiting_acceptance` | 原 stop/takeover GREEN；venv ownership 新实现与 deterministic pending tests 待最终 Windows GREEN |
| T4 | P0 | custom `run-task --config` ownership / cleanup | `awaiting_acceptance` | unit 3 passed；真实 ownership 新实现待最终 lifecycle |
| T5 | P1 | status reconnect / MCP timeout budget | `awaiting_acceptance` | 61af `4 passed`；最终 HEAD 待重跑 |
| T6 | P1 | inflight backpressure / queued cancel | `awaiting_acceptance` | 61af `13 passed`；最终 HEAD 待重跑 |
| T7 | P1 | Controller data_dir ACL advisory | `awaiting_acceptance` | doctor 可执行；broad-read advisory 已知；最终 HEAD 待诊断 |
| T8 | P2 | package/version/request_id/docs | `awaiting_acceptance` | package/server 61af PASS；whitespace cleanup 已提交，最终 gate 待执行 |
| T9 | Gate | fresh lifecycle + full verification + handoff | `awaiting_acceptance` | 第二次完整 final acceptance 尚未执行；PR blocked |

## 主要 remediation commits

```text
0ddc90e  fix: 仅在主线程注册Controller信号
9452db0  test: 覆盖Controller停止后的state删除竞态
b84619a  test: 增加真实WMI启动所有权探针
c2c9074  fix: 收敛Controller停止与启动竞态
872053a  test: 拒绝非对象Controller健康响应
87e62c0  test: 对齐Windows venv启动器所有权语义
c0eaf92  fix: 拒绝非对象Controller健康响应
1512b18  fix: 识别venv启动器子进程所有权
9cfb9d0  test: 对齐venv子进程所有权前提
803a2e2  test: 稳定验证共享Controller启动标记
c09e5d3  docs: 清理Controller验收文档空白
e58c5c2  docs: 同步Controller加固最终规格
4f4520e  docs: 同步Controller生命周期实施设计
```

## 最终远端审查 — 2026-09-10

### Spec review

Base→review HEAD 的 changed-file 集合仍为 Controller hardening 计划内 29 个文件，merge-base 仍是固定 Base；没有发现混入无关功能。当前 SPEC 已明确：

- health/listener 不可达不能单独证明 stop 完成；
- shared pending launcher 抑制跨 Bridge 重复 launch；
- Windows venv launcher PID 与 Controller PID 可不同；
- ownership 只在 launcher 存活且父链可证明时成立；
- authenticated health 非 object 受控拒绝；
- stale 不自动 stop/restart/replay；
- custom cleanup 仍以 `started_instance_id` 防误停 replacement。

远端规格复核未发现仍需修复的 Critical / Important 偏离。

### Code-quality review

独立复查 remediation 增量 `61af5ae..4f4520e`，重点检查 signal、stop loop、pending marker、Windows PID ownership、health validation 与测试合同：

- signal handler 仅主线程注册；test-thread 生命周期仍由 stop event 驱动；
- stop listener 断开后继续轮询 state，replacement 检测仍在发新请求前执行；
- pending PID 写入共享 launch-lock 文件，存活 pending 阻止重复 launch；失败 pending 退出后仍允许 cooldown retry；
- venv ownership 不使用 PID 数值强行相等，父链检查失败时保持 false，不扩大清理权限；
- readiness 始终只由 authenticated health 决定；ownership helper 不改变 stale/health 成功条件；
- 非 object health 不再进入 `.get()`；
- 原不稳定的 threaded pending test 已替换为两个条件/状态驱动的行为测试。

未发现新的 Critical / Important 静态 finding。已知保守边界：Windows parent-chain/CIM 查询失败会导致 `started_controller=false`，可能保留 custom Controller，但不会误停未证明归属的实例；该行为与 SPEC 一致，并由最终真实 Windows ownership/lifecycle 验收决定本机是否满足通过条件。

## ACL advisory

第一次验收 doctor exit 0，报告：

```text
controller_data_acl.checked=true
broad_read_principals includes NT AUTHORITY\Authenticated Users
broad_read_principals includes BUILTIN\Users
token_confidentiality_advisory=true
os_isolation=false
```

这是设计允许的 advisory finding。当前版本不会自动改 ACL，也不能描述成 Windows sandbox 或 effective-access proof。

## 决策日志

- **D1** 保留 Controller + disposable Bridge + unique Runtime / `runtime.lock` 架构。
- **D2** stale config / implementation fail-closed，不自动 stop 或 replay。
- **D3** state/health identity 使用 protocol v2。
- **D4** explicit custom `--config` 只清理由当前 invocation 真正启动的同一 `instance_id`；正式配置 persistent。
- **D5** 不提高并行度：1 concurrent / 16 inflight，只做 backpressure。
- **D6** ACL 只做 advisory，不自动写 ACL，不宣称 sandbox。
- **D7** Windows venv WMI 返回的是 redirector launcher PID；ready 仍只信 authenticated health，ownership 通过 launcher 存活 + Controller 后代关系证明。
- **D8** 不用任意 sleep 修并发测试；pending launch 使用条件/状态驱动的确定性测试。
- **D9** 第一次 Final Acceptance 的历史 PASS 不继承到当前 HEAD；所有 required checks 必须在最终精确 HEAD 上重新执行。

## 下一动作

```text
锁定本次 tracker 提交后的精确 branch HEAD
→ 本地 AI 一次性完整执行 LOCAL-ACCEPTANCE.md
→ ChatGPT 按 receiving-code-review 技术复核最终报告
→ 若所有 required evidence PASS，更新 tracker / docs/部署验收.md
→ verification-before-completion
→ 创建 Draft PR
→ 不 merge；最终 merge 由用户决定
```
