"""领导/成员问答协议的回归测试；不启动真实 AGY。"""
import asyncio
import concurrent.futures
import json
import time
from types import SimpleNamespace

import pytest
import tomlkit

import agy_worker.broker as broker_module
import agy_worker.manage as manage_module
import agy_worker.server as server_module
from agy_worker.collaboration import CollaborativeRuntime
from agy_worker.common import WorkerError
from agy_worker.controller_state import CONTROLLER_IMPLEMENTATION_FILES
from agy_worker.models import WorkerRequest


class ControlledFuture:
    def cancel(self):
        return False


@pytest.fixture
def runtime(tmp_path, monkeypatch):
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
    instance=CollaborativeRuntime(config)
    monkeypatch.setattr(instance.pool,'submit',lambda *args:ControlledFuture())
    yield instance
    instance.close()


def request(request_id='req-1'):
    return WorkerRequest.model_validate({
        'request_id':request_id,
        'workspace_id':'demo',
        'kind':'build',
        'objective':'编译并在缺少业务判断时询问领导。',
        'permissions':{'build':True,'log':True},
        'inputs':{'command_id':'compile'},
    })


def running_context(runtime, request_id='req-1'):
    state=runtime.submit(request(request_id))
    context=runtime.active[state['task_id']]
    context['started']=time.monotonic()
    context['record']['status']='running'
    runtime._save(context['record'])
    return state,context


def wait_for_question(runtime, task_id, timeout=1.0):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        state=runtime.status(task_id,wait_ms=0)
        if state.get('leader_question'):
            return state['leader_question']
        time.sleep(.01)
    raise AssertionError('成员问题未进入公开 task 状态')


def test_member_question_surfaces_and_answer_resumes_same_action(runtime):
    state,context=running_context(runtime)
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(runtime.action,context,{
            'action':'ask_leader',
            'arguments':{'question':'应该继续 A 还是 B？'},
        })
        question=wait_for_question(runtime,state['task_id'])

        assert question['question']=='应该继续 A 还是 B？'
        assert question['question_id'].startswith('question-')

        answered=runtime.answer(state['task_id'],question['question_id'],'继续 A。')
        member_result=pending.result(timeout=1)

    assert answered['status']=='answered'
    assert member_result=={'question_id':question['question_id'],'answer':'继续 A。'}
    assert 'leader_question' not in runtime.status(state['task_id'],wait_ms=0)
    record=context['record']
    assert record['leader_dialogue'][-1]['question']=='应该继续 A 还是 B？'
    assert record['leader_dialogue'][-1]['answer']=='继续 A。'


def test_answer_retry_is_idempotent_but_conflicting_retry_is_rejected(runtime):
    state,context=running_context(runtime,'req-idempotent-answer')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(runtime.action,context,{
            'action':'ask_leader','arguments':{'question':'是否继续？'},
        })
        question=wait_for_question(runtime,state['task_id'])
        first=runtime.answer(state['task_id'],question['question_id'],'继续。')
        assert pending.result(timeout=1)['answer']=='继续。'

    again=runtime.answer(state['task_id'],question['question_id'],'继续。')
    assert again==first
    with pytest.raises(WorkerError) as caught:
        runtime.answer(state['task_id'],question['question_id'],'停止。')
    assert caught.value.code=='idempotency_conflict'


def test_stale_question_id_cannot_answer_current_question(runtime):
    state,context=running_context(runtime,'req-stale-question')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(runtime.action,context,{
            'action':'ask_leader','arguments':{'question':'请选择。'},
        })
        question=wait_for_question(runtime,state['task_id'])
        with pytest.raises(WorkerError) as caught:
            runtime.answer(state['task_id'],'question-stale','错误答复')
        assert caught.value.code=='stale_question'
        runtime.answer(state['task_id'],question['question_id'],'正确答复')
        pending.result(timeout=1)


