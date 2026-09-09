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

> 说明：用户在 T1 后明确选择“远端连续开发，最后一次性本地验收”。因此 T2～T9 不再以每 Task 本地 RED/GREEN 打断开发；这不表示测试已通过，只表示可执行测试已随实现提交，最终由 `LOCAL-ACCEPTANCE.md` 在同一个最终 HEAD 上统一验证。

## 当前总状态

```text
phase: final_remote_review_complete_waiting_local_acceptance
production_code_changed: true
user_plan_approval: approved_2026-09-09
remote_spec_review: completed_with_findings_fixed
remote_code_quality_review: completed_with_findings_fixed
fresh_windows_verification_for_current_head: pending
open_pr: none
merge_authorized: false
```

### 证据边界

- 历史 T1 RED 已由本地 AI 实际执行并确认缺陷；规划期间也收到过 T1 的局部 GREEN 输出。
- 分支随后继续发生 T1 review fix、T2～T9 实现及最终质量修正，因此**历史执行不能证明当前最终 HEAD 通过**。
- 当前最终树的权威证据必须重新执行 `LOCAL-ACCEPTANCE.md`：定向 pytest、`scripts/check.ps1`、fresh 双 Bridge/WMI lifecycle、custom-config ownership、ACL doctor、`git diff --check`。
- 仓库当前没有 GitHub Actions workflow 可替代 Windows 本地验收。
- 正式 AGY / HBuilderX / Android 不属于本次 Controller hardening 的必要通过条件，除非最终验收发现实现实际触及对应链路。

## 任务总览

