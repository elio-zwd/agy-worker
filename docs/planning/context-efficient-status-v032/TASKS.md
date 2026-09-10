# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: routing_fix_awaiting_local_recheck
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
original_production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
previous_validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
routing_test_head: b0c9726830db88500823820994aba0ab0efa5526
routing_initial_code_head: 13293e9fb2bbd309e0e9ee96929699514f5bdcf9
routing_failed_acceptance_head: c28713f09856331339968a7b5c4856b3e2b9ca6c
routing_fix_head: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
previous_real_agy_payload_acceptance: passed
routing_failed_windows_check: exit_1_95_passed_1_failed_0_skipped_0_warnings
routing_fix_windows_check: not_run
real_codex_routing_transcript: not_run
open_findings: needs_local_routing_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 2026-09-10 新发现：真实 Codex 绕过 Worker

用户在真实 Codex 会话中发送“你让agy跑一下编译”后，transcript 显示 Codex 执行了：

```text
agy --help
agy -p "请在当前项目执行编译验证……"
```

最终编译摘要虽然简洁，但这不是 `agy_worker` MCP 热路径，因此旧的 `accepted` 状态被撤回。该证据说明 PR2 已验证的 payload 压缩与“Codex 实际选择 Worker”是两个独立门禁。

## 路由修补

- [x] T5 RED：新增 `tests/test_manage.py`，覆盖 developer instructions 保留、重复注册幂等、卸载清理、损坏 marker fail-closed、tool description 禁止 direct AGY CLI fallback。Commit：`b0c9726830db88500823820994aba0ab0efa5526`。
- [x] T6 初始 GREEN：`manage.register()` 管理 `<AGY_WORKER_ROUTING>` block；强化 MCP descriptions/server instructions。Commit：`13293e9fb2bbd309e0e9ee96929699514f5bdcf9`。
- [x] T7 首轮本地 Windows 全量检查：在 HEAD `c28713f09856331339968a7b5c4856b3e2b9ca6c` 真实执行 `scripts/check.ps1`，结果 `exit 1 / 95 passed / 1 failed / 0 skipped / 0 warnings`。唯一失败：`tests/test_manage.py::test_register_adds_codex_routing_without_overwriting_existing_instructions`。
- [x] T7.1 技术复核：生产指令原文“不得用 shell/terminal 直接调用”已表达禁止 direct CLI；失败来自测试要求连续子串“不可直接”或“不得直接”。为保留较强测试合同而不弱化断言，生产措辞改为更明确的“不得直接用 shell/terminal 调用”。相对失败 HEAD 只有 `src/agy_worker/manage.py` 一行替换。Commit：`be29e8c78836deed4ccf88864cace5e1fc5dc7c2`。
- [ ] T8 当前 routing fix Windows 全量回归：重新执行 `scripts/check.ps1`，必须实际 exit `0` 且 `0 failed`；同时 `git diff --check` exit `0`。
- [ ] T9 真实 Codex 路由验收：重新执行 `scripts/register.ps1` 后开启新 Codex 会话，使用同样自然语言“你让agy跑一下编译”，确认只走 `agy_worker` MCP，不出现 `agy --help` / `agy -p` / direct `agy.exe`。
- [ ] T10 低上下文复核：记录新会话可见 context/token 指标（若 UI 提供）作为补充证据；主要证据仍为工具 transcript 与 Worker terminal compact result。
- [ ] T11 ChatGPT 收到新本地报告后按 receiving-code-review 技术复核；全部门禁满足后才恢复 `accepted`。

## 保留的旧验收事实

此前真实 `jianyu_lint_assemble` 仍证明**只要请求走进 MCP**，v0.3.2 compact contract 工作正常：

```text
submit: 148B structured / 70B TextContent
running: 148–199B structured / 70–71B TextContent
unchanged: 100B structured / 37B TextContent
terminal: 571B structured / 67B TextContent
operation exit: 0
errors: 0
warnings: 19
terminal stale progress: absent
duplicate_full_json_in_mcp_result: false
```

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前 `phase=routing_fix_awaiting_local_recheck`，不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。
