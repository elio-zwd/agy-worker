"""最终代码质量审查发现的 Controller 生命周期回归用例。"""
import importlib.util
import json
import os
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

import agy_worker.controller_client as controller_client_module
from agy_worker.common import WorkerError
from agy_worker.controller_client import ControllerClient


VERIFY_CONTROLLER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "verify-controller.py"


def load_verify_controller_module():
    spec = importlib.util.spec_from_file_location(
        "agy_worker_verify_controller_quality_test", VERIFY_CONTROLLER_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verify_controller_targets_v032():
    module = load_verify_controller_module()

    assert module.EXPECTED_VERSION == "0.3.2"


def make_config(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config = tmp_path / "runtime.toml"
    config.write_text(f"data_dir = '{data_dir}'\n", encoding="utf-8")
    return config, data_dir


class JsonResponse:
    def __init__(self, value):
        self.raw = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.raw


def test_fresh_start_does_not_treat_unreachable_existing_state_as_not_running(
    tmp_path, monkeypatch
):
    module = load_verify_controller_module()
    config, data_dir = make_config(tmp_path)
    (data_dir / "controller.json").write_text("{}", encoding="utf-8")

    def unavailable(*_args, **_kwargs):
        raise WorkerError("controller_unavailable", "临时无法连接")

    monkeypatch.setattr(module.ControllerClient, "stop_existing", staticmethod(unavailable))

    assert module.stop_for_fresh_start(config) == "unreachable"


def test_fresh_start_can_classify_missing_state_as_not_running(tmp_path, monkeypatch):
    module = load_verify_controller_module()
    config, _data_dir = make_config(tmp_path)

    def unavailable(*_args, **_kwargs):
        raise WorkerError("controller_unavailable", "没有现有 Controller")

    monkeypatch.setattr(module.ControllerClient, "stop_existing", staticmethod(unavailable))

    assert module.stop_for_fresh_start(config) == "not_running"


def test_windows_launch_retries_use_distinct_environment_files(tmp_path, monkeypatch):
    config, data_dir = make_config(tmp_path)
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_text("", encoding="utf-8")
    fake_pythonw.write_text("", encoding="utf-8")
    monkeypatch.setattr(controller_client_module.sys, "executable", str(fake_python))
    monkeypatch.setattr(controller_client_module.shutil, "which", lambda _name: "C:/pwsh.exe")

    commands = []
    pids = iter((41001, 41002))

    def fake_run(*_args, **kwargs):
        commands.append(kwargs["env"]["AGY_WORKER_CONTROLLER_COMMAND"])
        return SimpleNamespace(returncode=0, stdout=f"{next(pids)}\n", stderr="")

    monkeypatch.setattr(controller_client_module.subprocess, "run", fake_run)
    client = object.__new__(ControllerClient)
    client.data_dir = data_dir
    client.config_path = config.resolve()

    assert client._launch_windows(tmp_path / "logs") == 41001
    assert client._launch_windows(tmp_path / "logs") == 41002

    assert commands[0] != commands[1]
    assert "controller-environment-" in commands[0]
    assert "controller-environment-" in commands[1]
    assert "controller-environment.json" not in commands[0]
    assert "controller-environment.json" not in commands[1]


def test_stale_controller_environment_files_are_cleaned_without_touching_fresh_files(tmp_path):
    _config, data_dir = make_config(tmp_path)
    stale = data_dir / "controller-environment-stale.json"
    fresh = data_dir / "controller-environment-fresh.json"
    legacy = data_dir / "controller-environment.json"
    for path in (stale, fresh, legacy):
        path.write_text("{}", encoding="utf-8")
    old = time.time() - 600
    os.utime(stale, (old, old))
    os.utime(legacy, (old, old))

    client = object.__new__(ControllerClient)
    client.data_dir = data_dir
    client._cleanup_stale_environment_files(older_than=300)

    assert not stale.exists()
    assert not legacy.exists()
    assert fresh.exists()


def test_stop_waits_for_state_disappearance_after_health_disconnect(tmp_path, monkeypatch):
    """HTTP 先消失而 state 尚未 unlink 时，stop 不得提前宣告完整退出。"""
    config, data_dir = make_config(tmp_path)
    state_path = data_dir / "controller.json"
    state = {
        "protocol_version": 2,
        "pid": 41001,
        "endpoint": "http://127.0.0.1:43123",
        "token": "d" * 64,
        "config_path": str(config.resolve()),
        "started_at": "2026-09-09T12:00:00Z",
        "instance_id": "a" * 32,
    }
    state_path.write_text(json.dumps(state), encoding="utf-8")

    original_management_state = ControllerClient._management_state
    management_reads = 0

    def staged_management_state(config_path, observed_state_path):
        nonlocal management_reads
        management_reads += 1
        if management_reads >= 3:
            observed_state_path.unlink(missing_ok=True)
            return None
        return original_management_state(config_path, observed_state_path)

    class StopThenDisconnectOpener:
        def open(self, request, timeout=None):
            if request.full_url.endswith("/control/stop"):
                return JsonResponse({"ok": True, "status": "stopping"})
            if request.full_url.endswith("/control/health"):
                raise controller_client_module.urllib.error.URLError("listener already closed")
            raise AssertionError(f"unexpected request: {request.full_url}")

    monkeypatch.setattr(
        ControllerClient,
        "_management_state",
        staticmethod(staged_management_state),
    )
    monkeypatch.setattr(
        controller_client_module.urllib.request,
        "build_opener",
        lambda *args, **kwargs: StopThenDisconnectOpener(),
    )

    result = ControllerClient.stop_existing(config, timeout=1)

    assert result == {"ok": True, "status": "stopped"}
    assert management_reads >= 3
    assert not state_path.exists()


def test_owned_launch_accepts_healthy_descendant_pid(monkeypatch):
    """Windows venv launcher PID 与 Python 子进程 PID 不同时，仍需建立同一次 launch 的 ownership。"""
    client = object.__new__(ControllerClient)
    client.started_controller = False
    client.started_instance_id = None
    client.last_launch_pid = 41001
    client._launched_pids = {41001}
    state = {"pid": 42002, "instance_id": "a" * 32}

    monkeypatch.setattr(controller_client_module.sys, "platform", "win32")
    monkeypatch.setattr(
        ControllerClient,
        "_process_is_alive",
        staticmethod(lambda pid: pid == 41001),
    )
    monkeypatch.setattr(
        ControllerClient,
        "_process_descends_from",
        staticmethod(lambda pid, ancestor: (pid, ancestor) == (42002, 41001)),
    )

    client._accept_healthy_state(state)

    assert client.started_controller is True
    assert client.started_instance_id == state["instance_id"]


@pytest.mark.skipif(
    controller_client_module.sys.platform != "win32",
    reason="需要真实 Windows WMI Controller 启动",
)
def test_real_wmi_launch_records_controller_ownership(tmp_path):
    """真实 WMI venv launcher 必须能安全归属其最终 healthy Python 子进程。"""
    config, data_dir = make_config(tmp_path)
    client = None
    try:
        client = ControllerClient(config, startup_timeout=10)
        assert client.last_launch_pid is not None
        assert client.state["pid"] > 0
        assert client.started_controller is True
        assert client.started_instance_id == client.state["instance_id"]
    finally:
        state_path = data_dir / "controller.json"
        if state_path.exists():
            expected_instance_id = client.state["instance_id"] if client is not None else None
            ControllerClient.stop_existing(
                config,
                expected_instance_id=expected_instance_id,
                timeout=10,
            )
