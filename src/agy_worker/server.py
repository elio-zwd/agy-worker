"""Codex 可见的任务级 MCP 工具与只读能力资源。"""
import argparse
import asyncio
import json
import time
from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server
from pydantic import ValidationError
from .common import WorkerError
from .models import (WorkerRequest, ContinueRequest, McpWorkerRequest, McpContinueRequest,
                     McpStatusRequest, CancelRequest, ArtifactRequest, CapabilitiesRequest)
from .controller_client import ControllerClient
from .controller_state import implementation_version

TOOL_TEXT_MAX_BYTES = 256
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled", "timed_out", "interrupted"}

TOOLS = {
    "agy_capabilities": (CapabilitiesRequest, "仅在 workspace_id 或 command_id 未知时调用，返回紧凑路由表；已知映射直接调用 agy_worker。完整 limits、Controller、权限和工作区诊断按需读取 agy://capabilities 或 agy://workspaces。"),
    "agy_worker": (McpWorkerRequest, "提交 AGY 任务并立即返回 task_id。AGY/agy 在支持任务中指本机 MCP，不是聊天、线程、agent 或 subagent；不得直接运行 agy/agy.exe，MCP 不可用时明确报告。已知 workspace_id 与 command_id 时直接调用，不要为定位 AGY 或调用入口先跑 git status/branch/log、rg AGY、agy --help 等探测。只使用 schema 暴露的当前可用权限；limits 仅在确需延长任务时设置 total_timeout_sec。编译只执行并采集错误，不分析或修改源码。"),
    "agy_continue": (McpContinueRequest, "续接已完成的 AGY 会话并启动新进程；给 expected_turn 与本轮完整可用权限，新逻辑续轮使用新的 req-<uuid4hex>。只使用 schema 暴露字段。"),
    "agy_status": (McpStatusRequest, "等待或查询任务状态。已有 revision 时传 after_revision；wait_ms 省略默认 50000，可按任务预计耗时自主选择 50000～600000。MCP 会把总等待预算切成内部最多 25 秒的 long-poll 并合并中间 progress/unchanged；AGY 提前进入终态会立即返回。没有 after_revision 时只读取即时快照。若总预算结束仍非终态，直接再次调用，不要在两次 agy_status 之间向用户发送等待说明。"),
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
        return _truncate_tool_text(f"agy_status: {status} rev={revision}；继续轮询，无需用户消息")
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


def _internal_request(model, target):
    """把 MCP 瘦请求扩展为 Runtime 完整模型，让内部安全默认值统一落地。"""
    return target.model_validate(model.model_dump(mode="json",by_alias=True))


async def _coalesced_status(client, model):
    """在一次 MCP 总等待预算内吞掉高频 progress revision，只把最终观察点交回 Codex。"""
    params=model.model_dump(mode="json",by_alias=True)
    wait_ms=params["wait_ms"]
    after_revision=params.get("after_revision")
    if after_revision is None:
        # 没有已知 revision 时没有可等待的变化基线，只取即时快照。
        return await asyncio.to_thread(
            client.call,"status",{**params,"wait_ms":0},timeout=30
        )

    deadline=time.monotonic()+wait_ms/1000
    current_revision=after_revision
    latest=None
    while True:
        remaining=deadline-time.monotonic()
        if remaining<=0:
            return latest if latest is not None else await asyncio.to_thread(
                client.call,"status",{**params,"wait_ms":0},timeout=30
            )
        poll_params={
            **params,
            "after_revision":current_revision,
            # Controller/Runtime 的既有单段合同仍最多 25 秒；较长预算只存在于 MCP 层。
            "wait_ms":max(1,min(25000,int(remaining*1000))),
        }
        result=await asyncio.to_thread(client.call,"status",poll_params,timeout=30)
        latest=result
        if not isinstance(result,dict) or result.get("status") in TERMINAL_STATUSES:
            return result
        revision=result.get("revision")
        if not isinstance(revision,int):
            return result
        if revision>current_revision:
            current_revision=revision
            continue
        if result.get("unchanged"):
            continue
        # 同 revision 的非 unchanged 响应不应出现；避免异常 Controller 造成热循环。
        return result


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
            "hint":"正常 MCP 请求只设置 schema 暴露字段；优先省略 limits，确需延长任务时只设置 total_timeout_sec。完整限制见 agy://capabilities。"}


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
                request=_internal_request(model,WorkerRequest)
                result = await asyncio.to_thread(client.call, "submit", request.model_dump(mode="json", by_alias=True))
            elif params.name == "agy_continue":
                request=_internal_request(model,ContinueRequest)
                result = await asyncio.to_thread(client.call, "continue", request.model_dump(mode="json", by_alias=True))
            elif params.name == "agy_status":
                result = await _coalesced_status(client,model)
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
                  "agy_worker/agy_continue 只填写工具 schema 暴露字段；不要添加 shell/code_write 或 artifact/summary 字节预算，确需延长任务只设置 total_timeout_sec。"
                  "queued/running 已知 revision 时用 after_revision；agy_status 的 wait_ms 省略默认 50000，可按预计耗时自主选择 50000～600000。较长 build/test 优先选择较长预算以减少模型轮询；AGY 终态会提前返回。单次 status 内部会用最多 25 秒分片合并 progress/unchanged。若仍非终态，立即再次调用，不要在轮询之间向用户发送等待说明。"
                  "完整 capabilities、worktree 和 artifact 只在需要时走冷资源。workspace_id 是登记别名；同仓库 Git worktree 用 workspace_path。"
                  "新逻辑请求使用新的 req-<uuid4hex>。AGY 只执行和采集证据，Codex 负责分析与源码修改。")
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
