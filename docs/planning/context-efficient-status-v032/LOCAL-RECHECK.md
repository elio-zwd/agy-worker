# AGY Worker v0.3.2 最小本地复验

> 目的：只复验 2026-09-10 第一轮本地验收暴露出的 5 个回归测试问题及最终 diff。
> 不重新运行真实 AGY build/test，因为自第一轮真实 AGY 验收以来没有生产代码变化。

## 固定事实

```text
branch: perf/context-efficient-status-v032
base: b51d81701f3cfe3859c485f87e42a03b22b4e3d7
production_code_head: 2b9ef842e4eb52bed7c00e6e57505a0c09a64852
first_acceptance_head: c19491917a6f6da5ca0f3c8242dad46f3891d1cd
test_fix_head: 238da44b4f23e3496f6b283f7e87d86f583879a3
```

本文件/Tracker 可能位于 `test_fix_head` 之后的 planning-only commit。开始前必须确认 `test_fix_head..HEAD` 只包含 `docs/planning/context-efficient-status-v032/**`；如出现其他路径，停止并报告。

## 1. 更新与工作区检查

在本机仓库根目录：

```powershell
git status --short
git fetch origin
git switch perf/context-efficient-status-v032
git pull --ff-only
git rev-parse HEAD
git status --short
git diff --name-only 238da44b4f23e3496f6b283f7e87d86f583879a3..HEAD
```

要求：

- pull 必须是 fast-forward；
- 工作区前后 clean；
- `238da44..HEAD` 若有文件，只能位于 `docs/planning/context-efficient-status-v032/**`。

不要修改、提交、rebase、reset、force-push 或 merge。

## 2. 核对测试修正净范围

```powershell
git diff --stat c19491917a6f6da5ca0f3c8242dad46f3891d1cd..238da44b4f23e3496f6b283f7e87d86f583879a3
git diff --name-only c19491917a6f6da5ca0f3c8242dad46f3891d1cd..238da44b4f23e3496f6b283f7e87d86f583879a3
```

预期只有：

```text
tests/test_controller.py
tests/test_runtime.py
tests/test_server.py
```

如果有生产文件，停止并报告。

## 3. 权威全量检查

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
```

必须记录：

```text
exit_code
pytest passed
pytest failed
pytest skipped
warnings（pytest 自身 warning summary，如有）
```

**通过条件：exit_code = 0，pytest failed = 0。**

如果失败，不修改代码；粘贴完整失败测试名称和首个有效 traceback/assertion evidence 给 ChatGPT。

## 4. 最终 whitespace/diff 检查

```powershell
git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD
```

必须 exit 0。

## 5. 结束状态

```powershell
git status --short
git rev-parse HEAD
```

工作区必须 clean。

本轮无需运行：

- 真实 `jianyu_lint_assemble`；
- AGY payload probe；
- `verify-controller.py`。

原因：第一轮这些真实生产路径已经在相同生产代码上通过；本轮从 `c194919..238da44` 的净变化只有测试文件。

## 6. 回报格式

把下面内容原样填好发给 ChatGPT：

```text
AGY Worker v0.3.2 regression recheck

branch_head: <git rev-parse HEAD>
working_tree_before: clean|dirty
post_test_fix_non_planning_files: <none|paths>

test_fix_scope:
  c194919..238da44 changed files: <paths>
  production_files_changed: false|true

scripts_check:
  command: pwsh.exe -NoProfile -File scripts/check.ps1
  exit_code: <n>
  pytest_passed: <n>
  pytest_failed: <n>
  pytest_skipped: <n>
  warnings: <n or exact summary>

diff_check:
  command: git diff --check b51d81701f3cfe3859c485f87e42a03b22b4e3d7..HEAD
  exit_code: <n>

working_tree_after: clean|dirty

open_findings:
  - <none or exact failures>

overall_recheck: PASS|FAIL
```

如果 `scripts/check.ps1` 或 `git diff --check` 任一非零，`overall_recheck` 必须是 `FAIL`。
