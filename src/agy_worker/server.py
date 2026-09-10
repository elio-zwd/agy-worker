"""Codex 可见的任务级 MCP 工具与只读能力资源。"""
import argparse
import asyncio
import json
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError
from .common import WorkerError
from .models import (WorkerRequest, ContinueRequest, StatusRequest, CancelRequest,
                     ArtifactRequest, CapabilitiesRequest)
from .controller_client import ControllerClient
from .controller_state import implementation_version

TOOL_TEXT_MAX_BYTES = 256

TOOLS = {
    "agy_capabilities": (CapabilitiesRequest, "先调用此只读 MCP 工具发现参数范围、workspace_id、同仓库 worktree 和已登记命令。用户要求‘让 AGY/agy’执行已支持任务时，应通过本 server 的工具链处理，而不是直接运行 AGY CLI。通常省略 limits 使用默认值。"),
    "agy_worker": (WorkerRequest, "用户要求‘让 AGY/agy’执行编译、测试、日志、浏览器、图片或 Android UI 等已支持任务时使用此 MCP 工具。不得通过 terminal/shell 直接运行 agy/agy.exe（包括 agy -p），正常任务也不要先跑 agy --help；MCP 不可用时明确报告，不得静默回退。异步返回 task_id；按任务授权，源码写入默认禁止。编译只提取错误，不分析或修复。"),
    "agy_continue": (ContinueRequest, "续接已完成的 AGY 会话并启动新进程，必须给 expected_turn 与完整本轮权限；每个新逻辑续轮使用新的 req-<uuid4hex>。"),
    "agy_status": (StatusRequest, "查询任务状态与有界结构化结果，可等待最多 25 秒的状态变化。"),
    "agy_cancel": (CancelRequest, "取消排队/运行任务；重复取消不会影响其他任务。"),
    "agy_artifact_read": (ArtifactRequest, "按任务与证据 ID 读取脱敏日志片段或图片，默认不返回原始敏感日志。"),
}


def _truncate_tool_text(value):
    """限制热路径 TextContent 的 UTF-8 字节数。"""
    raw=value.encode("utf-8")
    if len(raw)<=TOOL_TEXT_MAX_BYTES:
        return value
    return raw[:TOOL_TEXT_MAX_BYTES].decode("utf-8",errors="ignore")


def _compact_tool_text(tool_name, result):
    """TextContent 只提供人类可读摘要，机器结果以 structuredContent 为准。"""
    if not isinstance(result,dict):
        return _truncate_tool_text(f"{tool_name}: ok")
    status=result.get("status")
    revision=result.get("revision")
    if tool_name=="agy_status" and result.get("unchanged"):
        return _truncate_tool_text(f"agy_status: {status} rev={revision}；无变化")
    if status is not None:
        text=f"{tool_name}: {status}"
        if revision is not None:
            text+=f" rev={revision}"
        summary=(result.get("result") or {}).get("summary") if isinstance(result.get("result"),dict) else None
        if summary:
            text+=f"；{summary}"
        elif result.get("task_id"):
            text+=f"；task={result['task_id']}"
        return _truncate_tool_text(text)
    return _truncate_tool_text(f"{tool_name}: ok")


def _compact_error_text(body):
    """错误正文保留 code/message，但不再复制完整结构化错误 JSON。"""
    code=body.get("error") or body.get("code") or "invalid_request"
    message=body.get("message") or "请求失败"
    return _truncate_tool_text(f"{code}: {message}")


def validation_body(error):
    details=[]; messages=[]
    for issue in error.errors(include_url=False,include_input=False):
        field=".".join(str(part) for part in issue["loc"])
        context=issue.get("ctx",{})
        if issue["type"]=="less_than_equal":
            message=f"{field} 最大为 {context['le']}"
        elif issue["type"]=="greater_than_equal":
            message=f"{field} 最小为 {context['ge']}"
        else:
            message=f"{field}: {issue['msg']}"
        if field.startswith("limits."):
            message += "；建议省略该字段使用服务端默认值"
        messages.append(message)
        details.append({"field":field,"rule":issue["type"],**context})
    return {"error":"invalid_request","message":"；".join(messages),"details":details,
            "hint":"先调用 agy_capabilities 获取当前限制和可用工作区。"}


