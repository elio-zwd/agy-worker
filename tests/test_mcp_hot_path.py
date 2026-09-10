"""验证 MCP 热路径只返回决策所需信息，完整诊断留在冷资源。"""
import asyncio
import json
from types import SimpleNamespace

import agy_worker.server as server_module


FULL_CAPABILITIES={
    'schema_version':1,
    'enabled_kinds':['build','test','log','browser','vision'],
    'controller':{
        'protocol_version':2,
        'single_runtime':True,
        'max_concurrent_tasks':1,
        'max_inflight_tasks':16,
    },
    'limits':{
        'total_timeout_sec':{'default':300,'min':10,'max':1800},
        'summary_max_bytes':{'default':16384,'min':2048,'max':16384},
    },
    'workspaces':[
        {
            'workspace_id':'demo',
            'registered_path':'D:/demo',
            'git':True,
            'supports_worktrees':True,
            'allowed_commands':['compile','test'],
            'known_worktrees':['D:/demo','D:/demo-pr'],
        },
        {
            'workspace_id':'other',
            'registered_path':'D:/other',
            'git':False,
            'supports_worktrees':False,
            'allowed_commands':['check'],
        },
    ],
    'permissions':{
        'code_write':False,
        'arbitrary_shell':False,
        'os_isolation':False,
        'enforcement':'hook_and_broker',
    },
    'usage':'通常省略 limits 使用默认值。',
}


class RecordingClient:
    def __init__(self):
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        if method!='capabilities':
            raise AssertionError(f'unexpected method: {method}')
        return FULL_CAPABILITIES


def capture_server(monkeypatch, client):
    captured={}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_module,'Server',FakeServer)
    server_module.build_server(client)
    return captured


def test_capabilities_tool_returns_compact_routing_projection(monkeypatch):
    """热工具只暴露定位 workspace/command 所需字段，不复制冷诊断。"""
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=asyncio.run(handlers['on_call_tool'](
        None,SimpleNamespace(name='agy_capabilities',arguments={})
    ))

    assert client.calls==[('capabilities',None,None)]
    assert result.structured_content=={
        'schema_version':1,
        'workspaces':[
            {
                'workspace_id':'demo',
                'registered_path':'D:/demo',
                'allowed_commands':['compile','test'],
                'known_worktrees':['D:/demo','D:/demo-pr'],
            },
            {
                'workspace_id':'other',
                'registered_path':'D:/other',
                'allowed_commands':['check'],
            },
        ],
    }
    assert 'controller' not in result.structured_content
    assert 'limits' not in result.structured_content
    assert 'permissions' not in result.structured_content


def test_capabilities_resource_preserves_full_diagnostics(monkeypatch):
    """冷资源仍返回完整 Controller、limits、权限和 workspace 元数据。"""
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=asyncio.run(handlers['on_read_resource'](
        None,SimpleNamespace(uri='agy://capabilities')
    ))
    payload=json.loads(result.contents[0].text)

    assert client.calls==[('capabilities',None,None)]
    assert payload==FULL_CAPABILITIES


def test_workspaces_resource_preserves_full_worktree_metadata(monkeypatch):
    """需要 worktree 诊断时仍可显式走冷资源，不牺牲现有能力。"""
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=asyncio.run(handlers['on_read_resource'](
        None,SimpleNamespace(uri='agy://workspaces')
    ))
    payload=json.loads(result.contents[0].text)

    assert payload=={'schema_version':1,'workspaces':FULL_CAPABILITIES['workspaces']}
    assert payload['workspaces'][0]['known_worktrees']==['D:/demo','D:/demo-pr']
