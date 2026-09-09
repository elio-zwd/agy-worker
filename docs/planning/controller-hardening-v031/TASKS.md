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

> 说明：用户在 T1 后明确选择“远端连续开发，最后一次性本地验收”。2026-09-10 的第一次最终本地验收已真实执行并返回 FAIL；当前进入针对验收 finding 的 remediation，不得再沿用此前“remote review complete”结论。

## 当前总状态

```text
phase: acceptance_failed_remediation_red
production_code_changed: true
user_plan_approval: approved_2026-09-09
previous_acceptance_head: 61af5ae22241667f3b560e1559fdf360769717e6
previous_acceptance_verdict: FAIL
previous_acceptance_full_pytest: 65_passed_6_failed_6_warnings
remediation_signal_fix: committed_0ddc90e57d0fff42eec7c6fc9b745b707b86f5d1
remediation_stop_race_test: committed_9452db0d6163977ebafc8d3f425e0447164532ad_red_pending
remediation_real_wmi_ownership_probe: committed_b84619af7da3a9dbd5e9d2061298ae4b181c1a28_pending
fresh_windows_verification_for_current_head: pending
open_pr: none
merge_authorized: false
```

### 证据边界

- 第一次最终 Windows 验收是在精确 HEAD `61af5ae22241667f3b560e1559fdf360769717e6`、clean worktree 上执行，证据有效。
- 该验收确认 T1 identity/stale/security、T5 reconnect、T6 backpressure/queued cancel、T8 server/version、final quality 旧用例以及 fresh 双 Bridge/WMI lifecycle 通过。
- 同一验收确认 T2/T3/T4 的 6 个 pytest 失败，根因之一是 `controller.run()` 在非主测试线程调用 `signal.signal()`；全量结果为 `65 passed, 6 failed, 6 warnings`。
- 真实 custom `run-task --config` 默认 cleanup 还观察到脚本返回后 `controller.json` 短暂/持续存在；pre-existing preservation 与 `--keep-controller` 场景通过。
- `git diff --check` 在 11 处 tracked Markdown trailing whitespace 上失败；这是独立机械 finding，尚待清理后重新验证。
- ACL doctor 成功执行且报告 `Authenticated Users` / `BUILTIN\\Users` broad-read，`token_confidentiality_advisory=true`；按规格属于 advisory，`os_isolation=false` 保持。
- 当前 remediation HEAD 已不同于第一次验收 HEAD，因此历史 PASS 只能用于定位，不能证明当前树通过。
- 仓库没有 GitHub Actions workflow 可替代 Windows 本地验收。

## 第一次最终本地验收 — 2026-09-10

**Environment:** Windows 10 Pro 19045 x64；PowerShell 7.6.5；Python 3.13.9；package metadata `0.3.1`；branch / HEAD / origin main / fixed base 均与验收合同一致；验收前后 tracked worktree clean。

### PASS evidence

```text
tests/test_controller_security.py
16 passed

tests/test_controller.py -k "identity or stale or two_stdio or restart"
5 passed, 8 deselected

tests/test_controller_reconnect.py
4 passed

tests/test_runtime.py
13 passed

tests/test_server.py
2 passed

tests/test_controller_hardening_quality.py
4 passed

scripts/verify-controller.py --fresh --stop-after
exit 0
verification_passed=true
same_instance_stopped_after_verification=true
state exists after stop=false
```

### Blocking findings accepted after technical review

1. **Controller test-thread signal registration**
   - Evidence: T2/T3/T4 six failures + six `PytestUnhandledThreadExceptionWarning`。
   - Root cause: `ControllerService` 已发布 state 后，`controller.run()` 在 background test thread 无条件执行 `signal.signal()`；Python 抛 `ValueError: signal only works in main thread of the main interpreter`，且异常发生在 `try/finally` 之前，导致 `service.close()` 不执行。
   - Action: `0ddc90e` 仅在当前线程是 main thread 时注册 SIGINT/SIGTERM；真实进程入口仍保持 signal handler。
   - Verification: pending focused Windows rerun。

2. **custom-config default cleanup state 未消失**
   - Evidence: 真实 `scripts/run-task.py --config` 使用预期 `missing-workspace` 业务拒绝，state before=false，script exit=1，state after=true；紧接着显式 stop 成功并使 state=false。
   - Initial ownership hypothesis: 尚未接受；SPEC §9 明确禁止用“启动前无 state”替代 launch PID + healthy instance ownership。
   - Root-cause candidate after tracing: `stop_existing()` 在 `/control/health` 已不可达、但同一目标 `controller.json` 尚未 unlink 时直接返回 `stopped`，可能让 run-task finally 过早结束。
   - Action: `9452db0` 新增 deterministic RED `test_stop_waits_for_state_disappearance_after_health_disconnect`；生产 stop 尚未修改，等待本地 RED 证据。
   - Additional diagnostic: `b84619a` 新增真实 Windows WMI ownership probe，确认 WMI PID / state PID / instance ownership 是否成立。

