"""控制面权限与幂等性测试不消耗 AGY 模型额度。"""
import json
import subprocess
from pathlib import Path
import pytest
from agy_worker.common import WorkerError
from agy_worker.models import WorkerRequest,ContinueRequest
from agy_worker.runtime import Runtime


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'a.py').write_text('pass',encoding='utf-8')
    config=tmp_path/'runtime.toml'
    config.write_text(f"data_dir = '{tmp_path / 'data'}'\nenabled_kinds = ['build','browser','log']\n[workspaces.demo]\nsource = '{source}'\nallowed_commands = ['compile']\n",encoding='utf-8')
    instance=Runtime(config)
    monkeypatch.setattr(instance.pool,'submit',lambda *args:None)
    yield instance
    instance.close()


def request(**overrides):
    value={'request_id':'req-1','workspace_id':'demo','kind':'build','objective':'编译，不修改源码',
           'permissions':{'build':True,'log':True},'inputs':{'command_id':'compile'}}
    value.update(overrides)
    return WorkerRequest.model_validate(value)


def test_idempotency_and_conflict(runtime):
    first=runtime.submit(request());again=runtime.submit(request())
    assert first['task_id']==again['task_id']
    with pytest.raises(WorkerError,match='不同请求'):
        runtime.submit(request(objective='另一个目标'))


def test_unregistered_command_denied(runtime):
    with pytest.raises(WorkerError):
        runtime.submit(request(inputs={'command_id':'arbitrary'}))


def test_source_write_cannot_enable_without_isolation(runtime):
    with pytest.raises(WorkerError,match='系统隔离'):
        runtime.submit(request(permissions={'build':True,'code_write':True,'write_paths':['a.py'],'write_reason':'测试'}))


def test_outer_browser_scope(runtime):
    with pytest.raises(WorkerError,match='未授权'):
        runtime.submit(request(kind='browser',permissions={'browser':True,'origins':['https://example.com']},inputs={'url':'https://other.example'}))


def test_hook_only_allows_private_broker(runtime):
    state=runtime.submit(request())
    context=runtime.active[state['task_id']]
    assert runtime.hook(context,{'toolCall':{'name':'run_command','args':{'CommandLine':'echo test'}}})['decision']=='deny'
    assert runtime.hook(context,{'toolCall':{'name':'write_to_file','args':{}}})['decision']=='deny'
    assert runtime.hook(context,{'toolCall':{'name':'call_mcp_tool','args':{'ServerName':'github-mcp-server','ToolName':'create_issue'}}})['decision']=='deny'
    assert runtime.hook(context,{'toolCall':{'name':'call_mcp_tool','args':{'ServerName':'agy-worker-broker','ToolName':'worker_action'}}})['decision']=='allow'


def test_cancel_idempotent(runtime):
    state=runtime.submit(request())
    first=runtime.cancel(state['task_id'],'测试取消')
    second=runtime.cancel(state['task_id'],'测试取消')
    assert first['status']==second['status']=='cancelling'


def test_snapshot_includes_local_submodule(runtime, monkeypatch):
    source=Path(runtime.config['workspaces']['demo']['source'])
    (source/'.git').mkdir()
    module=source/'module';module.mkdir()
    (module/'.git').write_text('gitdir: unused',encoding='utf-8')
    (module/'local.py').write_text('本地未提交内容',encoding='utf-8')
    def listing(argv, **kwargs):
        files=b'local.py\0' if Path(argv[2])==module else b'a.py\0module\0'
        return subprocess.CompletedProcess(argv,0,files,b'')
    monkeypatch.setattr(subprocess,'run',listing)
    state=runtime.submit(request())
    context=runtime.active[state['task_id']]
    runtime._prepare(context)
    assert (context['workspace']/'module/local.py').read_text('utf-8')=='本地未提交内容'
    assert not (context['workspace']/'module/.git').exists()


def test_registered_git_worktree_is_accepted(tmp_path,monkeypatch):
    source=tmp_path/'repository';source.mkdir()
    subprocess.run(['git','init',str(source)],check=True,capture_output=True)
    (source/'a.py').write_text('main',encoding='utf-8')
    subprocess.run(['git','-C',str(source),'-c','user.name=Test','-c','user.email=test@example.invalid',
                    'add','a.py'],check=True,capture_output=True)
    subprocess.run(['git','-C',str(source),'-c','user.name=Test','-c','user.email=test@example.invalid',
                    'commit','-m','test'],check=True,capture_output=True)
    worktree=tmp_path/'feature'
    subprocess.run(['git','-C',str(source),'worktree','add','--detach',str(worktree)],check=True,capture_output=True)
    config=tmp_path/'runtime.toml'
    config.write_text(f"data_dir = '{tmp_path / 'data'}'\nenabled_kinds = ['build']\n[workspaces.repo]\nsource = '{source}'\nallowed_commands = ['compile']\n",encoding='utf-8')
    instance=Runtime(config);monkeypatch.setattr(instance.pool,'submit',lambda *args:None)
    try:
        value=request(workspace_id='repo',workspace_path=str(worktree))
        state=instance.submit(value)
        assert instance.active[state['task_id']]['source']==worktree.resolve()
        capability=instance.capabilities()['workspaces'][0]
        assert str(worktree.resolve()) in capability['known_worktrees']
        first=instance.active.pop(state['task_id'])
        first['session']['conversation_id']='conversation-test'
        instance._session(first['session'])
        continued=ContinueRequest.model_validate({
            'request_id':'req-2','workspace_id':'repo','kind':'build','objective':'续编译，不修改源码',
            'permissions':{'build':True,'log':True},'inputs':{'command_id':'compile'},
            'session_id':state['session_id'],'expected_turn':1})
        next_state=instance.submit(continued)
        assert instance.active[next_state['task_id']]['source']==worktree.resolve()
    finally:
        instance.close()


def test_unrelated_git_repository_is_denied(tmp_path,monkeypatch):
    source=tmp_path/'registered';other=tmp_path/'other'
    for path in (source,other):
        path.mkdir();subprocess.run(['git','init',str(path)],check=True,capture_output=True)
    config=tmp_path/'runtime.toml'
    config.write_text(f"data_dir = '{tmp_path / 'data'}'\nenabled_kinds = ['build']\n[workspaces.repo]\nsource = '{source}'\nallowed_commands = ['compile']\n",encoding='utf-8')
    instance=Runtime(config);monkeypatch.setattr(instance.pool,'submit',lambda *args:None)
    try:
        with pytest.raises(WorkerError,match='不属于'):
            instance.submit(request(workspace_id='repo',workspace_path=str(other)))
    finally:
        instance.close()
