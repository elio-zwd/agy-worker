"""验证 Codex 注册不会绕过 agy_worker，也不会覆盖用户既有全局指令。"""
import json
from pathlib import Path

import pytest
import tomlkit

import agy_worker.manage as manage
import agy_worker.server as server_module


def _prepare_config(monkeypatch, tmp_path, *, developer_instructions=None):
    codex_home = tmp_path / "codex"
    codex_home.mkdir()
    worker_root = tmp_path / "worker"
    worker_root.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setattr(manage, "ROOT", worker_root)

    document = tomlkit.document()
    if developer_instructions is not None:
        document["developer_instructions"] = developer_instructions
    servers = tomlkit.table()
    servers["other"] = {"command": "other.exe", "args": ["--keep"]}
    document["mcp_servers"] = servers
    path = codex_home / "config.toml"
    path.write_text(tomlkit.dumps(document), encoding="utf-8")
    return path


def _old_managed_block():
    return (
        f"{manage.CODEX_ROUTING_BEGIN}\n"
        "旧版 AGY Worker 路由规则。\n"
        f"{manage.CODEX_ROUTING_END}"
    )


def test_register_adds_codex_routing_without_overwriting_existing_instructions(monkeypatch, tmp_path):
    original = "保留用户已有 developer instruction。"
    path = _prepare_config(monkeypatch, tmp_path, developer_instructions=original)

    manage.register()
    document = tomlkit.parse(path.read_text("utf-8"))
    instructions = str(document["developer_instructions"])

    assert instructions.startswith(original)
    assert instructions.count(manage.CODEX_ROUTING_BEGIN) == 1
    assert instructions.count(manage.CODEX_ROUTING_END) == 1
    assert "agy_worker" in instructions
    assert "agy.exe" in instructions
    assert "不可直接" in instructions or "不得直接" in instructions
    assert document["mcp_servers"]["other"]["command"] == "other.exe"
    assert document["mcp_servers"]["agy_worker"]["command"] == str(Path(manage.sys.executable))

    # 重复注册必须幂等，不能把同一 developer instruction 反复追加到上下文。
    manage.register()
    repeated = tomlkit.parse(path.read_text("utf-8"))
    repeated_instructions = str(repeated["developer_instructions"])
    assert repeated_instructions.count(manage.CODEX_ROUTING_BEGIN) == 1
    assert repeated_instructions.count(manage.CODEX_ROUTING_END) == 1


def test_register_upgrades_previous_managed_block_and_preserves_user_prefix(monkeypatch, tmp_path):
    original = "用户自己的全局规则。"
    old_block = _old_managed_block()
    path = _prepare_config(
        monkeypatch,
        tmp_path,
        developer_instructions=original + "\n\n" + old_block,
    )

    manage.register()
    document = tomlkit.parse(path.read_text("utf-8"))
    instructions = str(document["developer_instructions"])

    assert instructions == original + "\n\n" + manage.CODEX_ROUTING_BLOCK
    assert "旧版 AGY Worker 路由规则" not in instructions
    assert instructions.count(manage.CODEX_ROUTING_BEGIN) == 1
    assert instructions.count(manage.CODEX_ROUTING_END) == 1


def test_routing_rule_closes_chat_thread_agent_loophole():
    """“让 AGY 跑一下编译”必须绑定 Worker，而不是被解释成另一个聊天/代理线程。"""
    instructions = manage.CODEX_ROUTING_BLOCK

    assert "让 AGY 跑一下编译" in instructions
    assert "只指" in instructions
    assert "agy_worker" in instructions
    assert "聊天" in instructions
    assert "线程" in instructions
    assert "agent" in instructions
    assert "subagent" in instructions
    assert "不得" in instructions


def test_unregister_removes_only_managed_routing_and_keeps_user_config(monkeypatch, tmp_path):
    original = "用户自己的全局规则必须原样保留。"
    path = _prepare_config(monkeypatch, tmp_path, developer_instructions=original)

    manage.register()
    manage.register(remove=True)
    document = tomlkit.parse(path.read_text("utf-8"))

    assert str(document["developer_instructions"]) == original
    assert "agy_worker" not in document["mcp_servers"]
    assert document["mcp_servers"]["other"]["args"] == ["--keep"]


def test_unregister_removes_previous_managed_block_and_keeps_user_prefix(monkeypatch, tmp_path):
    original = "用户自己的全局规则。"
    path = _prepare_config(
        monkeypatch,
        tmp_path,
        developer_instructions=original + "\n\n" + _old_managed_block(),
    )

    manage.register(remove=True)
    document = tomlkit.parse(path.read_text("utf-8"))

    assert str(document["developer_instructions"]) == original
    assert "agy_worker" not in document["mcp_servers"]
    assert document["mcp_servers"]["other"]["command"] == "other.exe"


def test_unregister_removes_developer_instruction_key_when_worker_created_it(monkeypatch, tmp_path):
    path = _prepare_config(monkeypatch, tmp_path)

    manage.register()
    manage.register(remove=True)
    document = tomlkit.parse(path.read_text("utf-8"))

    assert "developer_instructions" not in document
    assert "agy_worker" not in document["mcp_servers"]
    assert "other" in document["mcp_servers"]


def test_register_fails_closed_on_conflicting_managed_marker(monkeypatch, tmp_path):
    path = _prepare_config(
        monkeypatch,
        tmp_path,
        developer_instructions=f"用户内容\n{manage.CODEX_ROUTING_BEGIN}\n未闭合内容",
    )

    with pytest.raises(ValueError, match="路由指令标记"):
        manage.register()

    # 失败时不得把 MCP 注册或用户配置写一半。
    document = tomlkit.parse(path.read_text("utf-8"))
    assert "agy_worker" not in document["mcp_servers"]
    assert str(document["developer_instructions"]).endswith("未闭合内容")


def test_worker_tool_description_explicitly_prevents_direct_agy_cli_fallback():
    description = server_module.TOOLS["agy_worker"][1]

    assert "AGY" in description
    assert "MCP" in description
    assert "agy.exe" in description
    assert "直接" in description
    assert "不可用" in description
    assert "聊天" in description
    assert "线程" in description
    assert "subagent" in description


def test_schema_generation_uses_public_status_wait_contract(monkeypatch, tmp_path):
    """重新生成 schema 时必须保留 MCP 的 50～600 秒合同，不能泄漏内部 25 秒模型。"""
    root=tmp_path/'worker'
    (root/'schemas').mkdir(parents=True)
    monkeypatch.setattr(manage,'ROOT',root)

    manage.schemas()

    schema=json.loads((root/'schemas/agy_status.json').read_text('utf-8'))
    wait_schema=schema['properties']['wait_ms']
    assert wait_schema['default']==50000
    assert wait_schema['minimum']==50000
    assert wait_schema['maximum']==600000
