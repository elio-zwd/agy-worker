"""领导答复不能在任务取消或总超时后被错误接受。"""
import time

import pytest

from agy_worker.common import WorkerError
from agy_worker.collaboration import CollaborativeRuntime
from agy_worker.models import WorkerRequest


class ControlledFuture:
    def cancel(self):
        return False


def make_runtime(tmp_path, monkeypatch):
    source=tmp_path/'source'
    source.mkdir()
    (source/'a.py').write_text('pass',encoding='utf-8')
    config=tmp_path/'runtime.toml'
    config.write_text(
        f"data_dir = '{tmp_path / 'data'}'\n"
        "enabled_kinds = ['build']\n"
        "[workspaces.demo]\n"
        f"source = '{source}'\n"
        "allowed_commands = ['compile']\n",
        encoding='utf-8',
    )
    runtime=CollaborativeRuntime(config)
    monkeypatch.setattr(runtime.pool,'submit',lambda *args:ControlledFuture())
    return runtime


def make_pending(runtime, *, request_id, started):
    request=WorkerRequest.model_validate({
        'request_id':request_id,'workspace_id':'demo','kind':'build','objective':'测试问答竞态',
        'permissions':{'build':True},'inputs':{'command_id':'compile'},
        'limits':{'total_timeout_sec':10},
    })
    state=runtime.submit(request)
    context=runtime.active[state['task_id']]
    context['started']=started
    context['record']['status']='running'
    runtime._ensure_collaboration_context(context)
    question={
        'question_id':'question-race','question':'还能继续吗？','created_at':'2026-09-13T00:00:00Z',
    }
    context['record']['leader_question']=question
    runtime._save(context['record'])
    return state,context


def test_answer_rejects_cancelled_task_even_if_question_is_still_pending(tmp_path,monkeypatch):
    runtime=make_runtime(tmp_path,monkeypatch)
    try:
        state,context=make_pending(runtime,request_id='req-answer-cancel-race',started=time.monotonic())
        context['cancel'].set()

        with pytest.raises(WorkerError) as caught:
            runtime.answer(state['task_id'],'question-race','继续。')

        assert caught.value.code=='cancelled'
        assert 'leader_question' not in context['record']
        assert context['record']['leader_dialogue'][-1]['status']=='cancelled'
    finally:
        runtime.close()


def test_answer_rejects_task_after_total_timeout_even_before_cancel_event(tmp_path,monkeypatch):
    runtime=make_runtime(tmp_path,monkeypatch)
    try:
        state,context=make_pending(runtime,request_id='req-answer-timeout-race',started=time.monotonic()-11)

        with pytest.raises(WorkerError) as caught:
            runtime.answer(state['task_id'],'question-race','继续。')

        assert caught.value.code=='timed_out'
        assert 'leader_question' not in context['record']
        assert context['record']['leader_dialogue'][-1]['status']=='timed_out'
    finally:
        runtime.close()
