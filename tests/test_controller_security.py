"""Controller 连接元数据必须在任何网络访问前完成严格校验。"""
import json

import pytest

from agy_worker.common import WorkerError
from agy_worker.controller_client import ControllerClient


class RejectingOpener:
    """若测试触发网络访问就留下证据；state 校验应更早失败。"""

    def __init__(self):
        self.called = False

    def open(self, request, timeout=None):
        self.called = True
        raise OSError("测试不允许访问网络")


def make_config(tmp_path):
    data_dir = tmp_path / "data"
    config = tmp_path / "runtime.toml"
    config.write_text(f"data_dir = '{data_dir}'\n", encoding="utf-8")
    data_dir.mkdir()
    return config, data_dir


def valid_state(config, *, endpoint="http://127.0.0.1:43123"):
    return {
        "protocol_version": 2,
        "implementation_version": "0.3.1",
        "implementation_sha256": "a" * 64,
        "config_sha256": "b" * 64,
        "instance_id": "c" * 32,
        "pid": 12345,
        "endpoint": endpoint,
        "token": "d" * 64,
        "config_path": str(config.resolve()),
        "started_at": "2026-09-09T12:00:00Z",
    }


def write_state(data_dir, value):
    (data_dir / "controller.json").write_text(
        json.dumps(value, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://127.0.0.1:43123",
        "http://localhost:43123",
        "http://0.0.0.0:43123",
        "http://[::1]:43123",
        "http://user:pass@127.0.0.1:43123",
        "http://127.0.0.1:43123/not-control-root",
        "http://127.0.0.1:43123/?query=1",
        "http://127.0.0.1:43123/#fragment",
        "http://127.0.0.1",
    ],
)
def test_controller_state_rejects_non_loopback_or_ambiguous_endpoint(
    tmp_path, monkeypatch, endpoint
):
    """破坏点：若客户端信任 state 中任意 URL，Bearer token 可能被发往非目标地址。"""
    config, data_dir = make_config(tmp_path)
    write_state(data_dir, valid_state(config, endpoint=endpoint))
    opener = RejectingOpener()
    monkeypatch.setattr(
        "agy_worker.controller_client.urllib.request.build_opener",
        lambda *args, **kwargs: opener,
    )

    with pytest.raises(WorkerError) as caught:
        ControllerClient(config, autostart=False)

    assert caught.value.code == "controller_state_invalid"
    assert opener.called is False


def test_controller_state_rejects_unknown_fields_before_network(tmp_path, monkeypatch):
    """破坏点：当前协议 state 出现未知字段时不能被普通 Bridge 静默接受。"""
    config, data_dir = make_config(tmp_path)
    state = valid_state(config)
    state["unexpected"] = "value"
    write_state(data_dir, state)
    opener = RejectingOpener()
    monkeypatch.setattr(
        "agy_worker.controller_client.urllib.request.build_opener",
        lambda *args, **kwargs: opener,
    )

    with pytest.raises(WorkerError) as caught:
        ControllerClient(config, autostart=False)

    assert caught.value.code == "controller_state_invalid"
    assert opener.called is False


def test_controller_state_rejects_missing_identity_before_network(tmp_path, monkeypatch):
    """破坏点：缺少冻结身份的 v2 state 不能退化成仅凭 PID/endpoint 判活。"""
    config, data_dir = make_config(tmp_path)
    state = valid_state(config)
    del state["instance_id"]
    write_state(data_dir, state)
    opener = RejectingOpener()
    monkeypatch.setattr(
        "agy_worker.controller_client.urllib.request.build_opener",
        lambda *args, **kwargs: opener,
    )

    with pytest.raises(WorkerError) as caught:
        ControllerClient(config, autostart=False)

    assert caught.value.code == "controller_state_invalid"
    assert opener.called is False
