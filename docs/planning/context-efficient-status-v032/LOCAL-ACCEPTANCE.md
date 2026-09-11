# AGY Worker v0.3.2 本地 Windows / 真实 AGY 验收协议

> 这是给用户本地 AI 的**只读验收任务**。不要修改源码、不要修复问题、不要提交、不要合并、不要删除 branch/worktree/data。发现失败时保存证据并报告给 ChatGPT，由远端主开发 AI 按 `receiving-code-review` 判断和修复。

## 0. 固定验收对象

```text
repository: elio-zwd/agy-worker
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
TARGET_CODE_HEAD: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
package target: 0.3.2
controller protocol target: 2
MCP tool count target: 6
```

`TARGET_CODE_HEAD` 是本轮最后一个生产代码 commit。它之后允许存在 `docs/planning/context-efficient-status-v032/**` 的纯文档 handoff commit；如果最新远端 branch 在 `TARGET_CODE_HEAD` 之后还有**任何源码、测试、脚本、配置、pyproject 或非 planning 文档变化**，不要继续验收，直接报告 HEAD 与文件列表，避免测错候选代码。

## 1. 安全前置检查

在 `D:\My\_Elio\agy-worker` 执行。先确认没有用户未提交工作：

```powershell
Set-Location 'D:\My\_Elio\agy-worker'
git status --short
```

- 若输出非空：**不要 stash/reset/clean/checkout 覆盖用户内容**。停止并报告现有变更。
- 若为空：继续。

更新远端引用并切到目标 branch：

```powershell
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only origin perf/context-efficient-status-v032
$Head = (git rev-parse HEAD).Trim()
$Target = '2b9ef842e4eb52bed7c00e6e57505a0c09a64852'
$Base = 'b51d81701f3cfe3859c485f87e42a03b22b4e3d7'
Write-Host "branch HEAD=$Head"
git diff --name-only "$Target..$Head"
```

如果 `$Head -ne $Target`，上面的 diff 只能出现：

```text
docs/planning/context-efficient-status-v032/...
```

否则停止并报告。

同时记录：

```powershell
git log -1 --oneline $Target
git status --short
```

## 2. 安装/刷新当前 v0.3.2 环境

使用仓库现有安装入口，不改全局 Python：

```powershell
pwsh.exe -NoProfile -File scripts/install.ps1
```

若失败，记录完整错误与 exit code，不继续伪造后续 PASS。

确认 package metadata：

```powershell
.venv\Scripts\python.exe -c "from importlib.metadata import version; print(version('elio-agy-worker'))"
```

必须得到：

```text
0.3.2
```

确认协议常量与公开工具数量可在后续 verifier / MCP capabilities 中证明为：

```text
protocol_version = 2
MCP tools = 6
```

## 3. 权威仓库检查

