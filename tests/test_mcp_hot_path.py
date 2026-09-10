"""验证 MCP 热路径只暴露决策所需契约，并在一次 status 调用内合并噪声进度。"""
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


class SubmitClient:
    def __init__(self):
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        if method!='submit':
            raise AssertionError(f'unexpected method: {method}')
        return {
            'task_id':'task-1','session_id':'session-1','turn':1,
            'status':'queued','revision':1,
        }


class StatusSequenceClient:
    def __init__(self, results):
        self.results=list(results)
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        if method!='status':
            raise AssertionError(f'unexpected method: {method}')
        if not self.results:
            raise AssertionError('status 被额外调用')
        return self.results.pop(0)


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


def list_tools(handlers):
    return asyncio.run(handlers['on_list_tools'](None,SimpleNamespace()))


def test_capabilities_tool_returns_compact_routing_projection(monkeypatch):
    """热工具只暴露定位 workspace/command 所需字段，不复制冷诊断。"""
    client=RecordingClient()
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_capabilities',{})

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


def test_worker_and_continue_schemas_hide_unavailable_permissions_and_cold_limits(monkeypatch):
    """模型不应被公开 schema 诱导去填写 Runtime 永远拒绝或热路径无需调整的字段。"""
    handlers=capture_server(monkeypatch,RecordingClient())
    result=list_tools(handlers)
    schemas={
        tool.name:tool.model_dump(by_alias=True)['inputSchema']
        for tool in result.tools
    }

    for name in ('agy_worker','agy_continue'):
        schema=schemas[name]
        properties=schema['properties']
        permission_ref=properties['permissions']['$ref'].split('/')[-1]
        limit_ref=properties['limits']['$ref'].split('/')[-1]
        permission_properties=schema['$defs'][permission_ref]['properties']
        limit_properties=schema['$defs'][limit_ref]['properties']

        assert 'shell' not in schema['properties']['kind']['enum']
        assert 'shell' not in permission_properties
        assert 'code_write' not in permission_properties
        assert 'write_paths' not in permission_properties
        assert 'write_reason' not in permission_properties
        assert set(limit_properties)=={'total_timeout_sec'}


def test_status_schema_defaults_to_50s_and_allows_50_to_600s(monkeypatch):
    """公开 schema 必须把模型引导到默认 50 秒、显式 50～600 秒的等待预算。"""
    handlers=capture_server(monkeypatch,RecordingClient())
    result=list_tools(handlers)
    status_schema=next(
        tool.model_dump(by_alias=True)['inputSchema']
        for tool in result.tools if tool.name=='agy_status'
    )

    wait_schema=status_schema['properties']['wait_ms']
    assert wait_schema['default']==50000
    assert wait_schema['minimum']==50000
    assert wait_schema['maximum']==600000


def test_worker_mcp_request_expands_safe_internal_defaults(monkeypatch):
    """热 schema 只收必要字段，传给 Controller 前仍补齐内部安全默认值。"""
    client=SubmitClient()
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_worker',{
        'request_id':'req-1',
        'workspace_id':'demo',
        'kind':'build',
        'objective':'编译测试，只采集结果。',
        'permissions':{'build':True,'log':True},
        'inputs':{'command_id':'compile'},
        'limits':{'total_timeout_sec':1200},
    })

    assert result.is_error is False
    assert len(client.calls)==1
    method,payload,timeout=client.calls[0]
    assert method=='submit' and timeout is None
    assert payload['limits']=={
        'total_timeout_sec':1200,
        'summary_max_bytes':16384,
        'artifact_max_bytes':536870912,
    }
    assert payload['permissions']['shell'] is False
    assert payload['permissions']['code_write'] is False


def test_worker_mcp_rejects_hidden_shell_and_artifact_tuning_before_controller(monkeypatch):
    """旧/手写调用若仍发送隐藏字段，应在 MCP 边界明确失败而不是进入 Runtime。"""
    client=SubmitClient()
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_worker',{
        'request_id':'req-1',
        'workspace_id':'demo',
        'kind':'build',
        'objective':'编译测试。',
        'permissions':{'build':True,'shell':True},
        'inputs':{'command_id':'compile'},
        'limits':{'artifact_max_bytes':20000},
    })

    assert result.is_error is True
    assert result.structured_content['error']=='invalid_request'
    assert client.calls==[]


