"""使用正式配置验证两个 stdio Bridge 共享同一个常驻 Controller。"""
import argparse
import asyncio
import json
import sys
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from agy_worker.controller_client import ControllerClient


@asynccontextmanager
async def bridge(config):
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "agy_worker.server", "--config", str(config)],
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            initialized = await session.initialize()
            yield initialized, session


async def verify(config):
    async with AsyncExitStack() as stack:
        first_init, first = await stack.enter_async_context(bridge(config))
        second_init, second = await stack.enter_async_context(bridge(config))
        first_tools = await first.list_tools()
        second_tools = await second.list_tools()
        capabilities = await second.call_tool("agy_capabilities", {})
        if len(first_tools.tools) != 6 or len(second_tools.tools) != 6:
            raise RuntimeError("两个 Bridge 未同时发现六个公开工具")
        result = {
            "first_server_version": first_init.server_info.version,
            "second_server_version": second_init.server_info.version,
            "tool_count": len(first_tools.tools),
            "workspace_count": len(capabilities.structured_content["workspaces"]),
        }

    # stdio 会话已经全部关闭，Controller 必须仍然可访问。
    controller = ControllerClient(config, autostart=False)
    status = controller.call("capabilities")
    result.update(
        controller_pid=controller.state["pid"],
        controller_protocol=controller.state["protocol_version"],
        controller_alive_after_bridges=True,
        max_concurrent_tasks=status["controller"]["max_concurrent_tasks"],
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()
    result = asyncio.run(verify(Path(args.config).resolve()))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
