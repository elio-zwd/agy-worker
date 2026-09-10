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
| `awaiting_acceptance` | 远端实现与审查完成，但还缺最终 Windows 执行证据 |
| `accepted` | 最终 Windows 验收证据已由 ChatGPT 按 `receiving-code-review` 技术复核通过 |
| `blocked` | 有明确阻断问题，必须记录原因和证据 |

## 当前总状态

```text
phase: accepted_ready_for_draft_pr
production_code_changed: true
user_plan_approval: approved_2026-09-09
base: 904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066
validated_code_head: b00a5a8853336c345fc186bb9049c44931f19149
second_final_acceptance_verdict: PASS
second_final_acceptance_full_check: 77_passed_0_failed_0_skipped_0_warnings
remote_spec_review: completed_no_open_critical_or_important
remote_code_quality_review: completed_no_open_critical_or_important
acceptance_evidence_review: completed_consistent_with_current_code_contract
post_acceptance_changes: documentation_only_acceptance_record
open_pr: pending_draft_creation
merge_authorized: false
```

## 证据边界

最终 Windows 验收针对精确代码/测试 HEAD：

```text
b00a5a8853336c345fc186bb9049c44931f19149
```

环境：Windows 10 Pro 19045 x64、PowerShell 7.6.5、Python 3.13.9、package metadata `0.3.1`，验收开始与结束 tracked worktree 均 clean。

本文件与 `docs/部署验收.md` 的后续提交只记录验收结果，不修改 `src/`、`tests/`、`scripts/`、依赖或配置。按 `AGENTS.md`，仅文档变更无需重复执行无关测试；因此所有“77 passed”与真实 WMI/lifecycle 结论都明确绑定 `validated_code_head=b00a5a8...`，不伪称在验收记录提交之后重新运行过 Windows 全量测试。

第一次 Final Acceptance 在 `61af5ae22241667f3b560e1559fdf360769717e6` 上返回 FAIL；其 65 passed / 6 failed / 6 warnings 仅作为 remediation 历史，不作为最终通过证据。

## 第二次完整 Final Acceptance — 2026-09-10

### 环境与版本

```text
Branch: fix/controller-hardening-v031
HEAD: b00a5a8853336c345fc186bb9049c44931f19149
origin/main: 904b75a6e7b9d0b75c0ae8f63924c3ed0acf5066
Starting git status: clean
Editable install: exit 0
Package metadata: 0.3.1
```

### 定向回归

| Area | Command / evidence | Result |
|---|---|---|
| T1 security | `pytest -q tests/test_controller_security.py` | `17 passed` |
| T1 identity/stale/Bridge/restart | `pytest -q tests/test_controller.py -k "identity or stale or two_stdio or restart"` | `5 passed, 10 deselected` |
| T2 stop/protocol | `pytest -q tests/test_controller.py -k "stop or protocol"` | `4 passed, 11 deselected` |
| T3 launch/takeover/pending/WMI | `pytest -q tests/test_controller.py -k "simultaneous or takeover or launch_retry or wmi_launch or pending_pid"` | `6 passed, 9 deselected` |
| T4 run-task ownership | `pytest -q tests/test_run_task.py` | `3 passed` |
| T5 reconnect | `pytest -q tests/test_controller_reconnect.py` | `4 passed` |
| T6 backpressure/cancel | `pytest -q tests/test_runtime.py` | `13 passed` |
| T8 server/version | `pytest -q tests/test_server.py` | `2 passed` |
| Final quality | `pytest -q tests/test_controller_hardening_quality.py` | `7 passed` |

全部定向回归 exit 0，无 warning/error。

### 权威全量检查

仓库权威入口：

```text
pwsh.exe -NoProfile -File scripts/check.ps1
exit 0
compileall successful
77 passed in 37.92s
failed=0
skipped=0
warnings=0
```

`check.ps1` 的实际实现是先 `python -m compileall -q src`，成功后执行完整 `python -m pytest -q`，因此该证据覆盖最终代码/测试树的全量 pytest。

### Windows venv WMI ownership

真实质量回归：

```text
test_real_wmi_launch_records_controller_ownership: PASS
WMI launcher PID: 63484
Controller state PID: 20020
started_controller: true
started_instance_id: 8e6271364baf445597525d666b2f5b6c
state.instance_id: 8e6271364baf445597525d666b2f5b6c
residual state/process: none
```

PID 数值不同符合 Windows venv redirector 语义。ownership 不是通过 PID 数值相等证明，而是由当前实现的 launcher 存活 + Win32_Process 父链证明，再绑定同一 healthy `instance_id`。这一行为与 SPEC 一致。

### Fresh 双 Bridge lifecycle

`scripts/verify-controller.py --fresh --stop-after`：exit 0，关键结果：

```text
first_server_version=0.3.1
second_server_version=0.3.1
tool_count=6
second_tool_count=6
controller_protocol=2
controller_instance_id_present=true
controller_pid_positive=true
controller_alive_after_bridges=true
max_concurrent_tasks=1
max_inflight_tasks=16
fresh_started_from_clean_target=true
same_instance_stopped_after_verification=true
verification_passed=true
state_after_stop=false
```

### custom `run-task --config` lifecycle

使用不存在的 workspace 让业务请求在前置校验阶段失败，从而不调用真实 AGY，只验证 Controller lifecycle：

- 无 pre-existing Controller：业务 exit 1 为预期；运行后 state=False，owned Controller 无泄漏。
- pre-existing Controller：运行前后 PID/instance_id 均相同；脚本未误停；显式 stop exit 0 后 state=False。
- `--keep-controller`：业务 exit 1 为预期；运行后 state=True；显式 stop exit 0 后最终 state=False。

