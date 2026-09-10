"""验证 run-task 显式 custom config 的 Controller ownership 与清理边界。"""
import asyncio
import importlib.util
import json
import os
import sys
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import agy_worker.controller as controller_module
from agy_worker.controller import ControllerService
from agy_worker.controller_client import ControllerClient


RUN_TASK_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run-task.py"


def load_run_task_module():
    spec = importlib.util.spec_from_file_location("agy_worker_run_task_test", RUN_TASK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_config(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.py").write_text("pass", encoding="utf-8")
    config = tmp_path / "runtime.toml"
    config.write_text(
        f"data_dir = '{tmp_path / 'data'}'\n"
        "enabled_kinds = ['build']\n"
        "[workspaces.demo]\n"
        f"source = '{source}'\n"
        "allowed_commands = ['compile']\n",
        encoding="utf-8",
    )
    return config


def install_fake_stdio(module, monkeypatch):
    """替换 MCP stdio 慢边界；Controller 本身仍使用真实 state/health 生命周期。"""

    @asynccontextmanager
    async def fake_stdio(_options):
        yield object(), object()

    class FakeSession:
        def __init__(self, _reader, _writer):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def initialize(self):
            return None

        async def call_tool(self, _tool, _request, **_kwargs):
            payload = {"error": {"code": "test_stop", "message": "只验证 run-task 生命周期"}}
            return SimpleNamespace(content=[SimpleNamespace(text=json.dumps(payload))])

    monkeypatch.setattr(module, "stdio_client", fake_stdio)
    monkeypatch.setattr(module, "ClientSession", FakeSession)


def owned_launch(config, threads):
    """让 ControllerClient 认为自己启动了这个真实 Controller thread。"""

    def fake_launch(_client):
        thread = threading.Thread(target=controller_module.run, args=(config,), daemon=True)
        thread.start()
        threads.append(thread)
        return os.getpid()

    return fake_launch


def make_args(tmp_path, config, *, keep_controller=False):
    request = tmp_path / "request.json"
    request.write_text("{}", encoding="utf-8")
    return SimpleNamespace(
        request=str(request),
        output=None,
        config=str(config),
        keep_controller=keep_controller,
    )


def test_tool_result_value_prefers_structured_content():
    module = load_run_task_module()
    structured={"task_id":"task-1","status":"running","revision":5}
    response=SimpleNamespace(
        structured_content=structured,
        content=[SimpleNamespace(type="text",text="agy_worker: running；task=task-1")],
    )

    assert module.tool_result_value(response)==structured


def test_tool_result_value_falls_back_to_legacy_json_text():
    module = load_run_task_module()
    legacy={"task_id":"task-legacy","status":"queued","revision":1}
    response=SimpleNamespace(
        structured_content=None,
        content=[SimpleNamespace(type="text",text=json.dumps(legacy,ensure_ascii=False))],
    )

    assert module.tool_result_value(response)==legacy


@pytest.mark.skipif(sys.platform != "win32", reason="Runtime 基线使用 Windows msvcrt 锁")
def test_custom_config_cleans_controller_started_by_this_run(tmp_path, monkeypatch):
    module = load_run_task_module()
    install_fake_stdio(module, monkeypatch)
    config = make_config(tmp_path)
    threads = []
    monkeypatch.setattr(ControllerClient, "_launch", owned_launch(config, threads))

    assert asyncio.run(module.run(make_args(tmp_path, config))) == 1
    assert not (tmp_path / "data" / "controller.json").exists()
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()


@pytest.mark.skipif(sys.platform != "win32", reason="Runtime 基线使用 Windows msvcrt 锁")
def test_custom_config_preserves_preexisting_controller(tmp_path, monkeypatch):
    module = load_run_task_module()
    install_fake_stdio(module, monkeypatch)
    config = make_config(tmp_path)
    service = ControllerService(config)
    original_instance = service.state["instance_id"]
    try:
        assert asyncio.run(module.run(make_args(tmp_path, config))) == 1
        client = ControllerClient(config, autostart=False)
        assert client.state["instance_id"] == original_instance
    finally:
        service.close()


@pytest.mark.skipif(sys.platform != "win32", reason="Runtime 基线使用 Windows msvcrt 锁")
def test_custom_config_keep_controller_preserves_owned_instance(tmp_path, monkeypatch):
    module = load_run_task_module()
    install_fake_stdio(module, monkeypatch)
    config = make_config(tmp_path)
    threads = []
    monkeypatch.setattr(ControllerClient, "_launch", owned_launch(config, threads))

    assert asyncio.run(module.run(make_args(tmp_path, config, keep_controller=True))) == 1
    client = ControllerClient(config, autostart=False)
    instance_id = client.state["instance_id"]
    assert instance_id
    ControllerClient.stop_existing(config, expected_instance_id=instance_id, timeout=3)
    for thread in threads:
        thread.join(timeout=3)
        assert not thread.is_alive()
