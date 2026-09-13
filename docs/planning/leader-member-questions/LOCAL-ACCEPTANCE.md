# v0.4.0 领导 / 成员 AI 协作本地验收

> 目标：由本地 AI / 维护者在 Windows 10 + 当前 AGY 账号环境验证 `ask_leader → agy_status → agy_answer → resume`。本文件当前是**待执行清单**，不是 PASS 记录。

## 1. 基线与安装

```powershell
git status --short
git rev-parse HEAD
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
& ./.venv/Scripts/python.exe -c "from importlib.metadata import version; print(version('elio-agy-worker'))"
```

预期 metadata 为 `0.4.0`。记录实际 HEAD 和输出。

## 2. 单元 / 静态检查

```powershell
& ./.venv/Scripts/python.exe -m pytest -q tests/test_leader_member_questions.py
pwsh.exe -NoProfile -File scripts/check.ps1
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
git diff --check
git status --short
```

要求：

- 新协作测试真实执行并记录 passed/failed；
- 完整 `scripts/check.ps1` exit 0；
- schema regeneration 后没有意外 diff；
- `schemas/agy_answer.json` 与生成结果一致；
- `git diff --check` exit 0。

## 3. 注册与 stale Controller

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

## 4. 真实 AGY 问答闭环

提交一个**必须做业务选择才能继续、但不需要新系统权限**的任务。建议准备两个均已在原任务授权内的安全选项，例如“发现两种只读日志范围时先询问领导选择 A/B，再读取选定范围”。

验收观察：

1. AGY 只通过私有 `worker_action` 调用 `ask_leader`；
2. `agy_status` 在 AGY terminal 前返回 `leader_question`；
3. `leader_question` 包含 `question_id`、question、created_at；
4. 领导用**原样** task_id/question_id 调用 `agy_answer`；
5. 同一个 AGY 任务从原 `ask_leader` 调用拿到 answer 后继续，而不是新起第二个任务；
6. 最终 terminal 仍由真实 operation / AGY result 决定，不能仅凭文本声称成功。

保存对应 task audit、status/answer structured payload 和必要的 AGY stream 证据。

## 5. 幂等与错误语义

对已回答 question：

- 同 question_id + 完全相同 answer 再调一次，应返回同一 `answered` revision；
- 同 question_id + 不同 answer，应返回 `idempotency_conflict`；
- 当前 pending 为另一个 question_id 时，用旧/伪造 ID，应返回 `stale_question`；
- 空 question/answer、未知字段、超限文本应 fail closed。

## 6. 取消 / 超时 / 重启

至少执行以下一项真实取消和一项重启检查：

- 成员等待 answer 时 `agy_cancel`：等待应解除，task 按既有 cancel 语义收口；
- 使用短 `total_timeout_sec` 让等待耗尽：不得因咨询获得额外无限时间；
- pending question 时停止 Controller：旧 task 重启后应为 `interrupted`，不得自动恢复旧等待或重做外部动作。

## 7. 权限回归

问答前后确认：

- shell 仍不可用；
- code_write 仍不可用；
- AGY 仍不能调用其他 MCP；
- 浏览器/Android 权限没有因领导 answer 自动增加；
- `ask_leader` arguments 只接受 `question`。

## 8. 验收回填格式

```text
HEAD: <sha>
Python/package: <version>
Focused tests: PASS/FAIL + count
scripts/check.ps1: PASS/FAIL + count
schema regeneration: PASS/FAIL
register/stale controller: PASS/FAIL
real ask/answer/resume: PASS/FAIL
cancel or timeout: PASS/FAIL
restart/interrupted: PASS/FAIL
permission regression: PASS/FAIL
open issues: <具体日志/证据>
```

只把实际执行过的项标记 PASS；未执行项写“未验证”。
