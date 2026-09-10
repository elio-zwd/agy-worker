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
routing_direct_cli_fix_head: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
routing_windows_pass_head: 87fb3ddd34c595c0b1be78db1a446711b994895f
routing_chat_thread_red_head: d73d6a4646f7d1cb4818f93a18ea74f31a2fd698
routing_chat_thread_fix_head: 73a2015c04dc84ad0d755cfe4831fb84fe4b6e17
routing_upgrade_red_head: 365da956791f562d2989286e363e855eeb94a2e6
routing_target_head: 31119240a5d5388b17f3f0d724644a479ec77b21
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
previous_real_agy_payload_acceptance: passed
routing_windows_check_at_87fb3dd: exit_0_96_passed_0_failed_0_skipped_0_warnings
real_codex_route_at_87fb3dd: failed_chat_thread_delegation
current_windows_check: not_run
current_register_upgrade_check: not_run
current_real_codex_route: not_run
open_findings: needs_target_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 已确认的真实路由失败

### 1. direct CLI 绕过 Worker

第一次真实 Codex 验收中，用户要求“让 AGY 跑一下编译”，Codex 执行了：

```text
agy --help
agy -p "请在当前项目执行编译验证……"
```

这绕过 `agy_worker` MCP，因此旧 `accepted` 状态被撤回。

### 2. chat/thread 绕过 Worker

修补 direct CLI 后，本地 Windows 权威检查在 `87fb3ddd34c595c0b1be78db1a446711b994895f` 真实得到：

```text
scripts/check.ps1: exit 0
pytest: 96 passed / 0 failed / 0 skipped / 0 warnings
working_tree_before: clean
working_tree_after: clean
```

但随后真实 Codex 对“让 AGY 跑一下编译”仍出现“已列出聊天 / 已向聊天发送消息 / wait threads / 已读取聊天”，把 `AGY` 当成聊天/代理线程而不是 `agy_worker` MCP。因此 `96 passed` 只证明该 HEAD 的代码回归检查通过，不证明端到端路由目标通过。

## 当前修补

- [x] direct CLI 路由规则与测试：禁止正常 AGY 任务通过 shell/terminal 执行 `agy --help`、`agy -p`、direct `agy.exe`。
- [x] chat/thread RED：`d73d6a4646f7d1cb4818f93a18ea74f31a2fd698`。测试要求“让 AGY 跑一下编译”显式绑定 `agy_worker`，并覆盖聊天、线程、agent、subagent 歧义。
- [x] chat/thread GREEN：`73a2015c04dc84ad0d755cfe4831fb84fe4b6e17`。`developer_instructions`、MCP tool descriptions/server instructions 与 `AGENTS.md` 同步声明：Worker 支持任务里的 `AGY/agy` **只指本机 `agy_worker` MCP**；不得通过 list/read/send/wait chat/thread/subagent 寻找或委派所谓 AGY。
- [x] managed-block upgrade RED：`365da956791f562d2989286e363e855eeb94a2e6`。机器已安装旧 `<AGY_WORKER_ROUTING>` 时必须能升级，而不是把正常旧版本误判为损坏。
- [x] managed-block upgrade GREEN：`31119240a5d5388b17f3f0d724644a479ec77b21`。唯一且完整、位于 `developer_instructions` 末尾的 managed block 可原位替换为当前规则；用户前置指令原样保留。标记缺失配对、重复、位置异常仍 fail-closed。
- [ ] 当前 target Windows 全量回归：`scripts/check.ps1` exit `0`、0 failed；`git diff --check` exit `0`。
- [ ] 真实注册升级：当前机器已有旧路由块时，`scripts/register.ps1` 必须 exit `0`，升级后 begin/end 各一份、chat/thread 绑定规则存在；重复注册仍幂等。
- [ ] 新 Codex 会话端到端验收：只发送“让 AGY 跑一下编译”，必须进入 `agy_worker` MCP；不得 direct AGY CLI，也不得通过聊天/线程/agent/subagent 路由。
- [ ] 成功路径低上下文复核：只读下一步需要的 compact hot path；无需要时不读取完整 artifacts。
- [ ] ChatGPT 收到本地证据后再按 `receiving-code-review` + `verification-before-completion` 判断是否恢复 `accepted`。

## 设计取舍

当前不使用 `agents.enabled=false` 全局关闭 Codex 多代理能力，因为会伤及与 AGY 无关的正常多 AI 协作。

当前也不设置 `mcp_servers.agy_worker.required=true`；该配置会扩大到所有 Codex 启动/恢复。若当前明确语义绑定在真实新会话里仍不能稳定命中，再根据 transcript 评估更强机制，不提前扩大副作用。

## 保留的 compact payload 验收事实

此前真实 `jianyu_lint_assemble` 已证明**请求进入 MCP 后**，v0.3.2 compact contract 正常：

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

完整当前复验协议：`LOCAL-ROUTING-RECHECK.md`。

## Merge Gate

```text
merge_authorized: false
```

PR #2 保持 Draft。当前不得描述为完成或可合并；未经用户明确授权，不 merge `main`、不删除 branch、不启用 auto-merge、不重写历史。