def build_server(client):
    """构造 MCP Server；版本统一来自已安装包 metadata。"""
    async def list_tools(context, params):
        return types.ListToolsResult(tools=[types.Tool(name=name, description=description,
            inputSchema=model.model_json_schema(by_alias=True)) for name,(model,description) in TOOLS.items()])

    async def call_tool(context, params):
        try:
            if params.name not in TOOLS:
                raise WorkerError("invalid_request", "未知工具")
            model = TOOLS[params.name][0].model_validate(params.arguments or {})
            if params.name == "agy_capabilities":
                result = await asyncio.to_thread(client.call, "capabilities")
            elif params.name == "agy_worker":
                result = await asyncio.to_thread(client.call, "submit", model.model_dump(mode="json", by_alias=True))
            elif params.name == "agy_continue":
                result = await asyncio.to_thread(client.call, "continue", model.model_dump(mode="json", by_alias=True))
            elif params.name == "agy_status":
                result = await asyncio.to_thread(client.call, "status", model.model_dump(mode="json", by_alias=True), timeout=30)
            elif params.name == "agy_cancel":
                result = await asyncio.to_thread(client.call, "cancel", model.model_dump(mode="json", by_alias=True))
            else:
                envelope = await asyncio.to_thread(client.call, "artifact_read", model.model_dump(mode="json", by_alias=True))
                if envelope["content_type"] == "image":
                    return types.CallToolResult(content=[types.ImageContent(type="image",data=envelope["data"],mimeType=envelope["metadata"]["media_type"])])
                value=envelope["value"]
                return types.CallToolResult(content=[types.TextContent(type="text",text=json.dumps(value,ensure_ascii=False))])
            return types.CallToolResult(
                content=[types.TextContent(type="text",text=_compact_tool_text(params.name,result))],
                structuredContent=result,
            )
        except (WorkerError, ValidationError, ValueError) as error:
            body=validation_body(error) if isinstance(error,ValidationError) else {
                "error":getattr(error,"code","invalid_request"),"message":str(error)[:1500]}
            return types.CallToolResult(
                content=[types.TextContent(type="text",text=_compact_error_text(body))],
                structuredContent=body,isError=True,
            )

    async def list_resources(context, params):
        return types.ListResourcesResult(resources=[
            types.Resource(name="AGY Worker 能力",uri="agy://capabilities",mimeType="application/json",
                           description="参数范围、已启用能力、安全边界和已登记工作区"),
            types.Resource(name="AGY Worker 工作区",uri="agy://workspaces",mimeType="application/json",
                           description="workspace_id、已登记路径、同仓库 worktree 和命令 ID")])

    async def list_resource_templates(context, params):
        return types.ListResourceTemplatesResult(resourceTemplates=[])

    async def read_resource(context, params):
        uri=str(params.uri); capabilities=await asyncio.to_thread(client.call, "capabilities")
        if uri=="agy://capabilities":
            value=capabilities
        elif uri=="agy://workspaces":
            value={"schema_version":1,"workspaces":capabilities["workspaces"]}
        else:
            raise ValueError("未知 AGY Worker 资源")
        return types.ReadResourceResult(contents=[types.TextResourceContents(
            uri=uri,mimeType="application/json",text=json.dumps(value,ensure_ascii=False,indent=2))])

    instructions=("用户要求‘让 AGY/agy’执行本 Worker 已支持的任务时，必须使用本 MCP server 工具，不得通过 shell/terminal 直接运行 agy/agy.exe/agy -p，正常任务也不要先跑 agy --help；MCP 不可用时明确报告，不得静默回退。"
                  "先调用 agy_capabilities 或读取 agy://workspaces，再提交任务。workspace_id 是登记别名，不是路径；"
                  "同仓库 Git worktree 使用 workspace_path。通常省略 limits 使用默认值。"
                  "新逻辑请求使用新的 req-<uuid4hex>；只有同一逻辑请求的传输/重连重试才复用 request_id。"
                  "AGY 只执行和采集证据；Codex 负责分析与源码修改。")
    return Server("elio-agy-worker",version=implementation_version(),instructions=instructions,
                  on_list_tools=list_tools,on_call_tool=call_tool,on_list_resources=list_resources,
                  on_list_resource_templates=list_resource_templates,on_read_resource=read_resource)


async def serve(config):
    client = await asyncio.to_thread(ControllerClient, config)
    server=build_server(client)
    async with stdio_server() as (reader,writer):
        await server.run(reader,writer,server.create_initialization_options())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--config",required=True)
    args=parser.parse_args()
    asyncio.run(serve(args.config))


if __name__=="__main__":
    main()
