"""测试级共享夹具；避免 deadline 时钟桩污染 asyncio 使用的标准库 time 模块。"""
import time as stdlib_time
from types import SimpleNamespace

import pytest

import agy_worker.server as server_module


@pytest.fixture(autouse=True)
def isolate_server_clock(monkeypatch):
    """server 的测试时钟使用模块局部代理，monkeypatch 不再改写全局 time.monotonic。"""
    monkeypatch.setattr(
        server_module,
        "time",
        SimpleNamespace(monotonic=stdlib_time.monotonic),
    )
