# AGY Worker v0.3.2 MCP 热路径本地复验

> 给用户本地 AI 的严格验收任务。只验收，不修代码、不修改任何 `AGENTS.md`、不提交、不合并、不删除 branch/data。失败时保留原始证据并返回 ChatGPT。

## 0. 固定对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
PREVIOUS_WINDOWS_PASS_HEAD: 87fb3ddd34c595c0b1be78db1a446711b994895f
ROUTING_UPGRADE_FIX_HEAD: 31119240a5d5388b17f3f0d724644a479ec77b21
MCP_HOT_PATH_RED_HEAD: 7d8594ea16b18d261f07a4fcaba4442e0d7bf0fa
MCP_HOT_PATH_CODE_HEAD: 70577e68e9843b187feeda9080d5ce976c19fbe4
package: 0.3.2
controller protocol: 2
MCP tools: 6
```

`MCP_HOT_PATH_CODE_HEAD` 是当前待验收生产代码。它之后只允许 `README.md` 与 `docs/planning/context-efficient-status-v032/**` 文档变化；若出现新的 `src/`、`tests/`、scripts、config、依赖或 `AGENTS.md` 变化，停止并报告。

## 1. 已知历史证据与本轮目标

旧 HEAD `87fb3ddd34c595c0b1be78db1a446711b994895f` 已真实通过：

```text
scripts/check.ps1: exit 0
pytest: 96 passed / 0 failed / 0 skipped / 0 warnings
working_tree before/after: clean
```

之后真实 Codex 曾把 AGY 错当 chat/thread。用户在业务项目现有 `AGENTS.md` 中加入简短的“AGY是MCP”后，最新真实请求“使用AGY跑编译测试”已经正确进入 `agy_capabilities → agy_worker → agy_status`，因此本轮**不再改 Agents 路由**，只验 MCP 热路径是否减少无效上下文。

该次真实 transcript 同时暴露：

- MCP 前先跑 `git status / branch / log / rg AGY`；
- `agy_capabilities` 返回 Controller、limits、permissions、全部 workspace/worktree 等完整冷数据；
- queued/unchanged 期间存在重复状态轮询和用户可见解释。

本轮目标：已知映射时直接 `agy_worker`；未知映射时最多一次紧凑 `agy_capabilities`；完整诊断留给冷资源；queued/running 使用 25 秒 long-poll，unchanged 不逐轮解释。

## 2. 安全前置与当前 HEAD

在 `D:\My\_Elio\agy-worker`：

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '70577e68e9843b187feeda9080d5ce976c19fbe4'
git merge-base --is-ancestor $Target HEAD
Write-Host "mcp_hot_path_code_is_ancestor exit=$LASTEXITCODE"
git diff --name-only "$Target..HEAD"
git status --short
```

要求：

- 工作区开始时 clean；
- ancestor exit `0`；
- target 之后只能出现 `README.md` 和本 planning 目录文档；
- **不要修改任何业务项目或 agy-worker 的 `AGENTS.md`。**

## 3. 当前 HEAD 权威回归

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"

git diff --check 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD'
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

记录真实 exit code、passed/failed/skipped/warnings、compileall。必须 `scripts/check.ps1 exit 0`、`0 failed`、`git diff --check exit 0`。历史 `96 passed` 不能代替当前证据。

## 4. MCP 热/冷 capabilities 边界

正常 Codex 热路径不要为了验收主动读取冷资源。先在独立只读 probe 中核对 MCP server 行为；可以复用项目 `.venv` 导入 `agy_worker.server`，但不得改配置或源码。

必须确认热工具 `agy_capabilities` 的 structured result：

- 顶层仅 `schema_version`、`workspaces`；
- workspace 仅 `workspace_id`、`registered_path`、`allowed_commands`；
- 只有存在额外 worktree 时才允许 `known_worktrees`；
- 不得出现 `controller`、`limits`、`permissions`、`git`、`supports_worktrees`、`usage`。

冷资源保持能力：

- `agy://capabilities` 仍包含 `enabled_kinds`、`controller`、`limits`、`permissions` 和完整 workspaces；
- `agy://workspaces` 仍可包含 `git`、`supports_worktrees`、`known_worktrees` 等完整工作区诊断。

如能记录 UTF-8 JSON 字节数，分别记录热 `agy_capabilities` 与旧 transcript 中完整 payload 的字节数；这是补充指标，不代替字段合同。

## 5. 新 Codex 会话真实热路径

使用**已经存在“AGY是MCP”规则的业务项目当前状态**，不要再编辑 Agents。新开 Codex 会话，只发送：

```text
使用AGY跑编译测试
```

保存可见 transcript 和工具顺序。

### PASS 条件

必须满足正确性：

1. 使用 `agy_worker` MCP，不走 chat/thread/subagent，也不 direct `agy/agy.exe/agy -p`。
2. 编译/测试结论来自 Worker terminal operation/exit code；成功路径不无条件读取完整 artifacts。

同时记录热路径效率：

3. 不应仅为“确认 AGY、入口或映射”先跑 `git branch`、`git log`、`rg AGY`、`agy --help`。若确有业务项目自身规则要求 `git status` 等安全检查，原样记录规则/理由，不把它和 AGY discovery 混为一谈。
4. 新会话若不知道 workspace/command，允许调用**一次** `agy_capabilities`；其 structured result 必须符合第 4 节紧凑合同。若映射已经明确，则应直接 `agy_worker`。
5. `agy_status` 在 queued/running 后应优先使用上次 `revision` 作为 `after_revision` 且 `wait_ms=25000`。若 UI 不展示参数，记录 `unknown`，不要猜。
6. `unchanged` 后无需每轮输出“我继续等待”等面向用户解释；直接继续 long-poll 即可。
7. 若再次长时间 queued，不得改用 CLI 绕过；把 queue wait 作为独立现象报告，不在本轮自行修改 Controller。

可选补充：同一 Codex 会话完成/结束第一轮后再发一次等价请求，观察已知 workspace/command 后是否跳过 `agy_capabilities`。该项用于评估进一步优化，不作为本轮硬性 PASS 门禁。

## 6. 返回 ChatGPT 的报告模板

```text
branch_head:
mcp_hot_path_code_is_ancestor:
post_code_changed_files:
working_tree_before:

scripts_check_exit:
pytest_passed:
pytest_failed:
pytest_skipped:
pytest_warnings:
compileall:
git_diff_check_exit:

hot_capabilities_top_keys:
hot_workspace_keys:
hot_has_controller: yes/no
hot_has_limits: yes/no
hot_has_permissions: yes/no
hot_has_git_flags: yes/no
hot_capabilities_bytes_if_measured:
cold_capabilities_full_preserved: yes/no
cold_workspaces_full_preserved: yes/no

new_codex_session: yes/no
natural_language_request:
observed_tools_in_order:
pre_mcp_shell_seen: yes/no
pre_mcp_shell_commands:
pre_mcp_shell_reason_if_known:
capabilities_call_count:
capabilities_structured_keys:
agy_worker_seen: yes/no
status_calls:
status_after_revision_seen: yes/no/unknown
status_wait_25000_seen: yes/no/unknown
unchanged_user_narration_seen: yes/no
direct_agy_cli_seen: yes/no
chat_thread_subagent_route_seen: yes/no
worker_terminal_status:
operation_exit_code:
artifact_reads:
queue_wait_if_observed:
context_before_if_visible:
context_after_if_visible:

optional_second_request_capabilities_count:
working_tree_after:
open_findings:
overall_recheck: PASS/FAIL
```

本地 AI 只验收，不修代码。失败时保留 transcript、命令输出与 exit code，交回 ChatGPT 技术复核。