3. **Git whitespace gate**
   - Evidence: fixed-base 与 `origin/main...HEAD` 的 `git diff --check` 均 exit 2，共 11 行 trailing whitespace。
   - Action: mechanical cleanup pending；不影响业务根因分析，但最终 gate 必须变为 exit 0。

## 任务总览

| ID | Priority | 任务 | 远端状态 | Windows 当前状态 |
|---|---|---|---|---|
| T1 | P0 | Controller v2 身份 / stale config & implementation | `implementing`（controller.py remediation 影响实现摘要） | 61af 上 PASS；current HEAD 待重跑 |
| T2 | P0 | 跨协议显式 stop + `--config` stop | `implementing` | 61af FAIL；signal fix committed，stop-race RED pending |
| T3 | P0 | 启动锁 takeover / launch retry / WMI PID | `implementing` | 61af unit cleanup FAIL；fresh real WMI PASS；signal fix / ownership probe 待验证 |
| T4 | P0 | custom `run-task --config` ownership / cleanup | `implementing` | 61af unit FAIL + real default cleanup FAIL；pre-existing/keep PASS |
| T5 | P1 | status reconnect / MCP timeout budget | `awaiting_acceptance` | 61af PASS；current final rerun required |
| T6 | P1 | inflight backpressure / queued cancel | `awaiting_acceptance` | 61af PASS；current final rerun required |
| T7 | P1 | Controller data_dir ACL advisory | `awaiting_acceptance` | doctor works；broad-read advisory observed |
| T8 | P2 | package/version/request_id/cleaning docs sync | `implementing` | package/server PASS；whitespace gate FAIL |
| T9 | Gate | fresh lifecycle + full verification + handoff | `implementing` | first final acceptance FAIL；PR blocked |

## T1 — Controller v2 身份 / stale 检测

**交付在分支：**

- protocol v2；
- `ControllerState` / `LegacyControllerState` / `ControllerHealth`；
- `config_sha256`、固定常驻模块 `implementation_sha256`、package metadata version；
- per-instance `instance_id`；
- 严格 `http://127.0.0.1:<port>` endpoint；
- authenticated health 后再判断 stale config / implementation；
- state ↔ health identity 一致性；
- stale fail-closed，不自动 stop/replay。

主要实现/审查提交：

```text
1d511a79  fix: 增加Controller身份状态模型
42658007  fix: 升级Controller本地协议版本
64f9d35f  fix: 冻结并发布Controller身份
afba2d80  fix: 严格校验Controller状态与身份
0d3077ab  fix: 让Runtime health返回冻结身份
51b9668   fix: 调整Controller鉴权health验证顺序
895a806   fix: 固定Controller实现摘要模块集合
0ddc90e   fix: 仅在主线程注册Controller信号
```

61af 本地验收：security `16 passed`；identity/stale/two_stdio/restart `5 passed, 8 deselected`。由于 controller.py remediation 改变 implementation digest，current final HEAD 必须最终重跑。

## T2 — 跨协议显式 stop

**交付目标：** legacy management state；业务 call protocol strict；v1 stored-protocol stop；v2 authenticated stop；`manage stop --config`；`stop.ps1 -Config`；replacement 防误停；等待 state/health 终态。

第一次最终验收：`2 failed, 2 passed, 9 deselected`；两个失败都被 background-thread signal 异常污染。signal root 已修；另新增 stop-race RED，等待验证后再决定 stop 生产逻辑。

## T3 — launch takeover / retry

**交付目标：** deadline 驱动 launch lock 重抢；double-check health；≥0.5s cooldown；WMI `ProcessId`；readiness 仍只信 authenticated health；多次 WMI launch 使用独立 environment file。

第一次最终验收：定向 unit `2 failed, 2 passed, 9 deselected`，失败发生在 cleanup 并伴随 signal thread exception；同一验收的 fresh 真实 WMI 双 Bridge lifecycle 完整 PASS。当前追加真实 WMI ownership probe，避免把真实 T4 leak 错归因于 PID。

## T4 — custom run-task ownership

**交付目标：** explicit custom config ownership；pre-existing preserved；owned instance finally cleanup；`--keep-controller`；replacement instance protection；默认正式 config 继续 persistent。

