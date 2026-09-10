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


def test_status_after_revision_timeout_returns_compact_unchanged(runtime):
    state=runtime.submit(request(request_id='req-status-unchanged'))

    result=runtime.status(state['task_id'],after_revision=state['revision'],wait_ms=0)

    assert result=={
        'task_id':state['task_id'],
        'status':'queued',
        'revision':state['revision'],
        'unchanged':True,
    }
    encoded=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    assert len(encoded)<=256


def test_public_running_state_is_compact(runtime):
    state=runtime.submit(request(request_id='req-running-public'))
    context=runtime.active[state['task_id']]
    context['record']['status']='running'
    context['record']['progress']={'agy_pid':1234,'captured_bytes':2048}
    runtime._save(context['record'])

    result=runtime.status(state['task_id'],wait_ms=0)

    assert set(result)=={'task_id','session_id','turn','status','revision','progress'}
    assert result['progress']=={'agy_pid':1234,'captured_bytes':2048}
    encoded=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    assert len(encoded)<=512


def test_terminal_public_result_is_compact_and_keeps_artifact_drill_down(runtime):
    state=runtime.submit(request(request_id='req-terminal-compact'))
    context=runtime.active[state['task_id']]
    errors=[{'file':f'src/Error{index}.kt','line':index+1,'message':'错误'+('很长的诊断信息'*80)} for index in range(20)]
    warnings=[{'file':f'src/Warning{index}.kt','line':index+1,'message':'警告'+('很长的诊断信息'*80)} for index in range(20)]
    diagnostics_path=context['directory']/'errors.json'
    diagnostics_path.write_text(json.dumps({'errors':errors,'warnings':warnings},ensure_ascii=False),encoding='utf-8')
    context['artifacts'].add('errors',diagnostics_path)
    full_result={
        'schema_version':1,
        'status':'failed',
        'summary':'操作失败或未执行，请查看错误原文及证据。',
        'workspace_id':'demo',
        'workspace_path':str(context['source']),
        'input_snapshot':'snapshot-value',
        'agy':{'exit_code':1,'result_status':'FAILURE','pid':9999,'error':'agy detail'},
        'operation':{
            'command_id':'compile',
            'exit_code':1,
            'duration_ms':1234,
            'termination_reason':None,
            'errors':errors,
            'warnings':warnings,
            'total_errors':20,
            'total_warnings':20,
            'evidence':{'artifact_id':'operation-log'},
        },
        'source_changed':False,
        'changed_files':[],
        'errors':errors,
        'warnings':warnings,
        'total_errors':20,
        'total_warnings':20,
        'termination_reason':'operation_failed',
        'enforcement':{'hook_and_broker':True,'os_isolation':False,'code_write':False},
        'artifacts':[
            {'artifact_id':f'artifact-{index}','size_bytes':1000+index,'sha256':'a'*64,
             'media_type':'text/plain','created_at':'2026-09-10T00:00:00Z','sensitive':False}
            for index in range(12)
        ],
        'result_artifact_id':'result',
        'artifact_count':14,
        'truncated':True,
    }
    result_path=context['directory']/'result.json'
    result_path.write_text(json.dumps(full_result,ensure_ascii=False),encoding='utf-8')
    context['artifacts'].add('result',result_path)
    context['record'].update(status='failed',result=full_result)
    runtime._save(context['record'])

    public=runtime.status(state['task_id'],wait_ms=0)
    compact=public['result']

    assert public['status']=='failed'
    assert compact['schema_version']==2
    assert compact['operation']['exit_code']==1
    assert compact['operation']['total_errors']==20
    assert compact['operation']['total_warnings']==20
    assert compact['diagnostics_artifact_id']=='errors'
    assert compact['result_artifact_id']=='result'
    assert 'errors' not in compact
    assert 'warnings' not in compact
    assert 'artifacts' not in compact
    assert 'workspace_path' not in compact
    assert 'input_snapshot' not in compact
    assert 'agy' not in compact
    assert 'enforcement' not in compact
    encoded=json.dumps(public,ensure_ascii=False,separators=(',',':')).encode('utf-8')
    assert len(encoded)<=1536

    diagnostics=runtime.read_artifact(state['task_id'],'errors',view='text',start_line=1,line_count=20)
    assert diagnostics['artifact_id']=='errors'
    assert diagnostics['text']


def test_source_changed_count_survives_record_preview_truncation(runtime):
    state=runtime.submit(request(request_id='req-source-changed-count'))
    context=runtime.active[state['task_id']]
    preview=[f'src/File{index}.kt' for index in range(5)]
    context['record'].update(
        status='failed',
        result={
            'schema_version':1,
            'status':'failed',
            'summary':'源码发生变化。',
            'source_changed':True,
            'changed_files':preview,
            'changed_files_count':12,
            'termination_reason':'unexpected_source_change',
            'artifacts':[],
            'artifact_count':0,
            'result_artifact_id':'result',
            'truncated':True,
        },
    )
    runtime._save(context['record'])

    compact=runtime.status(state['task_id'],wait_ms=0)['result']

    assert compact['changed_files_count']==12
    assert compact['changed_files_preview']==preview


def test_public_runtime_error_is_utf8_bounded(runtime):
    state=runtime.submit(request(request_id='req-runtime-error-budget'))
    context=runtime.active[state['task_id']]
    original_message='错'*1500
    context['record'].update(status='failed',error={'code':'runtime_error','message':original_message})
    runtime._save(context['record'])

    public=runtime.status(state['task_id'],wait_ms=0)
    encoded=json.dumps(public,ensure_ascii=False,separators=(',',':')).encode('utf-8')

    assert public['error']['code']=='runtime_error'
    assert public['error']['message']
    assert len(public['error']['message'].encode('utf-8'))<=1024
    assert len(encoded)<=2048
    persisted=json.loads(runtime.db.execute('SELECT record FROM tasks WHERE id=?',(state['task_id'],)).fetchone()[0])
    assert persisted['error']['message']==original_message


def test_terminal_status_wins_over_same_after_revision(runtime):
    state=runtime.submit(request(request_id='req-terminal-same-rev'))
    context=runtime.active[state['task_id']]
    context['record'].update(
        status='succeeded',
        result={
            'schema_version':1,
            'status':'succeeded',
            'summary':'操作成功，日志采集完成。',
            'source_changed':False,
            'termination_reason':None,
            'artifacts':[],
            'artifact_count':0,
            'result_artifact_id':'result',
            'truncated':False,
        },
    )
    runtime._save(context['record'])
    terminal_revision=context['record']['revision']

    result=runtime.status(state['task_id'],after_revision=terminal_revision,wait_ms=0)

    assert result['status']=='succeeded'
    assert 'result' in result
    assert 'unchanged' not in result


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
