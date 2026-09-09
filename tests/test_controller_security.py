"""Controller 连接元数据与凭据目录必须提供可验证的本机安全诊断。"""
import hashlib
import json
from pathlib import Path

import pytest

import agy_worker.controller_state as controller_state_module
import agy_worker.runtime as runtime_module
import agy_worker.security as security_module
from agy_worker.common import WorkerError
from agy_worker.controller_client import ControllerClient
from agy_worker.runtime import Runtime
from agy_worker.security import classify_broad_read_principals, inspect_data_dir_acl


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


def test_stale_hash_is_not_reported_before_authenticated_health(tmp_path, monkeypatch):
    """残留 state 本身不能证明旧 Controller 仍在运行；先做鉴权 health 再判断 stale。"""
    config, data_dir = make_config(tmp_path)
    write_state(data_dir, valid_state(config))
    opener = RejectingOpener()
    monkeypatch.setattr(
        "agy_worker.controller_client.urllib.request.build_opener",
        lambda *args, **kwargs: opener,
    )

    with pytest.raises(WorkerError) as caught:
        ControllerClient(config, autostart=False)

    assert caught.value.code == "controller_unavailable"
    assert opener.called is True


def test_controller_implementation_digest_matches_fixed_persistent_module_set():
    """实现摘要必须严格遵守已批准计划中的固定常驻模块集合。"""
    relative_files = (
        "controller.py",
        "controller_protocol.py",
        "runtime.py",
        "common.py",
        "models.py",
        "artifacts.py",
        "logs.py",
        "processes.py",
        "browser.py",
    )
    root = Path(controller_state_module.__file__).resolve().parent
    expected = hashlib.sha256()
    for relative in sorted(relative_files):
        expected.update(relative.encode("utf-8"))
        expected.update(b"\0")
        expected.update((root / relative).read_bytes())
        expected.update(b"\0")

    assert controller_state_module.controller_implementation_sha256() == expected.hexdigest()


def test_acl_classifier_only_flags_broad_read_grants():
    read = security_module.FILE_READ_DATA
    entries = [
        {"sid": "S-1-5-21-1000", "principal": "WORKSTATION\\elio", "access_mask": read, "allowed": True},
        {"sid": "S-1-5-18", "principal": "NT AUTHORITY\\SYSTEM", "access_mask": security_module.GENERIC_ALL, "allowed": True},
        {"sid": "S-1-5-32-544", "principal": "BUILTIN\\Administrators", "access_mask": security_module.GENERIC_ALL, "allowed": True},
        {"sid": "S-1-1-0", "principal": "Everyone", "access_mask": read, "allowed": True},
        {"sid": "S-1-5-32-545", "principal": "BUILTIN\\Users", "access_mask": security_module.GENERIC_READ, "allowed": True},
        {"sid": "S-1-5-11", "principal": "NT AUTHORITY\\Authenticated Users", "access_mask": security_module.GENERIC_READ, "allowed": True},
        # deny ACE 与无读取权限的 allow ACE 都不能当作宽泛读取 grant。
        {"sid": "S-1-1-0", "principal": "Everyone", "access_mask": read, "allowed": False},
        {"sid": "S-1-1-0", "principal": "Everyone", "access_mask": 0x00000002, "allowed": True},
    ]

    assert classify_broad_read_principals(entries) == [
        "Everyone",
        "BUILTIN\\Users",
        "NT AUTHORITY\\Authenticated Users",
    ]


def test_acl_api_failure_is_unknown_not_safe(tmp_path, monkeypatch):
    monkeypatch.setattr(
        security_module,
        "_read_acl_entries",
        lambda _path: (_ for _ in ()).throw(OSError("ACL API unavailable")),
    )

    report = inspect_data_dir_acl(tmp_path)

    assert report["checked"] is False
    assert report["broad_read_principals"] == []
    assert report["token_confidentiality_advisory"] is False
    assert "ACL API unavailable" in report["error"]


def test_capabilities_reports_acl_unknown_without_failing(tmp_path, monkeypatch):
    runtime = object.__new__(Runtime)
    runtime.root = tmp_path
    runtime.config = {"enabled_kinds": [], "workspaces": {}}
    unknown = {
        "checked": False,
        "broad_read_principals": [],
        "token_confidentiality_advisory": False,
        "error": "mock failure",
    }
    monkeypatch.setattr(runtime_module, "inspect_data_dir_acl", lambda _path: unknown)

    capabilities = runtime.capabilities()

    assert capabilities["controller"]["data_dir_acl"] == unknown
    assert capabilities["permissions"]["os_isolation"] is False