第一次最终验收：unit `2 failed, 1 passed`，两个失败受 signal thread exception 影响；真实 lifecycle 中 default owned cleanup FAIL，pre-existing PASS，`--keep-controller` PASS。当前优先验证 stop-race 与 WMI ownership 两个独立假设。

## T5 — reconnect / timeout budget

61af 验收 `4 passed`。Current final HEAD 最终仍需全量重跑。

## T6 — inflight backpressure / queued cancel

61af 验收 `13 passed`。Current final HEAD 最终仍需全量重跑。

## T7 — `controller_data_acl` advisory

61af doctor exit 0：`checked=true`，broad-read principals 包含 `NT AUTHORITY\\Authenticated Users` 与 `BUILTIN\\Users`，`token_confidentiality_advisory=true`，`os_isolation=false`。这是已知 advisory 风险，不自动改 ACL，不声称 sandbox。

## T8 — package / docs / contracts

61af editable install / metadata `0.3.1` 与 `tests/test_server.py` PASS。当前仍有 Markdown trailing whitespace gate 要清理，最终 `git diff --check` 必须 exit 0。

## T9 — final verification / handoff

第一次最终本地验收结论：**FAIL**。Draft PR 未创建，merge 未授权。

在 remediation 完成前不得进入 finishing branch。下一次最终验收必须针对新的精确 HEAD 重新执行完整 `LOCAL-ACCEPTANCE.md`，不能把 61af 的 PASS 子项直接继承为最终结论。

## 远端审查记录

### Spec / code-quality history

此前远端静态审查处理过 ACL 字段漂移、fresh 不可达 state 误判、WMI retry environment-file 竞态等 finding；第一次真实 Windows 验收证明静态审查仍漏掉 test-thread signal 和 stop/state race，所以当前状态以本地执行证据为准。

### Receiving-code-review — 2026-09-10

对本地 AI 三条 blocking finding 的技术判断：

- signal thread finding：**接受，根因已确认**；
- real custom cleanup finding：**接受症状，拒绝未经验证的 ownership 根因推断**；继续按 stop race + WMI ownership 分离验证；
- trailing whitespace：**接受，机械修复**；
- ACL broad-read：**接受 advisory evidence，非本次自动阻断项**。

## 历史本地反馈登记

| Date | Task | Evidence | Finding | ChatGPT 技术判断 | Action |
|---|---|---|---|---|---|
| 2026-09-09 | T1 RED | `tests/test_controller_security.py`: 11 failed；identity/stale 定向测试捕获旧协议/身份缺失 | 符合预期缺失行为，不是 fixture/环境错误 | 接受有效 RED | 写 T1 实现 |
| 2026-09-09 | T1 initial GREEN | security 11 passed；controller 过滤命令只运行部分测试 | 过滤表达式漏 stale，不能关闭 T1 | 接受部分证据 | 重命名 stale + health-order RED |
| 2026-09-10 | Final acceptance @61af | full `65 passed, 6 failed, 6 warnings`；fresh WMI PASS；custom default cleanup FAIL；diff-check exit2 | signal thread、custom cleanup、whitespace 三项 blocking | 接受 FAIL；分离根因 | remediation in progress |

## 决策日志

- **D1** 保留 Controller + disposable Bridge + unique Runtime / `runtime.lock` 架构。
- **D2** stale config / implementation fail-closed，不自动 stop 或 replay。
- **D3** state/health identity 升 protocol v2。
- **D4** explicit custom `--config` 默认只清理由当前 invocation 真正启动的同一 instance；正式配置 persistent。
- **D5** 不提高并行度：1 concurrent / 16 inflight，只做 backpressure。
- **D6** ACL 只做 advisory，不改 ACL，不把它描述成 sandbox/effective-access proof。
- **D7** 第一次 final acceptance 的 FAIL 优先于此前静态 review 结论；所有 remediation 必须重新有执行证据。

## 下一动作

```text
本地 AI 拉取 remediation HEAD
→ 验证 signal 相关 T2/T3/T4 测试是否转 GREEN
→ 单独执行 stop-race 新测试，预期在生产修复前 RED
→ 执行真实 WMI ownership probe，确定 PID/instance ownership 是否成立
→ ChatGPT 根据证据只修已确认根因
→ 清理 11 处 trailing whitespace 并验证 git diff --check
→ focused remediation 全绿后，再对新的最终 HEAD 完整执行 LOCAL-ACCEPTANCE.md
→ 最终 PASS 后才进入 Draft PR / finishing branch，由用户决定 merge
```
