# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: routing_fix_awaiting_local_recheck
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
original_production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
previous_test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
previous_validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
routing_test_head: b0c9726830db88500823820994aba0ab0efa5526
routing_code_head: 13293e9fb2bbd309e0e9ee96929699514f5bdcf9
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
previous_windows_check_ps1: passed_91_0
previous_real_agy_payload_acceptance: passed
routing_linux_helper_probe: passed_non_authoritative
routing_windows_check_ps1: not_run
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

### 根因判断

- `manage.register()` 原先只把 `agy_worker` MCP 写入 Codex `config.toml`，没有跨项目的高优先级路由规则。
- MCP 工具 description / server instructions 没有针对“让 AGY/agy”这一真实措辞明确禁止 direct CLI fallback。
- 仅修改 `agy-worker/AGENTS.md` 不能覆盖用户在其他业务仓库启动的 Codex 会话。

## 修补任务

- [x] T5 RED：新增 `tests/test_manage.py`，覆盖保留用户 developer instructions、重复注册幂等、卸载仅清理 managed block、损坏 marker fail-closed、tool description 明确禁止 direct AGY CLI fallback。Commit：`b0c9726830db88500823820994aba0ab0efa5526`。
- [x] T6 GREEN：`manage.register()` 管理 `<AGY_WORKER_ROUTING>` developer-instruction block；加强 `agy_worker` / `agy_capabilities` descriptions 与 server instructions。Commit：`13293e9fb2bbd309e0e9ee96929699514f5bdcf9`。
- [x] T7 远端静态/配置安全复核：相对旧 accepted head 只改 `manage.py`、`server.py`、新增 `test_manage.py`；不改 protocol/tool count/runtime/payload/schema。Linux 纯 helper + TOML round-trip probe PASS，但不作为 Windows 测试完成证据。
- [ ] T8 Windows 全量回归：执行 `scripts/check.ps1`，记录 exit code 与 pytest passed/failed/skipped/warnings。
- [ ] T9 真实 Codex 路由验收：重新执行 `scripts/register.ps1` 后开启新 Codex 会话，使用与失败时相同的自然语言请求，确认调用 `agy_worker` MCP 且 transcript 中没有 `agy --help` / `agy -p` / direct `agy.exe`。
- [ ] T10 低上下文复核：记录新会话开始前后可见 context/token 指标（若 UI 提供）作为补充证据；以工具 transcript 与 Worker terminal evidence 为主，不用 UI 折叠冒充 token 证明。
- [ ] T11 ChatGPT 收到本地报告后按 receiving-code-review 技术复核；全部门禁满足后才恢复 `accepted`。

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

此前 Windows 全量回归仍记录为 `91 passed / 0 failed / 0 skipped / 0 warnings`，但新增 routing 代码和 5 个测试之后必须重新运行，不能沿用旧结果声明当前 head 通过。

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前 `phase=routing_fix_awaiting_local_recheck`，不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。