| ID | Priority | 任务 | 远端状态 | Windows 最终执行 |
|---|---|---|---|---|
| T1 | P0 | Controller v2 身份 / stale config & implementation | `awaiting_acceptance` | pending final rerun |
| T2 | P0 | 跨协议显式 stop + `--config` stop | `awaiting_acceptance` | pending |
| T3 | P0 | 启动锁 takeover / launch retry / WMI PID | `awaiting_acceptance` | pending |
| T4 | P0 | custom `run-task --config` ownership / cleanup | `awaiting_acceptance` | pending |
| T5 | P1 | status reconnect / MCP timeout budget | `awaiting_acceptance` | pending |
| T6 | P1 | inflight backpressure / queued cancel | `awaiting_acceptance` | pending |
| T7 | P1 | Controller data_dir ACL advisory | `awaiting_acceptance` | pending doctor + pytest |
| T8 | P2 | package/version/request_id/cleaning docs sync | `awaiting_acceptance` | pending |
| T9 | Gate | fresh lifecycle + full verification + handoff | `awaiting_acceptance` | pending; Draft PR intentionally not created |

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
```

历史本地 RED：

```text
tests/test_controller_security.py: 11 failed（预期缺失行为）
tests/test_controller.py -k "stale or identity": identity 缺失行为被捕获
```

当前最终 HEAD：重新执行，不沿用旧结果。

## T2 — 跨协议显式 stop

**交付在分支：** legacy management state；业务 call protocol strict；v1 stored-protocol stop；v2 authenticated stop；`manage stop --config`；`stop.ps1 -Config`；replacement 防误停；等待 state/health 终态。

主要提交：

```text
bfae4bd   test: 添加跨协议Controller停止RED用例
059c269   fix: 支持按旧协议显式停止Controller
a4d8368   fix: 支持指定配置停止Controller
8273e2a   fix: 让stop脚本转发Runtime配置
aa3b66e   fix: 解耦Controller停止与业务协议校验
```

最终执行：pending。

## T3 — launch takeover / retry

**交付在分支：** deadline 驱动 launch lock 重抢；double-check health；≥0.5s cooldown；WMI `ProcessId`；readiness 仍只信 authenticated health；多次 WMI launch 使用独立 environment file。

主要提交：

```text
48540db   test: 添加Controller启动接管RED用例
018a71d   fix: 支持Controller启动锁接管与重试
8037f30   test: 添加Controller最终质量回归用例
9a25658   test: 覆盖Controller环境文件清理
f4ebaa0   fix: 隔离Controller重试环境文件
```

最终执行：pending。

## T4 — custom run-task ownership

**交付在分支：** explicit custom config ownership；pre-existing preserved；owned instance finally cleanup；`--keep-controller`；replacement instance protection；默认正式 config 继续 persistent。

主要提交：

```text
4d54684   test: 添加run-task Controller所有权RED用例
443d003   fix: 记录Controller启动实例所有权
4534a1a   fix: 清理run-task临时Controller生命周期
```

最终执行：pending；最终真实 lifecycle 使用“missing workspace”前置拒绝，不依赖 AGY 登录。

## T5 — reconnect / timeout budget

**交付在分支：** status 第一次连接失败后 `_ensure()` 一次；第二次 `wait_ms=0`；task_id/after_revision 保留；submit/continue request_id 不变；Codex MCP `tool_timeout_sec=60`。

主要提交：

```text
8367278   test: 添加Controller重连预算RED用例
a1c0c18   fix: 调整Codex MCP工具超时预算
6bb2151   fix: 收敛Controller重连等待预算
```

最终执行：pending。

## T6 — inflight backpressure / queued cancel

**交付在分支：** `MAX_CONCURRENT_TASKS=1`；`MAX_INFLIGHT_TASKS=16`；idempotency lookup 在容量 gate 前；第 17 个新请求 `worker_busy` 且无 task/session 副作用；Future 保存；queued Future 可立即 cancel/remove active。

主要提交：

```text
109929a   test: 添加Runtime背压与排队取消RED用例
5923335   fix: 限制任务积压并立即取消排队任务
```

最终执行：pending。

## T7 — `controller_data_acl` advisory

**交付在分支：** pure broad-read classifier；pywin32 DACL inspection；NULL DACL 风险；API 失败 `checked=false`；doctor 输出 `controller_data_acl`；不自动改 ACL；`os_isolation=false` 保持。

主要提交：

```text
bd988db   test: 添加Controller ACL诊断RED用例
61b904d   security: 增加Controller凭据目录ACL诊断核心
c92ed72   security: 接入Controller凭据目录ACL诊断
c5001be   fix: 对齐Controller ACL诊断字段合同
4c3d00a   test: 锁定Controller ACL诊断字段合同
```

最终执行：pending；真实 doctor 结果必须区分 ACL advisory 与 doctor 整体依赖状态。

## T8 — package / docs / contracts

**交付在分支：** package `0.3.1`；`jsonschema==4.26.0` 正式 dependency；MCP server version 取 `implementation_version()`；request_id 全 data_dir 历史唯一 / `req-<uuid4hex>` 推荐；维护者辅助清洗仅为流程；README、实施设计、部署验收同步真实边界。

主要提交：

```text
0ecd597   test: 添加MCP服务版本一致性RED用例
091c9db   fix: 统一MCP服务版本来源
4199eda   fix: 声明jsonschema运行时依赖
cd7617b   docs: 更新示例请求幂等ID
2e791c3   docs: 更新真实项目示例请求ID
9eb9f69   docs: 同步v0.3.1接口和维护边界
2924ab5   docs: 区分v0.3与v0.3.1验收状态
e7144a8   docs: 收敛AGY Worker当前实施边界
```

最终执行：pending；验收前必须刷新 editable package metadata。

## T9 — final verification / handoff

**远端已准备：**

- `scripts/verify-controller.py --config PATH [--fresh] [--stop-after]`；
- 两个 stdio Bridge 的 server/tool 检查；
- Bridge 全退后用 `autostart=False` 验证同 Controller 仍活；
- protocol/instance/PID/max1/max16 checks；
- same-instance `--stop-after`；
- `--fresh` 对 replacement 或“state 存在但不可达”均 fail-closed；
- isolated acceptance config；
- custom-config 三种 ownership 场景；
- final-quality regression tests；
- 一次性本地报告模板。

主要提交：

```text
f73a526   test: 完善Controller生命周期验收脚本
b6c0417   docs: 收敛Controller最终一次性本地验收
8037f30   test: 添加Controller最终质量回归用例
9a25658   test: 覆盖Controller环境文件清理
f4ebaa0   fix: 隔离Controller重试环境文件
efad78d   fix: 让fresh验收拒绝不可达旧状态
8119ab7   docs: 对齐最终验收ACL合同与审查回归
```

**仍未执行 / 不得预判：**

- current final HEAD 的定向 pytest；
- `scripts/check.ps1`；
- fresh WMI 双 Bridge lifecycle；
- custom config no-leak/pre-existing/keep-controller；
- 正式 doctor 的 `controller_data_acl` 真实输出；
- 本地 `git diff --check origin/main...HEAD`；
- Draft PR。

Draft PR 只在最终本地验收报告返回、所有 blocking finding 关闭并更新真实证据文档后创建。

## 远端最终审查记录

### Spec review

逐条对照 `SPEC.md` §5～§16 和 `PLAN.md` T1～T9。已处理的 finding：

1. **Important — ACL 字段名漂移**：实现曾使用 `data_dir_acl`，已统一回已批准合同 `controller_data_acl`，并追加测试。
2. **Documentation — planning 状态过期**：规划入口 / tracker 已改为“远端审查完成、等待最终本地验收”，不把 pending execution 写成 PASS。

当前远端静态规格复核未保留已知 Critical / Important 未处理项；这不是运行验证结论。

### Code-quality / security review

重点复核：state tamper 外联、cross-version stop replacement、防 WMI process storm、Future/active/SQLite 锁顺序、status reconnect 预算、ACL advisory 表述、custom run-task finally cleanup。已处理的 finding：

1. **Important — `--fresh` 不可达 state 误判**：state 存在但 management stop 返回 `controller_unavailable` 时，现返回 `unreachable` 并终止 fresh 验收，不再当 `not_running`。
2. **Important — WMI retry environment-file 竞态**：多次 launch 改为唯一 `controller-environment-<uuid>.json`；超过 5 分钟的异常遗留文件做 best-effort 清理，新鲜文件不动，并有回归测试。

当前远端静态质量复核未保留已知 Critical / Important 未处理项；最终是否可交付仍取决于 Windows 验收。

## 历史本地反馈登记

| Date | Task | Evidence | Finding | ChatGPT 技术判断 | Action |
|---|---|---|---|---|---|
| 2026-09-09 | T1 RED | `tests/test_controller_security.py`: 11 failed；identity/stale 定向测试捕获旧协议/身份缺失 | 符合预期缺失行为，不是 fixture/环境错误 | 接受有效 RED | 写 T1 实现 |
| 2026-09-09 | T1 initial GREEN | `tests/test_controller_security.py`: 11 passed；controller 过滤命令仅运行 3 个测试 | 原过滤表达式漏掉两个 stale 测试，不能据此关闭 T1 | 接受通过部分，拒绝过度结论 | 重命名 stale 测试并追加 health-order RED |

## 决策日志

- **D1** 保留 Controller + disposable Bridge + unique Runtime / `runtime.lock` 架构。
- **D2** stale config / implementation fail-closed，不自动 stop 或 replay。
- **D3** state/health identity 升 protocol v2。
- **D4** explicit custom `--config` 默认只清理由当前 invocation 真正启动的同一 instance；正式配置 persistent。
- **D5** 不提高并行度：1 concurrent / 16 inflight，只做 backpressure。
- **D6** ACL 只做 advisory，不改 ACL，不把它描述成 sandbox/effective-access proof。
- **D7** T2～T9 采用用户批准的远端连续开发 + 最终一次性本地验收；没有最终执行证据前不得宣称完成。

## 下一动作

```text
本地 AI 拉取最终 HEAD
→ 严格按 LOCAL-ACCEPTANCE.md 一次性执行并返回完整报告
→ ChatGPT 按 receiving-code-review 技术复核每条 finding
→ 失败则新增回归测试/修复并重新验收最终树
→ 全部必要证据通过后更新 docs/部署验收.md + 本 tracker
→ 再创建 Draft PR，并由用户决定后续 Ready / merge
```
