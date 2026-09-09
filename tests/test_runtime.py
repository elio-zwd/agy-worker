"""控制面权限与幂等性测试不消耗 AGY 模型额度。"""
import json
import subprocess
from pathlib import Path

import pytest

from agy_worker.common import WorkerError
from agy_worker.models import WorkerRequest,ContinueRequest
from agy_worker.runtime import MAX_INFLIGHT_TASKS, Runtime


class ControlledFuture:
    """不执行任务的可控 Future，仅用于验证 queued/running 取消状态机。"""

    def __init__(self, *, cancellable=True):
        self.cancellable = cancellable
        self.cancel_calls = 0

    def cancel(self):
        self.cancel_calls += 1
        return self.cancellable


@pytest.fixture
def runtime(tmp_path,monkeypatch):
    source=tmp_path/'source';source.mkdir();(source/'a.py').write_text('pass',encoding='utf-8')
    config=tmp_path/'runtime.toml'
    config.write_text(f"data_dir = '{tmp_path / 'data'}'\nenabled_kinds = ['build','browser','log']\n[workspaces.demo]\nsource = '{source}'\nallowed_commands = ['compile']\n",encoding='utf-8')
    instance=Runtime(config)
    monkeypatch.setattr(instance.pool,'submit',lambda *args:ControlledFuture())
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
    assert first['status']==second['status']=='cancelled'


def test_inflight_limit_rejects_17th_new_request_without_side_effects(runtime):
    states=[]
    for index in range(MAX_INFLIGHT_TASKS):
        states.append(runtime.submit(request(request_id=f'req-{index:02d}')))

    task_dirs_before={path.name for path in (runtime.root/'tasks').iterdir()}
    tasks_before=runtime.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]
    sessions_before=runtime.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]

    with pytest.raises(WorkerError) as caught:
        runtime.submit(request(request_id='req-over-capacity'))

    assert caught.value.code=='worker_busy'
    assert runtime.db.execute('SELECT COUNT(*) FROM tasks').fetchone()[0]==tasks_before
    assert runtime.db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==sessions_before
    assert {path.name for path in (runtime.root/'tasks').iterdir()}==task_dirs_before
    assert len(runtime.active)==MAX_INFLIGHT_TASKS


def test_idempotent_retry_bypasses_full_inflight_gate(runtime):
    first_request=request(request_id='req-first')
    first=runtime.submit(first_request)
    for index in range(1,MAX_INFLIGHT_TASKS):
        runtime.submit(request(request_id=f'req-{index:02d}'))

    again=runtime.submit(first_request)

    assert again['task_id']==first['task_id']
    assert len(runtime.active)==MAX_INFLIGHT_TASKS


def test_queued_cancel_finishes_immediately_without_waiting_for_worker(runtime):
    state=runtime.submit(request(request_id='req-queued-cancel'))
    context=runtime.active[state['task_id']]
    future=context['future']

    cancelled=runtime.cancel(state['task_id'],'排队任务无需等待执行槽')

    assert future.cancel_calls==1
    assert cancelled['status']=='cancelled'
    assert state['task_id'] not in runtime.active
    persisted=json.loads(runtime.db.execute('SELECT record FROM tasks WHERE id=?',(state['task_id'],)).fetchone()[0])
    assert persisted['status']=='cancelled'


def test_running_cancel_keeps_existing_cancelling_semantics(runtime,monkeypatch):
    running_future=ControlledFuture(cancellable=False)
    monkeypatch.setattr(runtime.pool,'submit',lambda *args:running_future)
    state=runtime.submit(request(request_id='req-running-cancel'))

    cancelling=runtime.cancel(state['task_id'],'运行中协作取消')

    assert running_future.cancel_calls==1
    assert cancelling['status']=='cancelling'
    assert runtime.active[state['task_id']]['cancel'].is_set()


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
    instance=Runtime(config);monkeypatch.setattr(instance.pool,'submit',lambda *args:ControlledFuture())
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
    instance=Runtime(config);monkeypatch.setattr(instance.pool,'submit',lambda *args:ControlledFuture())
    try:
        with pytest.raises(WorkerError,match='不属于'):
            instance.submit(request(workspace_id='repo',workspace_path=str(other)))
    finally:
        instance.close()
