"""只给 AGY 使用的 MCP 入口，令牌来自本轮子进程环境。"""
import asyncio
import json
import os
import urllib.request
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

SCHEMA = {"type": "object", "properties": {
    "action": {"type": "string", "enum": ["execute", "read_log", "browser", "android", "image"]},
    "arguments": {"type": "object"}}, "required": ["action"], "additionalProperties": False}


async def list_tools(context, params):
    return types.ListToolsResult(tools=[types.Tool(name="worker_action",
        description="执行当前 Worker 授权范围内的操作。execute 不需要命令参数；read_log 接受 start_line/line_count；browser 接受 tool/arguments；android 接受 operation；image 接受 index。不得调用原生 shell 或其他 MCP 绕过。",
        inputSchema=SCHEMA)])


def forward(arguments):
    endpoint = os.environ.get("AGY_WORKER_ENDPOINT", "")
    token = os.environ.get("AGY_WORKER_TOKEN", "")
    if not endpoint.startswith("http://127.0.0.1:") or not token:
        return {"error": "permission_denied", "message": "仅 Worker 启动的 AGY 任务可以使用此工具"}
    request = urllib.request.Request(endpoint+"/action", data=json.dumps(arguments).encode(),
               headers={"Authorization": "Bearer "+token, "Content-Type": "application/json"})
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=1800) as response:
        return json.load(response)


async def call_tool(context, params):
    if params.name != "worker_action":
        raise ValueError("未知工具")
    try:
        result = await asyncio.to_thread(forward, params.arguments or {})
        if "image_base64" in result:
            return types.CallToolResult(content=[types.ImageContent(type="image", data=result["image_base64"], mimeType=result["media_type"])])
        return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(result,ensure_ascii=False))],
                                    isError="error" in result)
    except Exception:
        return types.CallToolResult(content=[types.TextContent(type="text", text="Worker 执行入口不可用")], isError=True)


async def main():
    server = Server("agy-worker-broker", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool)
    async with stdio_server() as (reader, writer):
        await server.run(reader, writer, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
