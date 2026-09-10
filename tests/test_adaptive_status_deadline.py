"""锁定自适应 status 总等待截止点的最终即时快照语义。"""
import asyncio

import agy_worker.server as server_module
from agy_worker.models import McpStatusRequest


class StatusSequenceClient:
    def __init__(self, results):
        self.results=list(results)
        self.calls=[]

    def call(self, method, params=None, timeout=None):
        self.calls.append((method,params,timeout))
        assert method=='status'
        if not self.results:
            raise AssertionError('status 被额外调用')
        return self.results.pop(0)


def test_deadline_takes_final_immediate_snapshot_before_returning(monkeypatch):
    """最后一个 long-poll 刚结束后出现 terminal 时，不能返回已过期的 running/unchanged。"""
    client=StatusSequenceClient([
        {'task_id':'task-1','status':'running','revision':1,'unchanged':True},
        {
            'task_id':'task-1','session_id':'session-1','turn':1,
            'status':'succeeded','revision':2,
            'result':{'summary':'操作成功。','operation':{'exit_code':0}},
        },
    ])
    ticks=iter([100.0,100.0,151.0])
    monkeypatch.setattr(server_module.time,'monotonic',lambda:next(ticks))
    model=McpStatusRequest(task_id='task-1',after_revision=1)

    result=asyncio.run(server_module._coalesced_status(client,model))

    assert result['status']=='succeeded'
    assert result['revision']==2
    assert [call[1]['wait_ms'] for call in client.calls]==[25000,0]
    assert client.calls[-1][1]['after_revision']==1
