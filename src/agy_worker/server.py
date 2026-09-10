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
    "agy_capabilities": (CapabilitiesRequest, "仅在 workspace_id 或 command_id 未知时调用，返回紧凑路由表；已知映射直接调用 agy_worker。完整 limits、Controller、权限和工作区诊断按需读取 agy://capabilities 或 agy://workspaces。"),
    "agy_worker": (WorkerRequest, "提交 AGY 任务并立即返回 task_id。AGY/agy 在支持任务中指本机 MCP，不是聊天、线程、agent 或 subagent；不得直接运行 agy/agy.exe，MCP 不可用时明确报告。已知 workspace_id 与 command_id 时直接调用，不要为定位 AGY 或调用入口先跑 git status/branch/log、rg AGY、agy --help 等探测。编译只执行并采集错误，不分析或修改源码。"),
    "agy_continue": (ContinueRequest, "续接已完成的 AGY 会话并启动新进程；给 expected_turn 与本轮完整权限，新逻辑续轮使用新的 req-<uuid4hex>。"),
    "agy_status": (StatusRequest, "等待或查询任务状态。queued/running 时优先传上次 revision 为 after_revision，并用 wait_ms=25000 长轮询；unchanged 只表示本窗口无新 revision，应静默继续等待，不要逐次向用户解释。"),
    "agy_cancel": (CancelRequest, "取消排队/运行任务；重复取消不会影响其他任务。"),
    "agy_artifact_read": (ArtifactRequest, "按需读取证据；成功热路径不要无条件读取完整日志或结果。"),
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


def _routing_capabilities(capabilities):
    """把完整能力事实投影成热路径只需的 workspace/command 路由表。"""
    workspaces=[]
    for workspace in capabilities.get("workspaces",[]):
        item={key:workspace[key] for key in ("workspace_id","registered_path","allowed_commands") if key in workspace}
        known=workspace.get("known_worktrees")
        if known and (len(known)>1 or known[0]!=workspace.get("registered_path")):
            item["known_worktrees"]=known
        workspaces.append(item)
    return {"schema_version":capabilities.get("schema_version",1),"workspaces":workspaces}


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
                full = await asyncio.to_thread(client.call, "capabilities")
                result = _routing_capabilities(full)
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
                           description="完整参数范围、已启用能力、安全边界和工作区诊断；仅在需要冷信息时读取"),
            types.Resource(name="AGY Worker 工作区",uri="agy://workspaces",mimeType="application/json",
                           description="完整 workspace、Git worktree 和命令登记；紧凑路由不足时读取")])

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

    instructions=("AGY/agy 在支持任务中指 agy_worker MCP。已知 workspace_id 和 command_id 时直接 agy_worker；未知时仅调用一次紧凑 agy_capabilities，不要为定位 AGY 先跑 git/rg/chat/CLI 探测。"
                  "queued/running 用 after_revision + wait_ms=25000 长轮询；unchanged 静默继续。完整 capabilities、worktree 和 artifact 只在需要时走冷资源。"
                  "workspace_id 是登记别名；同仓库 Git worktree 用 workspace_path。新逻辑请求使用新的 req-<uuid4hex>。AGY 只执行和采集证据，Codex 负责分析与源码修改。")
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