def test_member_wait_stops_when_task_is_cancelled(runtime):
    state,context=running_context(runtime,'req-cancel-question')
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pending=pool.submit(runtime.action,context,{
            'action':'ask_leader','arguments':{'question':'等待领导。'},
        })
        wait_for_question(runtime,state['task_id'])
        context['cancel'].set()
        with pytest.raises(WorkerError) as caught:
            pending.result(timeout=1)
    assert caught.value.code=='cancelled'
    assert 'leader_question' not in context['record']


def test_question_utf8_budget_and_per_task_quota_fail_closed(runtime):
    _state,context=running_context(runtime,'req-question-limits')
    with pytest.raises(WorkerError) as oversized:
        runtime.action(context,{
            'action':'ask_leader','arguments':{'question':'问'*1400},
        })
    assert oversized.value.code=='invalid_request'

    context['leader_questions']=8
    with pytest.raises(WorkerError) as quota:
        runtime.action(context,{
            'action':'ask_leader','arguments':{'question':'第九个问题'},
        })
    assert quota.value.code=='quota_exceeded'


def test_private_broker_exposes_only_bounded_leader_question_action():
    result=asyncio.run(broker_module.list_tools(None,None))
    tool=result.tools[0]
    schema=tool.input_schema
    assert 'ask_leader' in schema['properties']['action']['enum']
    assert 'shell' not in schema['properties']['action']['enum']
    assert '其他 MCP' in tool.description or '其他 MCP' in str(tool.description)


class RecordingClient:
    def __init__(self, results=None):
        self.results=list(results or [])
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        if self.results:
            return self.results.pop(0)
        return {'task_id':'task-1','question_id':'question-1','status':'answered','revision':4}


def capture_server(monkeypatch, client):
    captured={}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_module,'Server',FakeServer)
    server_module.build_server(client)
    return captured


def call_tool(handlers,name,arguments):
    return asyncio.run(handlers['on_call_tool'](
        None,SimpleNamespace(name=name,arguments=arguments)
    ))


def test_public_answer_tool_forwards_strict_request(monkeypatch):
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_answer',{
        'task_id':'task-1',
        'question_id':'question-1',
        'answer':'继续使用当前 workspace。',
    })

    assert result.is_error is False
    assert client.calls==[('answer',{
        'task_id':'task-1',
        'question_id':'question-1',
        'answer':'继续使用当前 workspace。',
    },None)]

    rejected=call_tool(handlers,'agy_answer',{
        'task_id':'task-1','question_id':'question-1','answer':'继续','extra':True,
    })
    assert rejected.is_error is True
    assert len(client.calls)==1


def test_status_coalescing_returns_pending_leader_question_immediately(monkeypatch):
    client=RecordingClient([
        {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
        {'task_id':'task-1','status':'running','revision':3,'leader_question':{
            'question_id':'question-1','question':'选 A 还是 B？','created_at':'2026-09-13T00:00:00Z',
        }},
    ])
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,'wait_ms':50000,
    })

    assert result.structured_content['leader_question']['question_id']=='question-1'
    assert len(client.calls)==2


def test_schema_generation_and_registration_include_answer_tool(monkeypatch,tmp_path):
    root=tmp_path/'worker'
    (root/'schemas').mkdir(parents=True)
    monkeypatch.setattr(manage_module,'ROOT',root)
    manage_module.schemas()
    answer_schema=json.loads((root/'schemas/agy_answer.json').read_text('utf-8'))
    assert set(answer_schema['required'])=={'task_id','question_id','answer'}

    codex_home=tmp_path/'codex'
    codex_home.mkdir()
    monkeypatch.setenv('CODEX_HOME',str(codex_home))
    path=codex_home/'config.toml'
    path.write_text('',encoding='utf-8')
    manage_module.register()
    document=tomlkit.parse(path.read_text('utf-8'))
    assert 'agy_answer' in document['mcp_servers']['agy_worker']['enabled_tools']


def test_controller_identity_hash_includes_collaboration_module():
    assert 'collaboration.py' in CONTROLLER_IMPLEMENTATION_FILES