执行仓库 `AGENTS.md` 指定的权威检查：

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
$CheckExit = $LASTEXITCODE
Write-Host "scripts/check.ps1 exit=$CheckExit"
```

必须原样记录：

- exit code；
- pytest `passed / failed / skipped / warnings` 数字；
- compileall 是否报错；
- 任何 warning/error 原文。

随后运行：

```powershell
git diff --check "$Base..HEAD"
$DiffExit = $LASTEXITCODE
Write-Host "git diff --check exit=$DiffExit"
```

目标是 exit 0。**没有实际 exit 0 不得写 PASS。**

## 4. Controller v0.3.2 身份 / 双 Bridge 回归

先显式停止旧 stale Controller：

```powershell
pwsh.exe -NoProfile -File scripts/stop.ps1
```

如果提示没有现有 Controller，可以记录为 clean start；如果提示 state 存在但不可达、replacement、timeout 或其他错误，不要自行删 `data/controller.json`，直接保存证据并报告。

执行仓库现有 Controller 验收脚本：

```powershell
.venv\Scripts\python.exe scripts/verify-controller.py --config config/runtime.toml --fresh --stop-after
$ControllerExit = $LASTEXITCODE
Write-Host "verify-controller exit=$ControllerExit"
```

记录完整 JSON，重点确认：

- `package_version_is_0_3_2 = true`；
- 两个 Bridge server version = `0.3.2`；
- 两个 Bridge 均 6 tools；
- Controller `protocol_version = 2`；
- Controller 在两个 Bridge 退出后仍存活；
- single runtime / max concurrent = 1 / max inflight = 16；
- `verification_passed = true` 才能把本项标为 PASS。

## 5. 真实 AGY build/test 字节验收

### 5.1 使用真实已登记任务

优先使用：

```text
workspace_id: ai_skill_roundtable
command_id: jianyu_lint_assemble
kind: build
```

仓库 `config/runtime.toml` 已登记该命令。目标是执行真实 `lintDebug + assembleDebug`，**只采集事实和证据，不修改见域源码**。

如果当前本机 `agy_capabilities` 中没有该 workspace/command，停止并报告配置差异，不擅自改配置。

如果任务最终 `total_warnings == 0`，本次“不少于 1 条 warning”的真实验收条件没有被满足。不要伪造 warning；报告 `warning_probe_not_satisfied`，再由 ChatGPT 决定是否选择另一个已登记命令。

### 5.2 临时验收探针

不要把探针保存到 Git 跟踪文件。可在 PowerShell 中把下面 Python 保存到 `$env:TEMP\agy-worker-v032-acceptance.py`，输出保存到仓库已忽略的 `work/` 或 `$env:TEMP`。

```python
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(r"D:\My\_Elio\agy-worker")
CONFIG = ROOT / "config" / "runtime.toml"
TERMINAL = {"succeeded", "failed", "cancelled", "timed_out", "interrupted"}


def compact_bytes(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def text_bytes(response):
    return [len(item.text.encode("utf-8")) for item in response.content if getattr(item, "type", None) == "text"]


def structured(response):
    value = getattr(response, "structured_content", None)
    if value is None:
        value = getattr(response, "structuredContent", None)
    return value


def show(label, response):
    value = structured(response)
    row = {
        "label": label,
        "structured_bytes": compact_bytes(value) if isinstance(value, dict) else None,
        "text_bytes": text_bytes(response),
        "structured": value,
        "text": [item.text for item in response.content if getattr(item, "type", None) == "text"],
    }
    print(json.dumps(row, ensure_ascii=False), flush=True)
    return value


async def main():
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agy_worker.server", "--config", str(CONFIG)],
        env={key: value for key, value in os.environ.items() if key.lower().endswith("_proxy")},
    )
    async with stdio_client(params) as (reader, writer):
        async with ClientSession(reader, writer) as client:
            init = await client.initialize()
            print(json.dumps({
                "label": "initialize",
                "server_version": init.server_info.version,
            }, ensure_ascii=False), flush=True)

            tools = await client.list_tools()
            print(json.dumps({"label": "tools", "count": len(tools.tools), "names": [x.name for x in tools.tools]}, ensure_ascii=False), flush=True)

            caps_response = await client.call_tool("agy_capabilities", {})
            caps = show("capabilities", caps_response)
            print(json.dumps({"label": "controller", "value": (caps or {}).get("controller")}, ensure_ascii=False), flush=True)

            request = {
                "request_id": "req-" + uuid.uuid4().hex,
                "workspace_id": "ai_skill_roundtable",
                "kind": "build",
                "objective": "执行已登记的 jianyu_lint_assemble，只报告真实退出状态、warning/error 计数和证据；不分析根因，不修改源码。",
                "permissions": {"build": True, "log": True, "code_write": False},
                "inputs": {"command_id": "jianyu_lint_assemble"},
                "limits": {"total_timeout_sec": 1200, "summary_max_bytes": 16384},
            }
            submit_response = await client.call_tool("agy_worker", request)
            state = show("submit", submit_response)
            if not isinstance(state, dict) or "task_id" not in state:
                raise RuntimeError("submit 没有返回结构化 task")

            status_index = 0
            while state.get("status") not in TERMINAL:
                after = state["revision"]
                response = await client.call_tool(
                    "agy_status",
                    {"task_id": state["task_id"], "after_revision": after, "wait_ms": 25000},
                    read_timeout_seconds=30,
                )
                returned = show(f"status-{status_index}", response)
                status_index += 1
                if not isinstance(returned, dict):
                    raise RuntimeError("status 没有 structured payload")
                # unchanged 不推进 revision，也绝不自动 cancel；继续等待同一任务。
                state = returned

            terminal = state
            print(json.dumps({"label": "terminal-final", "value": terminal}, ensure_ascii=False), flush=True)

            result = terminal.get("result") or {}
            diagnostics_id = result.get("diagnostics_artifact_id")
            evidence_id = ((result.get("operation") or {}).get("evidence") or {}).get("artifact_id")
            if diagnostics_id:
                response = await client.call_tool("agy_artifact_read", {
                    "task_id": terminal["task_id"], "artifact_id": diagnostics_id,
                    "view": "text", "start_line": 1, "line_count": 80,
                })
                show("artifact-diagnostics", response)
            if evidence_id:
                response = await client.call_tool("agy_artifact_read", {
                    "task_id": terminal["task_id"], "artifact_id": evidence_id,
                    "view": "text", "start_line": 1, "line_count": 80,
                })
                show("artifact-operation-log", response)


