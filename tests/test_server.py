"""验证对外错误与 MCP server 身份可由 Codex 直接纠正和核对。"""
from pydantic import ValidationError

import agy_worker.server as server_module
from agy_worker.controller_state import implementation_version
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
    assert captured['version'] == implementation_version() == '0.3.1'
