# AGY Worker v0.3.2 Context-Efficient Status Hub

本目录是 `perf/context-efficient-status-v032` 的跨对话持久上下文。目标是让 Codex 默认只接收足够做下一步判断的摘要，完整诊断按需从 artifact 读取，并确保用户明确说“让 AGY/agy 做任务”时不会绕过 Worker 直接执行 AGY CLI。

## 阅读顺序

1. `SPEC.md` — compact status/result 合同、字节预算和原始完成定义。
2. `TASKS.md` — **唯一当前进度状态源**。
3. `LOCAL-ROUTING-RECHECK.md` — 2026-09-10 真实 Codex 绕过 MCP 后的新增复验协议。
4. `LOCAL-ACCEPTANCE.md` — 首轮 Windows + 真实 AGY payload 验收。
5. `LOCAL-RECHECK.md` — 首轮测试回归修正后的复验记录。
6. `PLAN.md` — 原始 T1～T4 实施计划。

## 当前状态

```text
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
branch: perf/context-efficient-status-v032
phase: routing_fix_awaiting_local_recheck
routing_test_head: b0c9726830db88500823820994aba0ab0efa5526
routing_code_head: 13293e9fb2bbd309e0e9ee96929699514f5bdcf9
package: 0.3.2
controller protocol: 2
MCP tools: 6
previous Windows scripts/check.ps1: PASS, 91 passed / 0 failed
previous real AGY payload acceptance: PASS
new routing Windows check: not_run
new real Codex routing transcript: not_run
merge authorized: false
open PR: #2 (Draft)
```

## 为什么重新打开完成门禁

此前 direct MCP probe 已证明 compact payload 生效：submit 148B、running 148–199B、自然 unchanged 100B、terminal 571B，且没有完整 JSON 的 TextContent + structuredContent 双份。随后用户在真实 Codex 会话中发送“你让agy跑一下编译”，实际 transcript 却出现：

```text
agy --help
agy -p "...编译验证..."
```

这条路径直接绕过 `agy_worker → Controller → Runtime`，所以此前 payload PASS 仍然有效，但不能证明最终“低上下文真实使用”目标已经闭环。

## 本次修补

`routing_code_head` 增加三层约束：

1. `agy_worker.manage register` 在 Codex `config.toml` 的 `developer_instructions` 中追加一个短小、带 `<AGY_WORKER_ROUTING>` 边界的路由块；保留用户既有指令，重复注册不重复追加，卸载只删除本 Worker 管理的块，标记损坏时 fail-closed。
2. `agy_worker` / `agy_capabilities` tool description 明确告诉 Codex：用户要求 AGY 执行已支持任务时应走 MCP，不得直接 `agy/agy.exe/agy -p`，MCP 不可用时不得静默回退。
3. MCP server initialization instructions 同步相同路由边界。

不改变 package 0.3.2、Controller protocol 2、六个 MCP 工具、权限、Runtime、payload compact 合同或 AGY 执行语义。

## 当前证据边界

- 已通过远端 diff/static review：修补相对旧 accepted head 仅涉及 `manage.py`、`server.py`、新增 `tests/test_manage.py`，随后只允许本目录 planning 文档和 `AGENTS.md` 说明更新。
- 已在 ChatGPT 可执行的 Linux 环境对路由块 install/remove/idempotence 与 TOML round-trip 做最小纯逻辑检查；这不是仓库完整 pytest，也不是 Windows 证据。
- **尚未执行**当前 routing head 的 Windows `scripts/check.ps1`。
- **尚未执行**重新注册后的真实 Codex transcript 验收。

因此当前不是 `accepted`。下一步严格按 `LOCAL-ROUTING-RECHECK.md` 由本地 AI 验收；返回证据后再由 ChatGPT 技术复核。

未经用户明确授权，不 merge `main`、不删除 feature branch、不启用 auto-merge、不重写历史。
