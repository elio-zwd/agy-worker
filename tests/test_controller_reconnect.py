"""验证 Controller 断线重连不会重复 long-poll，并锁定外层 MCP timeout。"""
import tomllib
from pathlib import Path

import pytest

import agy_worker.manage as manage_module
from agy_worker.common import WorkerError
from agy_worker.controller_client import ControllerClient


def make_client_for_retry(monkeypatch, responses):
    client = object.__new__(ControllerClient)
    client.state = {"marker": "old"}
    calls = []

    def fake_request(state, path, payload=None, timeout=30):
        calls.append({"state": state, "path": path, "payload": payload, "timeout": timeout})
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    monkeypatch.setattr(client, "_request", fake_request)
    monkeypatch.setattr(client, "_ensure", lambda _timeout: {"marker": "new"})
    return client, calls


def test_status_reconnect_second_attempt_disables_long_poll(monkeypatch):
    client, calls = make_client_for_retry(
        monkeypatch,
        [
            WorkerError("controller_unavailable", "断线"),
            {"ok": True, "result": {"status": "queued"}},
        ],
    )
    params = {"task_id": "task-1", "after_revision": 7, "wait_ms": 25000}

    result = client.call("status", params, timeout=30)

    assert result["status"] == "queued"
    assert calls[0]["payload"]["params"] == params
    assert calls[1]["payload"]["params"] == {
        "task_id": "task-1",
        "after_revision": 7,
        "wait_ms": 0,
    }
    assert params["wait_ms"] == 25000


@pytest.mark.parametrize("method", ["submit", "continue"])
def test_mutating_request_reconnect_keeps_request_id(monkeypatch, method):
    client, calls = make_client_for_retry(
        monkeypatch,
        [
            WorkerError("controller_unavailable", "断线"),
            {"ok": True, "result": {"task_id": "task-1"}},
        ],
    )
    params = {"request_id": "req-fixed", "workspace_id": "demo"}

    client.call(method, params)

    assert calls[0]["payload"]["params"]["request_id"] == "req-fixed"
    assert calls[1]["payload"]["params"]["request_id"] == "req-fixed"


def test_register_sets_outer_mcp_tool_timeout_to_60(tmp_path, monkeypatch):
    codex_home = tmp_path / ".codex"
    monkeypatch.setenv("CODEX_HOME", str(codex_home))

    manage_module.register()

    document = tomllib.loads((codex_home / "config.toml").read_text("utf-8"))
    server = document["mcp_servers"]["agy_worker"]
    assert server["startup_timeout_sec"] == 20
    assert server["tool_timeout_sec"] == 60
    assert server["enabled_tools"] == [
        "agy_capabilities",
        "agy_worker",
        "agy_continue",
        "agy_status",
        "agy_cancel",
        "agy_artifact_read",
    ]
