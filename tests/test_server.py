"""验证对外错误与 MCP server 身份可由 Codex 直接纠正和核对。"""
import asyncio
import json
from types import SimpleNamespace

from pydantic import ValidationError

import agy_worker.server as server_module
from agy_worker.common import WorkerError
from agy_worker.controller_state import implementation_version
from agy_worker.models import WorkerRequest
from agy_worker.server import validation_body


class FakeClient:
    def __init__(self, result=None, error=None):
        self.result=result
        self.error=error

    def call(self, method, params=None, timeout=None):
        if self.error:
            raise self.error
        return self.result


def capture_call_tool(monkeypatch, client):
    captured={}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured['name']=name
            captured['version']=version
            captured['on_call_tool']=kwargs['on_call_tool']

    monkeypatch.setattr(server_module,'Server',FakeServer)
    server_module.build_server(client)
    return captured['on_call_tool']


def call_tool(callback, name, arguments):
    return asyncio.run(callback(None,SimpleNamespace(name=name,arguments=arguments)))


def test_limit_validation_is_actionable():
    try:
        WorkerRequest.model_validate({
            'request_id':'bad-limits','workspace_id':'demo','kind':'vision','objective':'读取图片',
            'permissions':{'vision':True},'inputs':{'files':['a.png']},
            'limits':{'summary_max_bytes':20000,'artifact_max_bytes':500000}})
    except ValidationError as error:
        body=validation_body(error)
    assert 'summary_max_bytes 最大为 16384' in body['message']
    assert 'artifact_max_bytes 最小为 1048576' in body['message']
    assert '省略 limits' in body['hint']
    assert 'agy://capabilities' in body['hint']


def test_status_uses_short_text_and_canonical_structured_content(monkeypatch):
    compact_status={
        'task_id':'task-1','session_id':'session-1','turn':1,
        'status':'running','revision':5,'progress':{'agy_pid':1234,'captured_bytes':2048},
    }
    callback=capture_call_tool(monkeypatch,FakeClient(result=compact_status))

    result=call_tool(callback,'agy_status',{'task_id':'task-1'})

    assert result.structured_content==compact_status
    assert len(result.content)==1
    assert result.content[0].type=='text'
    assert result.content[0].text!=json.dumps(compact_status,ensure_ascii=False)
    assert len(result.content[0].text.encode('utf-8'))<=256


def test_compact_status_text_exposes_unchanged_and_terminal_summary():
    unchanged=server_module._compact_tool_text('agy_status',{
        'task_id':'task-1','status':'running','revision':5,'unchanged':True,
    })
    terminal=server_module._compact_tool_text('agy_status',{
        'task_id':'task-1','status':'succeeded','revision':35,
        'result':{'summary':'操作成功，日志采集完成。','warnings':['不应进入文本'],'artifacts':[{'artifact_id':'x'}]},
    })

    assert 'running rev=5' in unchanged
    assert '继续轮询' in unchanged
    assert '无需用户消息' in unchanged
    assert 'succeeded rev=35' in terminal
    assert '操作成功，日志采集完成。' in terminal
    assert 'warnings' not in terminal
    assert 'artifacts' not in terminal
    assert len(unchanged.encode('utf-8'))<=256
    assert len(terminal.encode('utf-8'))<=256


def test_artifact_text_uses_single_text_payload(monkeypatch):
    envelope={
        'content_type':'json',
        'value':{'artifact_id':'operation-log','text':'line 1\nline 2','truncated':False},
    }
    callback=capture_call_tool(monkeypatch,FakeClient(result=envelope))

    result=call_tool(callback,'agy_artifact_read',{
        'task_id':'task-1','artifact_id':'operation-log','view':'text',
    })

    assert result.structured_content is None
    assert len(result.content)==1
    assert result.content[0].type=='text'
    payload=json.loads(result.content[0].text)
    assert payload['artifact_id']=='operation-log'
    assert payload['text']=='line 1\nline 2'


def test_worker_error_keeps_structured_body_without_duplicate_json(monkeypatch):
    callback=capture_call_tool(monkeypatch,FakeClient(error=WorkerError('worker_busy','busy')))

    result=call_tool(callback,'agy_status',{'task_id':'task-1'})

    assert result.is_error is True
    assert result.structured_content['error']=='worker_busy'
    assert result.structured_content['message']=='busy'
    assert result.content[0].text!=json.dumps(result.structured_content,ensure_ascii=False)
    assert 'worker_busy' in result.content[0].text
    assert 'busy' in result.content[0].text
    assert len(result.content[0].text.encode('utf-8'))<=256


def test_server_uses_package_metadata_version(monkeypatch):
    captured = {}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured['name'] = name
            captured['version'] = version
            captured['kwargs'] = kwargs

    monkeypatch.setattr(server_module, 'Server', FakeServer)
    server_module.build_server(object())

    assert captured['name'] == 'elio-agy-worker'
    assert captured['version'] == implementation_version() == '0.3.2'
