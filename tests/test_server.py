"""验证对外错误可由 Codex 直接纠正。"""
from pydantic import ValidationError
from agy_worker.models import WorkerRequest
from agy_worker.server import validation_body


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
    assert body['hint'].startswith('先调用 agy_capabilities')