结论：T4 真实 lifecycle 合同通过。

### ACL advisory

`doctor.ps1` exit 0：

```text
controller_data_acl.checked=true
broad_read_principals:
  - NT AUTHORITY\Authenticated Users
  - BUILTIN\Users
token_confidentiality_advisory=true
os_isolation=false
```

该结果按 SPEC 是**非阻断 advisory**。v0.3.1 不自动修改 ACL，也不声称 Windows sandbox 或完整 effective-access 证明。

### Git integrity

最终验收报告：

```text
Final HEAD: b00a5a8853336c345fc186bb9049c44931f19149
Final git status: clean
fixed-base git diff --check: exit 0, no output
origin/main...HEAD git diff --check: exit 0, no output
29 files changed, 4653 insertions(+), 514 deletions(-)
```

远端再次比较固定 Base→`b00a5a8...`：status `ahead`、behind=0、merge-base 等于固定 Base，changed-file 集合仍为 Controller hardening 计划内 29 个文件。

## 任务总览

| ID | Priority | 任务 | 状态 | 最终 Windows 证据 |
|---|---|---|---|---|
| T1 | P0 | Controller v2 identity / stale config & implementation | `accepted` | security 17 passed；identity/stale/Bridge/restart 5 passed |
| T2 | P0 | 跨协议 stop + `--config` stop | `accepted` | stop/protocol 4 passed；state 删除竞态 quality PASS |
| T3 | P0 | launch takeover / retry / shared pending / WMI launch | `accepted` | launch filter 6 passed；shared pending PASS；真实 WMI ownership PASS |
| T4 | P0 | custom `run-task --config` ownership / cleanup | `accepted` | unit 3 passed；三类真实 lifecycle PASS |
| T5 | P1 | status reconnect / timeout budget | `accepted` | 4 passed |
| T6 | P1 | inflight backpressure / queued cancel | `accepted` | 13 passed |
| T7 | P1 | Controller data_dir ACL advisory | `accepted` | doctor exit 0；advisory 正确报告，`os_isolation=false` |
| T8 | P2 | package/version/request_id/docs | `accepted` | server 2 passed；metadata 0.3.1；两个 diff-check exit 0 |
| T9 | Gate | fresh lifecycle + full verification + handoff | `accepted` | 77/77；fresh lifecycle exit 0；clean git integrity |

## Remediation 历史

### R1 — test-thread signal registration

第一次验收的 background-thread `signal.signal()` 导致 6 failure / 6 warning。修复为仅 Python 主线程注册进程 signal；第二次 Final Acceptance 无相关 warning，T2/T3/T4 全绿。

### R2 — stop/state 删除竞态

有效 RED 证明 health listener 先断开时 `stop_existing()` 曾过早返回。修复为继续轮询目标 state，直到删除、replacement 或 timeout。第二次 Final Acceptance 的 stop/protocol、quality 与 custom no-leak 均通过。

### R3 — Windows venv ownership

真实 Windows 证明 WMI launcher PID 与 Controller PID 可不同。最终实现使用存活 launcher + Win32_Process 父链确认后代关系，查询失败 fail-closed，不冒认 ownership。第二次真实 WMI probe 通过。

### R4 — shared pending launch

废弃依赖线程调度时机的不稳定测试，改为两个确定性行为测试：launch 写共享 pending PID；存活 pending PID 阻止重复 launch。第二次验收均 PASS。

### R5 — authenticated health 非 object

有效 RED 曾泄漏 `AttributeError`。修复为 `.get()` 前要求 JSON object，否则 `controller_state_invalid`。第二次 security suite 17 passed。

### R6 — Git whitespace gate

第一次验收发现 11 处 Markdown trailing whitespace。清理后第二次 fixed-base 与 `origin/main...HEAD` 两个 `git diff --check` 均 exit 0、无输出。

## 最终远端审查

### Spec review

远端最终规格复核没有发现开放的 Critical / Important 偏离：

- stale config / implementation fail-closed，不自动 stop/restart/replay；
- management stop 与 business protocol gate 解耦；
- stop 等待 state 的真实终态；
- shared pending launcher 抑制重复 launch；
- WMI venv ownership 只在可证明父链时成立；
- custom cleanup 使用 `started_instance_id` 防误停 replacement；
- authenticated health 非 object 受控拒绝；
- 1 concurrent / 16 inflight；
- ACL 仅 advisory；
- 公开 MCP 工具仍为 6 个。

### Code-quality review

远端代码质量复核没有发现开放的 Critical / Important finding。已知保守行为是 Windows CIM 父链查询失败会使 `started_controller=false`，倾向于保留 custom Controller 而不是误停未证明归属的实例；本次真实 Windows probe 已证明当前验收环境下该路径正常工作。

## 未验证 / 不在本次范围

第二次 Final Acceptance 明确未执行：

- 真实 AGY 业务任务；
- HBuilderX；
- Android / ADB / 真机；
- 真实 browser 业务流。

这些不属于本次 Controller v0.3.1 hardening 的必要通过条件，不能写成已验证。

## 集成状态

当前可以进入 `finishing-a-development-branch` 的 PR 交付路径：

```text
validated executable tree: b00a5a8853336c345fc186bb9049c44931f19149
final local acceptance: PASS
remote spec/code-quality review: no open Critical/Important
Draft PR: pending creation
merge to main: NOT authorized
branch deletion: NOT authorized
```

最终 merge 由用户决定。