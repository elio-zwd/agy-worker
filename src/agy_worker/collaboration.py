"""在基础 Runtime 之上增加受控的领导/成员问答，不扩大执行权限。"""
import threading
import time
import uuid

from .common import WorkerError, now
from .models import AnswerRequest
from .runtime import Runtime, TERMINAL


MAX_LEADER_QUESTIONS = 8
QUESTION_MAX_BYTES = 4096
ANSWER_MAX_BYTES = 8192
_MEMBER_GUIDANCE = (
    "\n协作规则：只有当继续任务确实缺少上级业务判断、选择或必要上下文时，"
    "才通过 worker_action 的 ask_leader 向领导提问；问题应一次说清需要决定的事项。"
    "ask_leader 不能用于扩大权限、请求 shell/源码写入/其他 MCP，也不要重复询问已得到答复的问题。"
)


def _bounded_text(value, *, name, max_bytes):
    if not isinstance(value, str) or not value.strip():
        raise WorkerError("invalid_request", f"{name} 不能为空")
    if len(value.encode("utf-8")) > max_bytes:
        raise WorkerError("invalid_request", f"{name} 超过 {max_bytes} UTF-8 bytes")
    return value


class CollaborativeRuntime(Runtime):
    """保持 Runtime 安全执行链不变，只叠加 task 内的上级咨询能力。"""

    @staticmethod
    def _ensure_collaboration_context(context):
        context.setdefault("leader_questions", 0)
        context.setdefault("leader_answer_event", threading.Event())
        context.setdefault("leader_answer", None)

    def control_call(self, method, params):
        if method == "answer":
            request = AnswerRequest.model_validate(params)
            return self.answer(**request.model_dump())
        return super().control_call(method, params)

    def _public_task(self, record, *, unchanged=False):
        result = super()._public_task(record, unchanged=unchanged)
        question = record.get("leader_question")
        if not unchanged and record.get("status") not in TERMINAL and question:
            result["leader_question"] = {
                key: question[key]
                for key in ("question_id", "question", "created_at")
                if key in question
            }
        return result

    def action(self, context, payload):
        if payload.get("action") != "ask_leader":
            return super().action(context, payload)
        if set(payload) - {"action", "arguments"}:
            raise WorkerError("invalid_request", "ask_leader 只接受 action 和 arguments")
        arguments = payload.get("arguments", {})
        if not isinstance(arguments, dict):
            raise WorkerError("invalid_request", "arguments 必须为对象")
        if context.get("started") is None:
            raise WorkerError("permission_denied", "任务尚未开始")
        if (
            time.monotonic() - context["started"] >= context["request"].limits.total_timeout_sec
            or context["cancel"].is_set()
        ):
            raise WorkerError("permission_denied", "任务已结束或超时")
        with context["operation_lock"]:
            context["actions"] += 1
            if context["actions"] > 80:
                raise WorkerError("quota_exceeded", "本轮操作超过 80 次")
            self.audit(context, "action", action="ask_leader")
            return self._ask_leader(context, arguments)

    def _ask_leader(self, context, arguments):
        if set(arguments) != {"question"}:
            raise WorkerError("invalid_request", "ask_leader 只接受 question")
        question_text = _bounded_text(
            arguments.get("question"), name="question", max_bytes=QUESTION_MAX_BYTES
        )
        self._ensure_collaboration_context(context)
        if context["leader_questions"] >= MAX_LEADER_QUESTIONS:
            raise WorkerError("quota_exceeded", f"每个任务最多询问领导 {MAX_LEADER_QUESTIONS} 次")

        question_id = "question-" + uuid.uuid4().hex
        question = {
            "question_id": question_id,
            "question": question_text,
            "created_at": now(),
        }
        event = context["leader_answer_event"]
        with self.lock:
            if context["record"].get("leader_question"):
                raise WorkerError("question_pending", "当前任务已有一个等待领导答复的问题")
            context["leader_questions"] += 1
            context["leader_answer"] = None
            event.clear()
            context["record"]["leader_question"] = question
            self.audit(context, "leader_question", question_id=question_id)
            self._save(context["record"])

        while True:
            if context["cancel"].is_set():
                self._close_pending_question(context, question_id, "cancelled")
                raise WorkerError("cancelled", "等待领导答复时任务被取消")
            remaining = context["request"].limits.total_timeout_sec - (
                time.monotonic() - context["started"]
            )
            if remaining <= 0:
                self._close_pending_question(context, question_id, "timed_out")
                raise WorkerError("timed_out", "等待领导答复时任务总预算耗尽")
            if event.wait(min(0.25, remaining)):
                with self.lock:
                    answer = context.get("leader_answer")
                    if answer and answer.get("question_id") == question_id:
                        context["leader_answer"] = None
                        event.clear()
                        return {"question_id": question_id, "answer": answer["answer"]}

    def _close_pending_question(self, context, question_id, reason):
        with self.lock:
            pending = context["record"].get("leader_question")
            if not pending or pending.get("question_id") != question_id:
                return
            context["record"].pop("leader_question", None)
            context["record"].setdefault("leader_dialogue", []).append({
                **pending,
                "status": reason,
                "closed_at": now(),
            })
            self.audit(context, "leader_question_closed", question_id=question_id, reason=reason)
            self._save(context["record"])

    def answer(self, task_id, question_id, answer):
        answer_text = _bounded_text(answer, name="answer", max_bytes=ANSWER_MAX_BYTES)
        with self.lock:
            context = self.active.get(task_id)
            if context:
                record = context["record"]
            else:
                row = self.db.execute("SELECT record FROM tasks WHERE id=?", (task_id,)).fetchone()
                if not row:
                    raise WorkerError("invalid_request", "任务不存在")
                import json
                record = json.loads(row[0])

            for entry in record.get("leader_dialogue", []):
                if entry.get("question_id") != question_id or entry.get("status") != "answered":
                    continue
                if entry.get("answer") != answer_text:
                    raise WorkerError("idempotency_conflict", "同一 question_id 已使用不同答复完成")
                return {
                    "task_id": task_id,
                    "question_id": question_id,
                    "status": "answered",
                    "revision": entry["answer_revision"],
                }

            if not context:
                raise WorkerError("invalid_request", "任务已结束，没有可回答的 pending question")
            pending = record.get("leader_question")
            if not pending:
                raise WorkerError("invalid_request", "当前任务没有等待领导答复的问题")
            if pending.get("question_id") != question_id:
                raise WorkerError("stale_question", "question_id 不是当前等待答复的问题")

            self._ensure_collaboration_context(context)
            answer_revision = record.get("revision", 0) + 1
            record.setdefault("leader_dialogue", []).append({
                **pending,
                "status": "answered",
                "answer": answer_text,
                "answered_at": now(),
                "answer_revision": answer_revision,
            })
            record.pop("leader_question", None)
            context["leader_answer"] = {"question_id": question_id, "answer": answer_text}
            self._save(record)
            self.audit(context, "leader_answer", question_id=question_id)
            context["leader_answer_event"].set()
            return {
                "task_id": task_id,
                "question_id": question_id,
                "status": "answered",
                "revision": answer_revision,
            }

    def _run(self, context):
        """只在 AGY prompt 中追加协作提示；基础执行、权限和收口逻辑全部复用 Runtime。"""
        original = context["request"]
        augmented = original.objective + _MEMBER_GUIDANCE
        if len(augmented) <= 12000:
            context["request"] = original.model_copy(update={"objective": augmented})
        try:
            return super()._run(context)
        finally:
            context["request"] = original
