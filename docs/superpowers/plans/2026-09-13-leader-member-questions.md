# Leader–Member AI Questions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让正在执行 AGY Worker 任务的成员 AI 能通过私有 Broker 向领导 AI 提问，并由领导通过公开 MCP `agy_answer` 回复后继续同一任务。

**Architecture:** 新增 `CollaborativeRuntime(Runtime)` 作为协作扩展层，保持现有基础 Runtime 和权限执行器不变；成员侧经 `worker_action.ask_leader` 写入 pending question，领导侧由 `agy_status` 观察、`agy_answer` 回复。问答状态由现有 task record 持久化，等待唤醒使用 task context 内的 `threading.Event`。

**Tech Stack:** Python 3.13–3.14, MCP Python SDK 2.2.0, Pydantic 2.13.5, sqlite3/threading, pytest, Windows 10 local acceptance.

**Spec:** `docs/superpowers/specs/2026-09-13-leader-member-questions-design.md`

## Global Constraints

- 不开放任意 shell、源码写入、其他 MCP 或外部模型 API。
- `ask_leader` 只能通过现有私有 Broker + task bearer token。
- `agy_answer` 只能通过现有 authenticated Controller IPC。
- 每 task 最多 8 个问题；等待答复不能延长原 `total_timeout_sec`。
- 保持 Controller protocol v2；`collaboration.py` 必须进入 `CONTROLLER_IMPLEMENTATION_FILES`。
- 包版本升级为 `0.4.0`。
- ChatGPT Web 不得声称本地 pytest、PowerShell、Windows 或真实 AGY 验证已通过。

---

### Task 1: 先固定公开 MCP 合同

**Files:**
- Modify: `tests/test_server.py`
- Modify: `tests/test_mcp_hot_path.py`
- Modify: `tests/test_manage.py`
- Modify: `src/agy_worker/models.py`
- Modify: `src/agy_worker/server.py`
- Modify: `src/agy_worker/manage.py`
- Create: `schemas/agy_answer.json`

**Interfaces:**
- Produces: `AnswerRequest(task_id: str, question_id: str, answer: str)`
- Produces: public tool `agy_answer`
- Consumes later: Controller method name `answer`

- [ ] **Step 1: Write failing public-contract tests**

Add tests that require:

```python
result=call_tool(callback,'agy_answer',{
    'task_id':'task-1',
    'question_id':'question-1',
    'answer':'继续使用当前 workspace。',
})
assert client.calls==[('answer',{
    'task_id':'task-1',
    'question_id':'question-1',
    'answer':'继续使用当前 workspace。',
},None)]
```

and status coalescing:

```python
client=StatusSequenceClient([
    {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
    {'task_id':'task-1','status':'running','revision':3,
     'leader_question':{'question_id':'question-1','question':'选 A 还是 B？','created_at':'2026-09-13T00:00:00Z'}},
])
result=call_tool(handlers,'agy_status',{
    'task_id':'task-1','after_revision':1,'wait_ms':50000,
})
assert result.structured_content['leader_question']['question_id']=='question-1'
assert len(client.calls)==2
```

Also assert schema generation creates `agy_answer.json` and Codex registration enables `agy_answer`.

- [ ] **Step 2: RED verification**

Run on Windows acceptance environment:

```powershell
& ./.venv/Scripts/python.exe -m pytest tests/test_server.py tests/test_mcp_hot_path.py tests/test_manage.py -q
```

Expected before implementation: failures because `agy_answer` / `AnswerRequest` do not exist and status coalescing swallows the question revision.

- [ ] **Step 3: Implement strict public model and Server dispatch**

Add to `models.py`:

```python
class AnswerRequest(Strict):
    task_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    question_id: str = Field(min_length=1, max_length=100, pattern=r"^[\w.-]+$")
    answer: str = Field(min_length=1, max_length=8000)
```

Add `agy_answer` to `TOOLS`; dispatch it through `client.call("answer", request.model_dump())`. In `_coalesced_status`, immediately return a nonterminal result containing `leader_question` rather than merging it away.

- [ ] **Step 4: Register and generate the schema**

Add `agy_answer` to `manage.register().enabled_tools` and to `manage.schemas()`. Commit generated `schemas/agy_answer.json` matching `AnswerRequest.model_json_schema()`.

- [ ] **Step 5: GREEN verification**

Re-run the exact Task 1 pytest command and record exit code/test count locally.

---

### Task 2: 实现 Runtime 问答交换

**Files:**
- Create: `src/agy_worker/collaboration.py`
- Create: `tests/test_collaboration.py`

**Interfaces:**
- Produces: `CollaborativeRuntime(Runtime)`
- Produces: private action `ask_leader`
- Produces: Controller-call handler `answer`

- [ ] **Step 1: Write failing behavior tests**

Create a Runtime fixture with a controlled pool future. Start `ask_leader` in a Python thread, then assert:

```python
question=runtime.status(task_id, wait_ms=0)['leader_question']
assert question['question']=='应该继续 A 还是 B？'

answered=runtime.answer(task_id, question['question_id'], '继续 A。')
assert answered['status']=='answered'
assert member_future.result(timeout=1)=={
    'question_id':question['question_id'],
    'answer':'继续 A。',
}
```

