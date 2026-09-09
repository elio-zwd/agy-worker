"""最终代码质量审查发现的 Controller 生命周期回归用例。"""
import importlib.util
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


def make_config(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    config = tmp_path / "runtime.toml"
    config.write_text(f"data_dir = '{data_dir}'\n", encoding="utf-8")
    return config, data_dir


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


@pytest.mark.skipif(
    controller_client_module.sys.platform != "win32",
    reason="需要真实 Windows WMI Controller 启动",
)
def test_real_wmi_launch_records_controller_ownership(tmp_path):
    """真实 WMI 返回 PID 必须对应最终 healthy instance，才能安全建立 run-task ownership。"""
    config, data_dir = make_config(tmp_path)
    client = None
    try:
        client = ControllerClient(config, startup_timeout=10)
        assert client.last_launch_pid == client.state["pid"]
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
