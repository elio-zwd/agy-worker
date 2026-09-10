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
routing_direct_cli_fix_head: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
routing_windows_pass_head: 87fb3ddd34c595c0b1be78db1a446711b994895f
routing_chat_thread_red_head: d73d6a4646f7d1cb4818f93a18ea74f31a2fd698
routing_chat_thread_fix_head: 73a2015c04dc84ad0d755cfe4831fb84fe4b6e17
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
previous_real_agy_payload_acceptance: passed
routing_windows_check_at_87fb3dd: exit_0_96_passed_0_failed_0_skipped_0_warnings
real_codex_route_at_87fb3dd: failed_chat_thread_delegation
current_windows_check: not_run
current_real_codex_route: not_run
open_findings: needs_chat_thread_routing_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 已确认的两类真实路由失败

### 1. direct CLI 绕过 Worker

第一次真实 Codex 验收中，用户要求“让 AGY 跑一下编译”，Codex 执行了：

```text
agy --help
agy -p "请在当前项目执行编译验证……"
```

因此旧 `accepted` 状态被撤回。

### 2. chat/thread 绕过 Worker

在 direct CLI 路由修补后，本地 Windows 权威检查于 HEAD `87fb3ddd34c595c0b1be78db1a446711b994895f` 已通过：

```text
scripts/check.ps1: exit 0
pytest: 96 passed / 0 failed / 0 skipped / 0 warnings
working_tree_before: clean
working_tree_after: clean
```

但随后真实 Codex 使用相同自然语言“让 AGY 跑一下编译”时，transcript 显示它把 `AGY` 解释成聊天/代理线程，出现“已列出聊天 / 已向聊天发送消息 / wait threads / 已读取聊天”等动作，最终由该聊天返回编译摘要。

这同样绕过 `Codex → agy_worker MCP → Bridge → Controller → Runtime → AGY CLI`。因此 **`96 passed` 只证明代码回归检查通过，不证明端到端路由目标满足**。

## 当前修补任务

- [x] T5：建立 direct CLI 路由 RED 合同。Commit：`b0c9726830db88500823820994aba0ab0efa5526`。
- [x] T6：加入 managed `developer_instructions` 与 MCP description/server instructions。Commit：`13293e9fb2bbd309e0e9ee96929699514f5bdcf9`。
- [x] T7：修正 direct CLI 禁止措辞；本地后续回归在 `87fb3dd` 得到 `96 passed / 0 failed`。生产措辞修补 Commit：`be29e8c78836deed4ccf88864cace5e1fc5dc7c2`。
- [x] T8：技术复核第二次真实失败。根因不是 compact payload，也不是 direct CLI 禁止失效，而是旧路由规则没有排除“把 AGY 当成 Codex chat/thread/subagent”的替代解释。
- [x] T9 RED：新增回归合同，要求“让 AGY 跑一下编译”显式绑定 `agy_worker`，并要求路由规则覆盖聊天、线程、agent、subagent 歧义。Commit：`d73d6a4646f7d1cb4818f93a18ea74f31a2fd698`。
- [x] T10 GREEN：`developer_instructions`、`agy_worker` / `agy_capabilities` descriptions、MCP server instructions 和仓库规则同步声明：在 Worker 支持任务中 `AGY/agy` **只指本机 `agy_worker` MCP**；不得列出/读取聊天或线程，不得向聊天/subagent 发消息或等待 thread。Commit：`73a2015c04dc84ad0d755cfe4831fb84fe4b6e17`。
- [ ] T11 当前 HEAD Windows 全量回归：`scripts/check.ps1` 必须 exit `0`、0 failed；`git diff --check` exit `0`。
- [ ] T12 重新注册：执行 `scripts/register.ps1`，确认 managed routing block 只有一份并包含 chat/thread 排除语义。
- [ ] T13 新 Codex 会话真实路由：仍只说“让 AGY 跑一下编译”，必须直接进入 `agy_worker` MCP 链；不得出现 direct AGY CLI，也不得出现 list/read/send/wait chat/thread/subagent 作为 AGY 路由。
- [ ] T14 低上下文复核：成功路径不无条件读取完整 artifacts；若 UI 提供 context/token 数值则记录为补充证据。
- [ ] T15 ChatGPT 收到本地报告后按 `receiving-code-review` 技术复核；全部门禁满足后才恢复 `accepted`。

## 设计取舍

当前**没有**通过 `agents.enabled=false` 全局关闭 Codex 多代理能力；那会影响与 AGY 无关的正常多 AI 协作，范围明显过大。

当前也没有设置 `mcp_servers.agy_worker.required=true`。该配置会在 MCP 无法初始化时使 Codex 启动/恢复失败，不适合作为只针对自然语言路由歧义的第一修复。若显式语义绑定仍无法稳定命中，再基于真实 transcript 评估更强的 hook/requirements 机制，而不是提前扩大副作用。

## 保留的旧验收事实

此前真实 `jianyu_lint_assemble` 仍证明**只要请求进入 MCP**，v0.3.2 compact contract 工作正常：

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
