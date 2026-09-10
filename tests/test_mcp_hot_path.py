"""验证 MCP 热路径只返回决策所需信息，完整诊断留在冷资源。"""
import asyncio
import json
from types import SimpleNamespace

import pytest

import agy_worker.server as server_module
from agy_worker.runtime import Runtime


@pytest.fixture
def runtime(tmp_path):
    source=tmp_path/'source';source.mkdir();(source/'a.py').write_text('pass',encoding='utf-8')
    config=tmp_path/'runtime.toml'
    config.write_text(
        f"data_dir = '{tmp_path / 'data'}'\n"
        "enabled_kinds = ['build','test','log']\n"
        "[workspaces.demo]\n"
        f"source = '{source}'\n"
        "allowed_commands = ['compile','test']\n",
        encoding='utf-8',
    )
    instance=Runtime(config)
    yield instance
    instance.close()


def test_routing_capabilities_omit_cold_diagnostics(runtime):
    """默认工具视图不应把 Controller、limits、权限等冷诊断灌入 Codex 上下文。"""
    result=runtime.capabilities(view='routing')

    assert set(result)=={'schema_version','workspaces'}
    assert len(result['workspaces'])==1
    workspace=result['workspaces'][0]
    assert set(workspace)=={'workspace_id','registered_path','allowed_commands'}
    assert workspace['workspace_id']=='demo'
    assert workspace['allowed_commands']==['compile','test']


def test_full_capabilities_preserve_diagnostics_for_cold_resource(runtime):
    """瘦身热路径不能删除原有诊断能力。"""
    result=runtime.capabilities(view='full')

    assert result['controller']['protocol_version']==2
    assert result['limits']['total_timeout_sec']['max']==1800
    assert result['permissions']['code_write'] is False
    assert result['enabled_kinds']==['build','test','log']


class RecordingClient:
    def __init__(self):
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        if method!='capabilities':
            raise AssertionError(f'unexpected method: {method}')
        if params=={'view':'routing'}:
            return {
                'schema_version':1,
                'workspaces':[{'workspace_id':'demo','registered_path':'D:/demo','allowed_commands':['compile']}],
            }
        if params=={'view':'full'}:
            return {
                'schema_version':1,
                'enabled_kinds':['build'],
                'controller':{'protocol_version':2},
                'limits':{},
                'workspaces':[{'workspace_id':'demo','registered_path':'D:/demo','allowed_commands':['compile']}],
                'permissions':{'code_write':False},
                'usage':'cold details',
            }
        raise AssertionError(f'unexpected capabilities params: {params!r}')


def capture_server(monkeypatch, client):
    captured={}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_module,'Server',FakeServer)
    server_module.build_server(client)
    return captured


def test_capabilities_tool_requests_routing_view(monkeypatch):
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=asyncio.run(handlers['on_call_tool'](
        None,SimpleNamespace(name='agy_capabilities',arguments={})
    ))

    assert client.calls==[('capabilities',{'view':'routing'},None)]
    assert set(result.structured_content)=={'schema_version','workspaces'}


def test_capabilities_resource_requests_full_view(monkeypatch):
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=asyncio.run(handlers['on_read_resource'](
        None,SimpleNamespace(uri='agy://capabilities')
    ))
    payload=json.loads(result.contents[0].text)

    assert client.calls==[('capabilities',{'view':'full'},None)]
    assert payload['controller']['protocol_version']==2
    assert payload['permissions']['code_write'] is False