asyncio.run(main())
```

PowerShell 运行时使用仓库 venv Python，例如：

```powershell
.venv\Scripts\python.exe "$env:TEMP\agy-worker-v032-acceptance.py" 2>&1 | Tee-Object -FilePath 'work\v032-acceptance.log'
$AgyExit = $LASTEXITCODE
Write-Host "real AGY probe exit=$AgyExit"
```

## 6. 逐项判定真实返回合同

基于探针原始输出逐条判定，不只看最终 PASS/FAIL 文案。

### 6.1 submit / changed nonterminal

- structured JSON 使用紧凑编码计量；
- changed queued/running/cancelling `<= 512 bytes`；
- TextContent 每条 `<= 256 UTF-8 bytes`；
- TextContent 不能等于完整 `json.dumps(structured payload)`；
- running 可以带小 `progress`；
- 不应出现 `created_at/updated_at`。

### 6.2 unchanged

如果真实任务自然出现 25 秒无更高 revision 的窗口，必须看到完整结构等价于：

```json
{"task_id":"task-...","status":"running","revision":5,"unchanged":true}
```

并满足：

- structured `<= 256 bytes`；
- 不含 `session_id/turn/progress/result`；
- TextContent `<=256B`；
- **绝不因为一次或多次 unchanged 自动调用 cancel**。

如果构建持续输出导致没有自然 unchanged 窗口，记录：

```text
unchanged_real_window: not_observed
```

这不是失败，也不允许人为暂停/篡改进程制造假证据；协议语义由单元测试覆盖。

### 6.3 build/test terminal

terminal structured 必须 `<= 1536 bytes`，并检查：

- 有 `task_id/session_id/turn/status/revision/result`；
- **无 terminal `progress`**；
- `result.schema_version == 2`；
- 有 `summary`；
- `operation.exit_code` 是真实命令退出码；
- `operation.total_errors / total_warnings` 存在；
- `operation.evidence.artifact_id` 存在；
- `result_artifact_id` 存在；
- warning/error 存在时 `diagnostics_artifact_id` 存在；
- 不展开 `errors[] / warnings[] / artifacts[] / workspace_path / input_snapshot / agy / enforcement`；
- TextContent `<=256B`，且不是 structured JSON 的完整复制。

若 `source_changed=true`，还必须：

- `changed_files_count` 是完整数量；
- `changed_files_preview` 最多 5 项；
- 每项 UTF-8 `<=128 bytes`；
- 不能因为 public preview 截断而删除 `result` artifact 中的完整证据。

### 6.4 artifact cold path

对 `agy_artifact_read` 文本/metadata：

- `structured_content` 应为空 / None；
- payload 只在单个 TextContent 中出现一次；
- `errors` artifact 能读到 warning/error 正文；
- `operation-log` 能按行读取上下文；
- 不因 status 紧凑化丢失 evidence。

已有 image artifact 行为由仓库测试覆盖；本次不要求为了 token 验收额外制造图片任务。

## 7. 官方 `run-task.py` 兼容性回归

本 PR 修改了 `scripts/run-task.py`，原因是 v0.3.2 普通 TextContent 已不再承载完整 JSON。`scripts/check.ps1` 中对应单元测试必须通过。

如需额外做一次真实脚本 smoke，可用新的 request_id 复制现有示例到 `work/` 后运行；不要修改仓库跟踪的 example 文件。必须确认脚本能从 structuredContent 得到 task，而不是对短 TextContent 做 `json.loads()` 后崩溃。

## 8. Codex 宿主 transcript 去重

如果本地 AI 能访问真实 Codex MCP 调用记录，再执行一次正常 `agy_status` 并检查：

- structured payload 只出现一份 canonical machine JSON；
- TextContent 是短摘要；
- 不再出现“同一个完整 JSON 一份 text + 一份 structured”的重复记录。

若本地环境无法查看 Codex transcript，记录：

```text
codex_transcript_duplicate_check: not_available
```

不要把 direct MCP probe 自动冒充成 Codex UI/transcript 验收。

## 9. 返回给 ChatGPT 的验收报告格式

请把下面模板填完整，**附关键原始输出**，不要只发“测试通过”：

```text
AGY Worker v0.3.2 local acceptance