Add separate cases for same-answer idempotent retry, conflicting retry, stale question ID, cancellation, UTF-8 size limits and per-task quota.

- [ ] **Step 2: RED verification**

```powershell
& ./.venv/Scripts/python.exe -m pytest tests/test_collaboration.py -q
```

Expected before implementation: import/behavior failures because `CollaborativeRuntime` does not exist.

- [ ] **Step 3: Implement `CollaborativeRuntime`**

Core shape:

```python
class CollaborativeRuntime(Runtime):
    def control_call(self, method, params):
        if method == 'answer':
            request=AnswerRequest.model_validate(params)
            return self.answer(**request.model_dump())
        return super().control_call(method, params)

    def _public_task(self, record, *, unchanged=False):
        result=super()._public_task(record, unchanged=unchanged)
        if not unchanged and record.get('status') not in TERMINAL and record.get('leader_question'):
            result['leader_question']=record['leader_question']
        return result
```

For `ask_leader`, validate `arguments == {'question': ...}`, enforce UTF-8 byte limit and max 8 questions, write `record['leader_question']`, `_save()` to advance revision, then wait on a per-context `threading.Event` in bounded slices while checking `cancel` and remaining `total_timeout_sec`.

For `answer`, under Runtime RLock verify task/question identity, persist bounded `leader_dialogue`, remove pending question, `_save()`, store the in-memory answer and set the Event. Same ID/same answer retries return the prior result; different answer raises `idempotency_conflict`.

- [ ] **Step 4: Add member guidance without duplicating base `_run`**

Override `_run` only as a wrapper: temporarily replace the request with `model_copy(update={'objective': objective + guidance})` when the combined objective stays within the public objective ceiling, call `super()._run(c)`, and restore the original request in `finally`. Guidance tells AGY to use `ask_leader` only when execution genuinely requires a leader decision or missing context, never to use it to expand permissions.

- [ ] **Step 5: GREEN verification**

Re-run `tests/test_collaboration.py` locally and record output.

---

### Task 3: 把协作 Runtime 接入安全链路

**Files:**
- Modify: `src/agy_worker/controller.py`
- Modify: `src/agy_worker/controller_state.py`
- Modify: `src/agy_worker/broker.py`
- Modify: `tests/test_controller_hardening_quality.py` or focused collaboration test where appropriate

**Interfaces:**
- Controller constructs `CollaborativeRuntime` instead of base `Runtime`.
- Broker `worker_action.action` enum includes `ask_leader` and documents its single `question` argument.
- Controller implementation digest includes `collaboration.py`.

- [ ] **Step 1: Write/extend tests first**

Assert the Controller runtime class exposes the collaboration behavior, Broker schema contains `ask_leader` but no new arbitrary action, and changing `collaboration.py` is included in the controller implementation file set.

- [ ] **Step 2: RED verification**

```powershell
& ./.venv/Scripts/python.exe -m pytest tests/test_controller.py tests/test_controller_hardening_quality.py tests/test_collaboration.py -q
```

- [ ] **Step 3: Wire Controller, Broker and implementation hash**

Use:

```python
from .collaboration import CollaborativeRuntime as Runtime
```

in `controller.py`, add `"collaboration.py"` to `CONTROLLER_IMPLEMENTATION_FILES`, and extend only the private Broker action enum/description.

- [ ] **Step 4: GREEN verification**

Re-run the Task 3 test command locally.

---

### Task 4: 版本、文档与完整验收

**Files:**
- Modify: `pyproject.toml`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/实施设计.md`
- Modify: `docs/部署验收.md`
- Modify: tests that assert package version / documented tool count

**Interfaces:**
- Package version: `0.4.0`
- Public MCP tools: 7

- [ ] **Step 1: Update version and contract docs**

Document the leader/member flow, `leader_question`, `agy_answer`, cancellation/timeout semantics, 8-question quota, and unchanged security boundary. Keep planned/future items clearly separated from implemented behavior until local acceptance supplies evidence.

- [ ] **Step 2: Refresh editable package metadata locally**

```powershell
& ./.venv/Scripts/python.exe -m pip install --no-deps --no-build-isolation -e .
```

- [ ] **Step 3: Run authoritative repository verification**

```powershell
pwsh.exe -NoProfile -File scripts/check.ps1
& ./.venv/Scripts/python.exe -m agy_worker.manage schemas
git diff --check
git diff
```

Expected: `scripts/check.ps1` exit 0; schema regeneration produces no diff; `git diff --check` exit 0.

- [ ] **Step 4: Run real leader/member acceptance**

Register/reload the feature build, submit a task whose AGY member needs a deliberate leader decision, and capture evidence that:

1. AGY calls private `ask_leader`.
2. `agy_status` returns `leader_question` without waiting to terminal.
3. Leader calls `agy_answer` with matching IDs.
4. The same AGY process resumes and completes the original task.
5. A cancellation while waiting terminates cleanly.
6. No shell/code_write/other MCP capability becomes available.

- [ ] **Step 5: Final spec and quality review**

Compare the final diff line-by-line with the design spec; separately review security, idempotency, timeout/cancel races, status coalescing, docs and test gaps. Do not claim PASS for any local/real-AGY item until concrete output is supplied.