def test_status_rejects_wait_outside_public_range_before_controller(monkeypatch):
    """低于 50 秒或高于 600 秒的外部等待值必须在 MCP 边界被拒绝。"""
    client=StatusSequenceClient([])
    handlers=capture_server(monkeypatch,client)

    too_short=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,'wait_ms':49999,
    })
    too_long=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,'wait_ms':600001,
    })

    assert too_short.is_error is True
    assert too_short.structured_content['error']=='invalid_request'
    assert too_long.is_error is True
    assert too_long.structured_content['error']=='invalid_request'
    assert client.calls==[]


def test_status_coalesces_progress_and_unchanged_until_terminal(monkeypatch):
    """单次 MCP long-poll 应吞掉中间 progress/unchanged，避免每个 revision 都返回 Codex。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
        {'task_id':'task-1','status':'running','revision':2,'unchanged':True},
        {
            'task_id':'task-1','session_id':'session-1','turn':1,'status':'succeeded','revision':3,
            'result':{'summary':'操作成功，日志采集完成。','operation':{'exit_code':0}},
        },
    ])
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,'wait_ms':50000,
    })

    assert result.structured_content['status']=='succeeded'
    assert result.structured_content['revision']==3
    assert [call[1]['after_revision'] for call in client.calls]==[1,2,2]
    assert all(0<call[1]['wait_ms']<=25000 for call in client.calls)


def test_status_default_50s_is_split_into_controller_long_polls(monkeypatch):
    """省略 wait_ms 时使用 50 秒总预算，但 Controller 单段仍不得超过 25 秒。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
        {
            'task_id':'task-1','session_id':'session-1','turn':1,'status':'succeeded','revision':3,
            'result':{'summary':'操作成功。','operation':{'exit_code':0}},
        },
    ])
    ticks=iter([100.0,100.0,120.0])
    monkeypatch.setattr(server_module.time,'monotonic',lambda:next(ticks))
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,
    })

    assert result.structured_content['status']=='succeeded'
    assert [call[1]['wait_ms'] for call in client.calls]==[25000,25000]


def test_status_600s_budget_returns_immediately_when_terminal_arrives(monkeypatch):
    """600 秒只是最大等待预算；终态出现后必须立即返回且不继续内部轮询。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
        {
            'task_id':'task-1','session_id':'session-1','turn':1,'status':'succeeded','revision':3,
            'result':{'summary':'操作成功。','operation':{'exit_code':0}},
        },
    ])
    ticks=iter([100.0,100.0,101.0])
    monkeypatch.setattr(server_module.time,'monotonic',lambda:next(ticks))
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,'wait_ms':600000,
    })

    assert result.structured_content['status']=='succeeded'
    assert [call[1]['wait_ms'] for call in client.calls]==[25000,25000]
    assert len(client.calls)==2


def test_status_without_after_revision_reads_immediate_snapshot(monkeypatch):
    """没有已知 revision 时只读当前快照，不把公开 50 秒默认值透传给 Controller。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':7,'progress':{'captured_bytes':100}},
    ])
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{'task_id':'task-1'})

    assert result.structured_content['status']=='running'
    assert result.structured_content['revision']==7
    assert client.calls[0][1]['wait_ms']==0
    assert len(client.calls)==1


def test_status_coalescing_uses_one_total_wait_budget(monkeypatch):
    """中间 revision 不能把 50 秒总预算重置成每轮新的 50 秒。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':2,'progress':{'captured_bytes':100}},
        {'task_id':'task-1','status':'running','revision':3,'progress':{'captured_bytes':200}},
        {
            'task_id':'task-1','session_id':'session-1','turn':1,'status':'succeeded','revision':4,
            'result':{'summary':'操作成功。','operation':{'exit_code':0}},
        },
    ])
    ticks=iter([100.0,100.0,135.0,145.0])
    monkeypatch.setattr(server_module.time,'monotonic',lambda:next(ticks))
    handlers=capture_server(monkeypatch,client)

    result=call_tool(handlers,'agy_status',{
        'task_id':'task-1','after_revision':1,
    })

    assert result.structured_content['status']=='succeeded'
    waits=[call[1]['wait_ms'] for call in client.calls]
    assert waits==[25000,15000,5000]
