"""验证常驻 Controller 可被多个一次性 stdio Bridge 共同使用。"""
import asyncio
import json
import sys
import threading
import time
from contextlib import AsyncExitStack, asynccontextmanager
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import agy_worker.controller as controller_module
import agy_worker.controller_client as controller_client_module
import agy_worker.manage as manage_module
import agy_worker.runtime as runtime_module
from agy_worker.common import WorkerError
from agy_worker.controller import ControllerService
from agy_worker.controller_client import ControllerClient


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


def rewrite_config_with_changed_enabled_kinds(config):
    text = config.read_text(encoding="utf-8")
    config.write_text(
        text.replace("enabled_kinds = ['build']", "enabled_kinds = ['build', 'test']"),
        encoding="utf-8",
    )


def wait_for_controller_state(config, timeout=3):
    state_path = config.parent / "data" / "controller.json"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if state_path.exists():
            return state_path, json.loads(state_path.read_text("utf-8"))
        time.sleep(0.02)
    raise AssertionError("Controller state 未在超时内发布")


class JsonResponse:
    def __init__(self, value):
        self.raw = json.dumps(value).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.raw


@asynccontextmanager
async def bridge(config):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agy_worker.server", "--config", str(config)],
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            yield session


def test_two_stdio_bridges_share_controller(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    service = ControllerService(config)
    monkeypatch.setattr(service.runtime.pool, "submit", lambda *args: None)

    async def scenario():
        async with AsyncExitStack() as stack:
            first = await stack.enter_async_context(bridge(config))
            second = await stack.enter_async_context(bridge(config))
            assert len((await first.list_tools()).tools) == 6
            assert len((await second.list_tools()).tools) == 6

            submitted = await first.call_tool(
                "agy_worker",
                {
                    "request_id": "shared-controller",
                    "workspace_id": "demo",
                    "kind": "build",
                    "objective": "只验证跨 Bridge 状态，不执行命令",
                    "permissions": {"build": True},
                    "inputs": {"command_id": "compile"},
                },
            )
            task_id = submitted.structured_content["task_id"]
            status = await second.call_tool("agy_status", {"task_id": task_id})
            assert status.structured_content["status"] == "queued"

            context = service.runtime.active[task_id]
            evidence = context["directory"] / "bridge-evidence.txt"
            evidence.write_text("跨 Bridge 证据", encoding="utf-8")
            context["artifacts"].add("bridge-evidence", evidence)
            artifact = await second.call_tool(
                "agy_artifact_read",
                {"task_id": task_id, "artifact_id": "bridge-evidence", "view": "text"},
            )
            assert artifact.structured_content["text"] == "跨 Bridge 证据"

        # 两个 Bridge 都退出后，独立 Controller 仍可响应。
        assert ControllerClient(config).call("status", {"task_id": task_id})["status"] == "queued"

    try:
        asyncio.run(scenario())
    finally:
        service.close()


def test_simultaneous_bridges_start_one_controller(tmp_path):
    config = make_config(tmp_path)
    clients = []
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            clients = list(pool.map(lambda _: ControllerClient(config), range(2)))
        pids = {client.state["pid"] for client in clients}
        assert len(pids) == 1
        assert clients[0].call("capabilities")["workspaces"][0]["workspace_id"] == "demo"
    finally:
        if clients:
            clients[0].stop()
            state_path = Path(clients[0].state_path)
            deadline = time.monotonic() + 10
            while state_path.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert not state_path.exists()


def test_restart_marks_active_task_interrupted_and_keeps_artifact(tmp_path, monkeypatch):
    config = make_config(tmp_path)
    first = ControllerService(config)
    monkeypatch.setattr(first.runtime.pool, "submit", lambda *args: None)
    request = {
        "request_id": "restart-test",
        "workspace_id": "demo",
        "kind": "build",
        "objective": "验证重启语义",
        "permissions": {"build": True},
        "inputs": {"command_id": "compile"},
    }
    existing_client = ControllerClient(config)
    submitted = existing_client.call("submit", request)
    context = first.runtime.active[submitted["task_id"]]
    evidence = context["directory"] / "saved.txt"
    evidence.write_text("保留的历史证据", encoding="utf-8")
    context["artifacts"].add("saved", evidence)
    first.close()

    second = ControllerService(config)
    try:
        status = existing_client.call("status", {"task_id": submitted["task_id"]})
        assert status["status"] == "interrupted"
        artifact = existing_client.call(
            "artifact_read",
            {"task_id": submitted["task_id"], "artifact_id": "saved", "view": "text"},
        )
        assert artifact["value"]["text"] == "保留的历史证据"
    finally:
        second.close()


def test_controller_identity_is_frozen_and_published(tmp_path):
    """破坏点：若 state 没有完整冻结身份，Bridge 无法判断后台实例是否已过期。"""
    config = make_config(tmp_path)
    service = ControllerService(config)
    try:
        assert service.state["protocol_version"] == 2
        assert len(service.state["implementation_sha256"]) == 64
        assert len(service.state["config_sha256"]) == 64
        assert len(service.state["instance_id"]) == 32
        assert service.state["implementation_version"]

        client = ControllerClient(config, autostart=False)
        assert client.state["instance_id"] == service.state["instance_id"]
        assert client.state["config_sha256"] == service.state["config_sha256"]
        assert client.state["implementation_sha256"] == service.state["implementation_sha256"]
    finally:
        service.close()


def test_stale_config_rejects_running_controller(tmp_path):
    """破坏点：后台 Runtime 已读取旧配置时，新 Bridge 不能继续把它当作当前配置实例。"""
    config = make_config(tmp_path)
    service = ControllerService(config)
    try:
        ControllerClient(config, autostart=False)
        rewrite_config_with_changed_enabled_kinds(config)

        with pytest.raises(WorkerError) as caught:
            ControllerClient(config, autostart=False)

        assert caught.value.code == "controller_stale_config"
    finally:
        service.close()


def test_stale_implementation_rejects_running_controller(tmp_path, monkeypatch):
    """破坏点：代码已经更新但旧 Controller 仍存活时，新 Bridge 必须 fail-closed。"""
    config = make_config(tmp_path)
    service = ControllerService(config)
    try:
        ControllerClient(config, autostart=False)
        monkeypatch.setattr(
            controller_client_module,
            "controller_implementation_sha256",
            lambda: "f" * 64,
            raising=False,
        )

        with pytest.raises(WorkerError) as caught:
            ControllerClient(config, autostart=False)

        assert caught.value.code == "controller_stale_implementation"
    finally:
        service.close()


def test_management_stop_can_stop_older_protocol_controller(tmp_path, monkeypatch):
    """普通业务拒绝旧协议，但显式管理停止必须仍能使用旧 state 自己的协议号。"""
    config = make_config(tmp_path)
    monkeypatch.setattr(controller_module, "PROTOCOL_VERSION", 1)
    monkeypatch.setattr(runtime_module, "PROTOCOL_VERSION", 1)
    thread = threading.Thread(target=controller_module.run, args=(config,), daemon=True)
    thread.start()
    state_path, _state = wait_for_controller_state(config)

    with pytest.raises(WorkerError) as caught:
        ControllerClient(config, autostart=False)
    assert caught.value.code == "protocol_mismatch"

    result = ControllerClient.stop_existing(config, timeout=3)
    assert result["ok"] is True
    assert result["status"] == "stopped"
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not state_path.exists()


def test_v2_stop_is_auth_only_but_business_call_stays_protocol_strict(tmp_path):
    """跨协议兼容性只能扩大到 stop，不能让普通业务调用绕过协议检查。"""
    config = make_config(tmp_path)
    thread = threading.Thread(target=controller_module.run, args=(config,), daemon=True)
    thread.start()
    state_path, state = wait_for_controller_state(config)
    client = ControllerClient(config, autostart=False)

    bad_call = client._request(
        state,
        "/control/call",
        {"protocol_version": 999, "method": "capabilities", "params": {}},
        timeout=1,
    )
    assert bad_call["ok"] is False
    assert bad_call["error"]["code"] == "protocol_mismatch"

    stop = client._request(state, "/control/stop", {"protocol_version": 999}, timeout=1)
    assert stop["ok"] is True
    thread.join(timeout=3)
    assert not thread.is_alive()
    assert not state_path.exists()


def test_management_stop_does_not_attack_replacement_instance(tmp_path, monkeypatch):
    """stop 请求发出后若 state 已被新实例替换，不得再向 replacement 发送任何请求。"""
    config = make_config(tmp_path)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    state_path = data_dir / "controller.json"
    target = {
        "protocol_version": 2,
        "pid": 111,
        "endpoint": "http://127.0.0.1:43123",
        "token": "d" * 64,
        "config_path": str(config.resolve()),
        "started_at": "2026-09-09T12:00:00Z",
        "instance_id": "a" * 32,
    }
    replacement = {
        **target,
        "pid": 222,
        "token": "e" * 64,
        "instance_id": "b" * 32,
    }
    state_path.write_text(json.dumps(target), encoding="utf-8")

    class ReplacingOpener:
        def __init__(self):
            self.requests = []

        def open(self, request, timeout=None):
            self.requests.append(request)
            if len(self.requests) != 1 or not request.full_url.endswith("/control/stop"):
                raise AssertionError("replacement 出现后不得继续发送控制请求")
            state_path.write_text(json.dumps(replacement), encoding="utf-8")
            return JsonResponse({"ok": True, "status": "stopping"})

    opener = ReplacingOpener()
    monkeypatch.setattr(
        controller_client_module.urllib.request,
        "build_opener",
        lambda *args, **kwargs: opener,
    )

    result = ControllerClient.stop_existing(config, timeout=1)
    assert result["ok"] is True
    assert result["status"] == "replaced"
    assert len(opener.requests) == 1


def test_manage_stop_accepts_custom_config(tmp_path, monkeypatch):
    """manage stop --config 必须把指定配置传给管理停止，而不是偷用正式配置。"""
    config = make_config(tmp_path)
    called = {}

    def fake_stop_existing(config_path, timeout=10):
        called["config_path"] = Path(config_path).resolve()
        called["timeout"] = timeout
        return {"ok": True, "status": "stopped"}

    monkeypatch.setattr(
        manage_module.ControllerClient,
        "stop_existing",
        staticmethod(fake_stop_existing),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["agy_worker.manage", "stop", "--config", str(config)],
    )

    manage_module.main()
    assert called["config_path"] == config.resolve()