branch_head: <git rev-parse HEAD>
target_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
post_target_non_planning_files: <none | list>
working_tree_before: <clean | details>
package_version: <value>

scripts_check:
  command: pwsh.exe -NoProfile -File scripts/check.ps1
  exit_code: <n>
  pytest_passed: <n>
  pytest_failed: <n>
  pytest_skipped: <n>
  warnings: <n/details>

diff_check:
  command: git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD
  exit_code: <n>

controller_verification:
  exit_code: <n>
  server_version: <...>
  protocol_version: <...>
  tool_count: <...>
  verification_passed: <true/false>

real_agy:
  request_id: <...>
  task_id: <...>
  final_status: <...>
  operation_exit_code: <...>
  total_errors: <...>
  total_warnings: <...>
  submit_structured_bytes: <n>
  submit_text_bytes: <n/list>
  status_rows:
    - after_revision: <n>
      wait_ms: 25000
      returned_revision: <n>
      status: <...>
      unchanged: <true/false>
      structured_bytes: <n>
      text_bytes: <n/list>
  unchanged_real_window: <observed + JSON | not_observed>
  terminal_structured_bytes: <n>
  terminal_text_bytes: <n/list>
  terminal_has_progress: <true/false>
  diagnostics_artifact_id: <...>
  result_artifact_id: <...>
  diagnostics_read: <PASS/FAIL + evidence excerpt/reference>
  operation_log_read: <PASS/FAIL + evidence excerpt/reference>
  duplicate_full_json_in_mcp_result: <true/false>
  codex_transcript_duplicate_check: <PASS/FAIL/not_available>

open_findings:
  - <severity + exact evidence, or none>

overall_local_result: <PASS / FAIL / PARTIAL>
```

## 10. 判定边界

本地 AI 只负责运行与证据收集，不负责宣布 PR 可以 merge。即使所有本地项目都 PASS，也请把报告交回 ChatGPT；ChatGPT 会逐条技术复核、回填 `TASKS.md`，之后由用户决定是否合并 PR #2。
