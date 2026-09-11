"""锁定 v0.3.2 后续问题的修复目标，并保护既有 fail-closed 边界。"""
import pytest
from pydantic import ValidationError

import agy_worker.server as server_module
from agy_worker.models import Limits, McpLimits, McpStatusRequest
from agy_worker.runtime import Runtime


def test_default_task_budget_is_600_seconds():
    """默认任务预算应覆盖已观察到的约 267 秒构建以及合理的前置开销。"""
    assert McpLimits().total_timeout_sec == 600
    assert Limits().total_timeout_sec == 600


def test_runtime_capabilities_reports_same_default_task_budget():
    """冷资源里的能力声明必须与实际请求模型使用同一个默认值。"""
    runtime = Runtime.__new__(Runtime)
    runtime.config = {"enabled_kinds": [], "workspaces": {}}

    capabilities = runtime.capabilities()

    assert capabilities["limits"]["total_timeout_sec"] == {
        "default": 600,
        "min": 10,
        "max": 1800,
    }


def test_public_status_contract_still_rejects_internal_short_poll_value():
    """公开 wait_ms 继续 fail-closed，内部短轮询值不能变成兼容入口。"""
    with pytest.raises(ValidationError):
        McpStatusRequest(task_id="task-1", after_revision=1, wait_ms=25000)


def test_model_visible_status_guidance_hides_internal_poll_budget(monkeypatch):
    """Codex 可见提示只描述公开合同，不能泄露可被误抄成 wait_ms 的内部 25 秒实现值。"""
    captured = {}

    class FakeServer:
        def __init__(self, name, *, version, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(server_module, "Server", FakeServer)
    server_module.build_server(object())

    guidance = server_module.TOOLS["agy_status"][1] + "\n" + captured["instructions"]
    assert "25 秒" not in guidance
    assert "25000" not in guidance
    assert "省略 after_revision 和 wait_ms" in guidance
