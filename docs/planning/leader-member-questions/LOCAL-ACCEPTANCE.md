# v0.4.0 领导 / 成员 AI 协作本地验收

> 目标：由本地 AI / 维护者在 Windows 10 + 当前 AGY 账号环境验证 `ask_leader → agy_status → agy_answer → resume`，并确认已完成 PR #4 的 v0.3.3 行为没有在整合中回归。本文件当前是**待执行清单**，不是 PASS 记录。

## 0. 整合基线

本轮最终验收分支：

```text
feat/leader-member-questions-v2
```

该分支直接包含 PR #4 `fix/v033-timeout-status-guidance` 的 HEAD `cf089281165fc07243afe609eeaa1076b3993c76` 作为祖先，再整合 v0.4.0 领导/成员协作。验收时不要继续使用旧的 `feat/leader-member-questions` 作为最终结论来源。

如果旧分支验收已经完成，可保留其结果作为“协作功能在旧基线上的证据”；本轮不必机械重复所有昂贵步骤，但必须重新执行整合敏感项：完整检查、schema、v0.3.3 600 秒/status 合同，以及至少一次真实 ask/answer/resume smoke。

## 1. 基线与安装

```powershell
git status --short
git rev-parse HEAD
git merge-base --is-ancestor cf089281165fc07243afe609eeaa1076b3993c76 HEAD
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
& ./.venv/Scripts/python.exe -c "from importlib.metadata import version; print(version('elio-agy-worker'))"
```

要求：

- 当前分支为 `feat/leader-member-questions-v2`；
- `merge-base --is-ancestor` exit 0，证明 PR #4 HEAD 是当前分支祖先；
- package metadata 为 `0.4.0`；
- 记录实际 HEAD 和工作区状态。

## 2. 单元 / 静态检查

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_v033_followups.py tests/test_leader_member_questions.py tests/test_leader_member_question_races.py
pwsh.exe -NoProfile -File scripts/check.ps1
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
git diff --check
git status --short
```

要求：

- v0.3.3 回归测试与新协作测试真实执行并记录 passed/failed；
- 完整 `scripts/check.ps1` exit 0；
- schema regeneration 后没有意外 diff；
- `schemas/agy_worker.json` / `agy_continue.json` 的 `total_timeout_sec.default` 仍为 600；
- `schemas/agy_answer.json` 与生成结果一致；
- `git diff --check` exit 0。

## 3. v0.3.3 整合回归

确认：

- `McpLimits().total_timeout_sec == 600`；
- Runtime capabilities 报告默认任务预算 600；
- 公开 `agy_status.wait_ms=25000` 仍 fail-closed；
- Codex 可见 `agy_status` tool description + Server instructions 不出现 `25 秒` 或 `25000`；
- 当前/terminal 快照引导仍要求省略 `after_revision` 和 `wait_ms`。

若旧 PR #4 的真实慢构建已经有可信 PASS 证据，本轮可不重复完整慢构建；若没有，则仍建议执行一次正常省略 `limits` 的较慢真实任务，确认 600 秒默认预算实际生效。

## 4. 注册与 stale Controller

```powershell
pwsh.exe -NoProfile -File scripts/register.ps1
pwsh.exe -NoProfile -File scripts/stop.ps1
```

核对 Codex 配置：

- `enabled_tools` 包含 `agy_answer`；
- `tool_timeout_sec=660`；
- 用户原有 developer instructions 保留；
- managed routing block 提到 `leader_question → agy_answer`；
- 旧 Controller 未被新 Bridge 静默复用；若 implementation hash 不一致，应 fail-closed 并要求显式 stop。

## 5. 真实 AGY 问答闭环

提交一个**必须做业务选择才能继续、但不需要新系统权限**的任务。建议准备两个均已在原任务授权内的安全选项，例如“发现两种只读日志范围时先询问领导选择 A/B，再读取选定范围”。

验收观察：

1. AGY 只通过私有 `worker_action` 调用 `ask_leader`；
2. `agy_status` 在 AGY terminal 前返回 `leader_question`；
3. `leader_question` 包含 `question_id`、question、created_at；
4. 领导用**原样** task_id/question_id 调用 `agy_answer`；
5. 同一个 AGY 任务从原 `ask_leader` 调用拿到 answer 后继续，而不是新起第二个任务；
6. 最终 terminal 仍由真实 operation / AGY result 决定，不能仅凭文本声称成功。

保存对应 task audit、status/answer structured payload 和必要的 AGY stream 证据。

## 6. 幂等与错误语义

如果旧分支已经完整 PASS，可把旧结果作为辅助证据；至少在 v2 做一次相同 answer 幂等 smoke。完整合同：

- 同 question_id + 完全相同 answer 再调一次，应返回同一 `answered` revision；
- 同 question_id + 不同 answer，应返回 `idempotency_conflict`；
- 当前 pending 为另一个 question_id 时，用旧/伪造 ID，应返回 `stale_question`；
- 空 question/answer、未知字段、超限文本应 fail closed。

## 7. 取消 / 超时 / 重启

若旧分支对应真实场景已 PASS，且 v2 的 race/unit tests 与完整 `scripts/check.ps1` 均 PASS，可不重复所有昂贵真实场景；否则至少执行一项真实取消/超时检查。

完整预期：

- 成员等待 answer 时 `agy_cancel`：等待应解除，task 按既有 cancel 语义收口；
- 使用短 `total_timeout_sec` 让等待耗尽：不得因咨询获得额外无限时间；
- pending question 时停止 Controller：旧 task 重启后应为 `interrupted`，不得自动恢复旧等待或重做外部动作。

## 8. 权限回归

问答前后确认：

- shell 仍不可用；
- code_write 仍不可用；
- AGY 仍不能调用其他 MCP；
- 浏览器/Android 权限没有因领导 answer 自动增加；
- `ask_leader` arguments 只接受 `question`。

## 9. 验收回填格式

```text
HEAD: <sha>
Branch: feat/leader-member-questions-v2
PR4 ancestor check: PASS/FAIL
Python/package: <version>
Focused integration tests: PASS/FAIL + count
scripts/check.ps1: PASS/FAIL + count
schema regeneration: PASS/FAIL
v0.3.3 600s/status regression: PASS/FAIL
register/stale controller: PASS/FAIL
real ask/answer/resume smoke: PASS/FAIL
answer idempotency: PASS/FAIL/沿用旧分支证据
cancel or timeout: PASS/FAIL/沿用旧分支证据/未验证
restart/interrupted: PASS/FAIL/沿用旧分支证据/未验证
permission regression: PASS/FAIL
open issues: <具体日志/证据>
```

只把实际执行过的项标记 PASS；沿用旧分支结果时必须明确写“沿用旧分支证据”，不能伪装成 v2 上重新执行过。
