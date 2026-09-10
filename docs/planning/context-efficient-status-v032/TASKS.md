# AGY Worker v0.3.2 低上下文状态 Task Tracker

> 本文件是 `perf/context-efficient-status-v032` 的**唯一当前进度状态源**。
> Base：`b51d81701f3cfe3859c485f87e42a03b22b4e3d7`

## 当前总状态

```text
phase: mcp_hot_path_awaiting_local_recheck
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
original_production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
previous_validated_head: 4e555315cbdc187f905c6222c2a8432b3feef077
routing_direct_cli_fix_head: be29e8c78836deed4ccf88864cace5e1fc5dc7c2
routing_windows_pass_head: 87fb3ddd34c595c0b1be78db1a446711b994895f
routing_chat_thread_fix_head: 73a2015c04dc84ad0d755cfe4831fb84fe4b6e17
routing_upgrade_fix_head: 31119240a5d5388b17f3f0d724644a479ec77b21
mcp_hot_path_red_head: 7d8594ea16b18d261f07a4fcaba4442e0d7bf0fa
mcp_hot_path_code_head: ec69cde0ebb1f3c2870f2af1cbaa53c31198f7b6
mcp_hot_path_docs_head: 02efd9f00bb0716476d6491e449384624bfcd0b9
package: 0.3.2
controller_protocol: 2
mcp_tool_count: 6
previous_real_agy_payload_acceptance: passed
routing_windows_check_at_87fb3dd: exit_0_96_passed_0_failed_0_skipped_0_warnings
real_codex_route_at_87fb3dd: failed_chat_thread_delegation
real_codex_route_with_business_agents_alias: passed_mcp_route
observed_preflight_at_alias_run: git_status_branch_log_rg_before_mcp
observed_capabilities_at_alias_run: full_cold_payload_returned
observed_queue_wait_at_alias_run: queued_approximately_75_seconds
current_windows_check: not_run_after_mcp_hot_path
current_real_mcp_hot_path: not_run
open_findings: needs_mcp_hot_path_recheck
merge_authorized: false
open_pr: "#2_draft"
```

## 已确认的路由事实

此前真实 Codex 曾先后出现 direct `agy -p` 和 chat/thread 两种绕过，因此 PR #2 增加了路由绑定和 managed block 升级。随后用户在业务项目 `AGENTS.md` 中加入简短的“AGY是MCP”后，真实请求“使用AGY跑编译测试”已经实际进入 `agy_capabilities → agy_worker → agy_status` MCP 链，不再走 direct CLI 或 chat/thread。

这说明当前剩余重点已从“能否命中 MCP”转为“命中后是否足够省上下文”。用户明确要求本轮继续修改 MCP，**暂不修改 AGENTS**。

## 新观测：MCP 热路径仍有浪费

这次真实 MCP transcript 暴露了三类开销：

1. Codex 在调用 MCP 前执行组合 shell：`git status --short; git branch --show-current; git log -5 --oneline; rg ... "AGY|agy" ...`。其中为定位 AGY/MCP 而做的 branch/log/rg 探测对 Worker 路由没有价值。
2. `agy_capabilities` 把全部 workspace、known worktrees、Controller、limits、permissions 等完整冷数据作为 structured result 返回。按用户本轮实际三 workspace 数据估算，原 compact JSON 约 `1420B`；只保留路由字段约 `700B`。
3. queued 状态约 75 秒内多次 long-poll。unchanged envelope 本身已经很小，主要优化点是使用 `after_revision + wait_ms=25000` 并避免每次 unchanged 前后生成解释文字，而不是扩大 status payload。

75 秒 queued 只记录为并发现象，本轮不把它与 token 优化混成 Controller 生命周期修改；Controller 仍是单执行槽。

## 当前 MCP 热路径修补

- [x] T16 设计收敛：不改 Runtime/Controller，不新增工具，不修改公开请求 schema。Controller 继续产生完整 capabilities；仅在 MCP server 出口做热/冷投影。
- [x] T17 RED 合同：新增 `tests/test_mcp_hot_path.py`，以 MCP consumer-visible 行为验证：`agy_capabilities` 热工具只返回路由投影；`agy://capabilities` 和 `agy://workspaces` 冷资源仍保留完整诊断/worktree。最终 RED 版本：`7d8594ea16b18d261f07a4fcaba4442e0d7bf0fa`。ChatGPT Web 未执行 Windows RED，不把“已观察失败”写成事实。
- [x] T18 GREEN：`server.py` 增加 `_routing_capabilities()`；热工具保留 `schema_version`、`workspace_id`、`registered_path`、`allowed_commands`，仅存在额外 Git worktree 时保留 `known_worktrees`；Controller/limits/permissions 等仅留在冷资源。Commit：`ec69cde0ebb1f3c2870f2af1cbaa53c31198f7b6`。
- [x] T19 MCP 调用提示瘦身：已知 workspace/command 时直接 `agy_worker`；未知时才调用一次 `agy_capabilities`；不要仅为定位 AGY/MCP 先跑 git branch/log、`rg AGY`、`agy --help`。`agy_status` 对 queued/running 推荐 `after_revision + wait_ms=25000`，unchanged 静默继续。
- [x] T20 兼容性自审：保留 `agy_worker` description 中 direct `agy.exe`、MCP unavailable、chat/thread/subagent 防绕过语义；参数校验失败时原 `agy_capabilities` hint 保持不变；不改六工具、schema、Runtime、Controller、权限。
- [x] T21 README 同步：`02efd9f00bb0716476d6491e449384624bfcd0b9`。
- [ ] T22 当前 HEAD Windows 全量回归：`scripts/check.ps1` 必须 exit `0`、0 failed；`git diff --check` exit `0`。
- [ ] T23 真实 MCP 热路径：新 Codex 会话使用业务项目现有“AGY是MCP”规则，发送“使用AGY跑编译测试”；记录是否还有无意义 AGY-discovery shell、capabilities 实际字段、status 调用参数/叙述。
- [ ] T24 capabilities 冷热验收：真实 `agy_capabilities` 不应再返回 `controller`、`limits`、`permissions`、`git`、`supports_worktrees`；需要诊断时 `agy://capabilities` / `agy://workspaces` 仍应完整。
- [ ] T25 ChatGPT 收到本地证据后执行 `receiving-code-review` + `verification-before-completion`；全部门禁满足后才恢复 `accepted`。

## 设计取舍

本轮不修改任何 `AGENTS.md`。用户业务项目里已有的“AGY是MCP”继续作为当前真实路由条件，但本 PR 的 MCP 仍保留自身最小防绕过描述。

本轮不自动推断 `workspace_id` / `command_id`，也不新增默认命令配置。同一 workspace 可登记多个命令，自动猜错的风险高于一次紧凑 capabilities 查询。

本轮不增加 `agy_status` 最大等待时间、不改 Controller HTTP timeout，也不碰单执行槽。unchanged 已是约百字节级热返回；先用现有 25 秒 long-poll 和更少叙述获得低风险收益。

## 保留的 compact payload 验收事实

此前真实 `jianyu_lint_assemble` 已证明**请求进入 MCP 后**，v0.3.2 status/result compact contract 正常：

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
